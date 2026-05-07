"""
Mail folder discovery and message retrieval via Microsoft Graph API.

Key design decisions:
- Folder name match is case-insensitive with Vietnamese Unicode normalization (NFC).
- Exact match is preferred over case-insensitive match when multiple folders exist.
- Top-level folders are searched first; child folders are traversed recursively.
- Messages are fetched with full body content so the portal URL can be extracted.
- Optional receivedDateTime filter is applied server-side via OData $filter.
"""
from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ..graph.client import GraphClient

logger = logging.getLogger(__name__)

_FOLDER_SELECT = "$select"
_FOLDER_FIELDS = "id,displayName,childFolderCount"


def _norm(text: str) -> str:
    """NFC-normalize and lowercase for Vietnamese-safe comparison."""
    return unicodedata.normalize("NFC", text).lower().strip()


def _to_utc_str(dt: datetime) -> str:
    """Convert a (possibly naive local) datetime to UTC ISO 8601 for OData $filter."""
    if dt.tzinfo is None:
        dt = dt.astimezone()   # attach local timezone (Python 3.6+)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── Data classes ───────────────────────────────────────────────────────────

@dataclass
class MailFolder:
    id: str
    display_name: str
    child_folder_count: int = 0
    parent_folder_id: Optional[str] = None


@dataclass
class EmailAddress:
    name: str
    address: str

    def __str__(self) -> str:
        if self.name:
            return f"{self.name} <{self.address}>"
        return self.address


@dataclass
class MailMessage:
    id: str
    internet_message_id: Optional[str]
    subject: str
    sender: EmailAddress
    received_datetime: str      # ISO 8601 UTC string from Graph API
    has_attachments: bool
    body_preview: str
    body_html: str = ""         # Full HTML body — used for portal URL extraction
    body_text: str = ""         # Plain text body — fallback for URL extraction
    raw: Dict[str, Any] = field(default_factory=dict)


# ── MailReader ─────────────────────────────────────────────────────────────

class MailReader:
    """Discovers folders and retrieves messages from Microsoft Graph."""

    def __init__(self, client: GraphClient, page_size: int = 50):
        self._client = client
        self._page_size = page_size

    def find_cong_van_folder(self, target_name: str = "Công văn") -> Optional[MailFolder]:
        """
        Find the mail folder whose displayName matches target_name
        (case-insensitive, Unicode-safe).
        Priority: exact match > case-insensitive > first child folder match.
        """
        target_norm = _norm(target_name)
        candidates: List[MailFolder] = []

        try:
            top_raw = list(self._client.paginate(
                "/me/mailFolders",
                params={_FOLDER_SELECT: _FOLDER_FIELDS, "$top": 100},
            ))
        except Exception as exc:
            logger.error("Cannot list mail folders: %s", exc)
            return None

        for raw in top_raw:
            folder = _raw_to_folder(raw)
            if _norm(folder.display_name) == target_norm:
                candidates.append(folder)
            if folder.child_folder_count > 0:
                candidates.extend(self._search_children(folder.id, target_norm))

        if not candidates:
            logger.error(
                "Thư mục '%s' không tìm thấy trong hộp thư (tìm kiếm không phân biệt hoa/thường).",
                target_name,
            )
            return None

        exact = [c for c in candidates if c.display_name == target_name]
        chosen = exact[0] if exact else candidates[0]

        if len(candidates) > 1:
            names = [c.display_name for c in candidates]
            logger.warning(
                "Tìm thấy %d thư mục khớp với '%s': %s. Dùng: '%s'",
                len(candidates), target_name, names, chosen.display_name,
            )

        logger.info("Đã tìm thấy thư mục '%s' (id=%s)", chosen.display_name, chosen.id)
        return chosen

    def _search_children(self, parent_id: str, target_norm: str) -> List[MailFolder]:
        matches: List[MailFolder] = []
        try:
            children_raw = list(self._client.paginate(
                f"/me/mailFolders/{parent_id}/childFolders",
                params={_FOLDER_SELECT: _FOLDER_FIELDS, "$top": 100},
            ))
        except Exception as exc:
            logger.warning("Cannot read child folders of %s: %s", parent_id, exc)
            return matches

        for raw in children_raw:
            folder = _raw_to_folder(raw, parent_id)
            if _norm(folder.display_name) == target_norm:
                matches.append(folder)
            if folder.child_folder_count > 0:
                matches.extend(self._search_children(folder.id, target_norm))
        return matches

    def get_messages(
        self,
        folder_id: str,
        received_after: Optional[datetime] = None,
        received_before: Optional[datetime] = None,
    ) -> List[MailMessage]:
        """
        Retrieve ALL messages from a folder (newest first), including full body.
        The full body is required to extract the portal document lookup URL.

        received_after / received_before: optional datetime bounds (local or UTC-aware).
        They are converted to UTC and applied as an OData $filter on receivedDateTime.
        """
        select_fields = ",".join([
            "id", "internetMessageId", "subject",
            "sender", "receivedDateTime",
            "hasAttachments", "bodyPreview",
            "body",
        ])
        params: Dict[str, Any] = {
            "$select": select_fields,
            "$top": self._page_size,
            "$orderby": "receivedDateTime desc",
        }

        filter_parts: List[str] = []
        if received_after:
            filter_parts.append(f"receivedDateTime ge {_to_utc_str(received_after)}")
        if received_before:
            filter_parts.append(f"receivedDateTime le {_to_utc_str(received_before)}")
        if filter_parts:
            params["$filter"] = " and ".join(filter_parts)

        messages: List[MailMessage] = []
        for raw in self._client.paginate(
            f"/me/mailFolders/{folder_id}/messages", params=params
        ):
            messages.append(_raw_to_message(raw))

        logger.info("Đã tải %d email từ thư mục.", len(messages))
        return messages

    def get_messages_by_sender(
        self,
        sender_email: str,
        received_after: Optional[datetime] = None,
        received_before: Optional[datetime] = None,
    ) -> List[MailMessage]:
        """
        Retrieve messages from Inbox filtered by sender email address.
        Used as fallback when folder-based search fails.
        """
        select_fields = ",".join([
            "id", "internetMessageId", "subject",
            "sender", "receivedDateTime",
            "hasAttachments", "bodyPreview",
            "body",
        ])
        filter_parts: List[str] = [
            f"sender/emailAddress/address eq '{sender_email}'"
        ]
        if received_after:
            filter_parts.append(f"receivedDateTime ge {_to_utc_str(received_after)}")
        if received_before:
            filter_parts.append(f"receivedDateTime le {_to_utc_str(received_before)}")

        params: Dict[str, Any] = {
            "$select": select_fields,
            "$top": self._page_size,
            # Note: $orderby cannot be combined with $filter on messages without
            # ConsistencyLevel header — sort in Python instead
            "$filter": " and ".join(filter_parts),
        }

        messages: List[MailMessage] = []
        for raw in self._client.paginate("/me/mailFolders/inbox/messages", params=params):
            messages.append(_raw_to_message(raw))

        # Sort newest first (mirrors folder-based behaviour)
        messages.sort(key=lambda m: m.received_datetime, reverse=True)

        logger.info("Đã tải %d email từ sender '%s'.", len(messages), sender_email)
        return messages


# ── Helpers ────────────────────────────────────────────────────────────────

def _raw_to_folder(raw: Dict[str, Any], parent_id: str = None) -> MailFolder:
    return MailFolder(
        id=raw["id"],
        display_name=raw["displayName"],
        child_folder_count=raw.get("childFolderCount", 0),
        parent_folder_id=parent_id,
    )


def _raw_to_message(raw: Dict[str, Any]) -> MailMessage:
    sender_raw = (raw.get("sender") or {}).get("emailAddress") or {}
    body_raw = raw.get("body") or {}
    content_type = (body_raw.get("contentType") or "text").lower()
    body_content = body_raw.get("content") or ""

    return MailMessage(
        id=raw["id"],
        internet_message_id=raw.get("internetMessageId"),
        subject=raw.get("subject") or "(không có tiêu đề)",
        sender=EmailAddress(
            name=sender_raw.get("name", ""),
            address=sender_raw.get("address", ""),
        ),
        received_datetime=raw["receivedDateTime"],
        has_attachments=bool(raw.get("hasAttachments", False)),
        body_preview=raw.get("bodyPreview", ""),
        body_html=body_content if content_type == "html" else "",
        body_text=body_content if content_type != "html" else "",
        raw=raw,
    )
