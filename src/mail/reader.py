"""
Mail message retrieval via Microsoft Graph API.

Key design decisions:
- Messages are searched by sender across the full mailbox (/me/messages).
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
    """Retrieves messages from Microsoft Graph."""

    def __init__(self, client: GraphClient, page_size: int = 50):
        self._client = client
        self._page_size = page_size

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
        for raw in self._client.paginate("/me/messages", params=params):
            messages.append(_raw_to_message(raw))

        # Sort newest first (mirrors folder-based behaviour)
        messages.sort(key=lambda m: m.received_datetime, reverse=True)

        logger.info("Đã tải %d email từ sender '%s'.", len(messages), sender_email)
        return messages


# ── Helpers ────────────────────────────────────────────────────────────────

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
