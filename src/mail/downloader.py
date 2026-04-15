"""
Attachment downloader for Microsoft Graph messages.

Design:
- Lists all file attachments (skips itemAttachment / referenceAttachment types).
- Downloads content bytes: tries contentBytes field in JSON first (works for
  files ≤ 4 MB); falls back to /$value binary endpoint for larger files.
- Handles filename collisions deterministically: appends _1, _2, … before
  the extension. Same inputs always produce the same output path.
- Sanitizes filenames to remove Windows-illegal characters.
"""
from __future__ import annotations

import base64
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from ..graph.client import GraphClient

logger = logging.getLogger(__name__)

_WIN_ILLEGAL = re.compile(r'[\\/:*?"<>|]')


# ── Data class ─────────────────────────────────────────────────────────────

@dataclass
class AttachmentInfo:
    id: str
    name: str           # sanitized filename
    content_type: str
    size: int           # bytes, from metadata
    is_inline: bool
    local_path: Optional[Path] = None   # set after successful download


# ── AttachmentDownloader ───────────────────────────────────────────────────

class AttachmentDownloader:
    """Downloads email attachments from Microsoft Graph to a local folder."""

    def __init__(self, client: GraphClient):
        self._client = client

    def list_attachments(self, message_id: str) -> List[AttachmentInfo]:
        """
        List all file attachments for a message (metadata only, no content).
        Skips itemAttachment and referenceAttachment types.
        """
        try:
            data = self._client.get(
                f"/me/messages/{message_id}/attachments",
                params={"$select": "id,name,contentType,size,isInline,@odata.type"},
            )
        except Exception as exc:
            logger.warning("Cannot list attachments for message %s: %s", message_id, exc)
            return []

        result: List[AttachmentInfo] = []
        for raw in data.get("value", []):
            odata_type = raw.get("@odata.type", "")
            # Only process file attachments
            if "fileAttachment" not in odata_type and odata_type != "":
                logger.debug("Skipping non-file attachment type: %s", odata_type)
                continue
            result.append(AttachmentInfo(
                id=raw["id"],
                name=_sanitize(raw.get("name") or "attachment"),
                content_type=raw.get("contentType", "application/octet-stream"),
                size=raw.get("size", 0),
                is_inline=bool(raw.get("isInline", False)),
            ))
        return result

    def download_all(
        self,
        message_id: str,
        target_folder: Path,
        attachments: Optional[List[AttachmentInfo]] = None,
    ) -> List[Path]:
        """
        Download all attachments into target_folder.
        Returns list of successfully written file paths.
        Creates target_folder if it doesn't exist.
        """
        if attachments is None:
            attachments = self.list_attachments(message_id)

        if not attachments:
            return []

        target_folder.mkdir(parents=True, exist_ok=True)
        downloaded: List[Path] = []

        for att in attachments:
            try:
                content = self._fetch_content(message_id, att)
                if content is None:
                    logger.warning("No content retrieved for '%s', skipping.", att.name)
                    continue
                dest = _unique_path(target_folder, att.name)
                dest.write_bytes(content)
                att.local_path = dest
                downloaded.append(dest)
                logger.info(
                    "  Downloaded: %-40s  (%s bytes) → %s",
                    att.name, f"{len(content):,}", dest.name,
                )
            except Exception as exc:
                logger.error("Failed to download attachment '%s': %s", att.name, exc)

        return downloaded

    # ── Private ────────────────────────────────────────────────────────────

    def _fetch_content(self, message_id: str, att: AttachmentInfo) -> Optional[bytes]:
        """
        Fetch attachment bytes.
        Strategy:
          1. Request the attachment JSON and decode contentBytes (works for ≤ 4 MB).
          2. If contentBytes missing/empty, fall back to /$value raw endpoint.
        """
        try:
            data = self._client.get(
                f"/me/messages/{message_id}/attachments/{att.id}",
                params={"$select": "contentBytes"},
            )
            cb = data.get("contentBytes")
            if cb:
                return base64.b64decode(cb)
        except Exception:
            pass  # fall through to $value endpoint

        try:
            return self._client.get_bytes(
                f"/me/messages/{message_id}/attachments/{att.id}/$value"
            )
        except Exception as exc:
            logger.error(
                "Cannot fetch content for attachment %s (id=%s): %s",
                att.name, att.id, exc,
            )
            return None


# ── Filename utilities ─────────────────────────────────────────────────────

def _sanitize(name: str) -> str:
    """Replace Windows-illegal characters and strip leading dots/spaces."""
    name = _WIN_ILLEGAL.sub("_", name)
    name = name.strip(". ")
    return name or "attachment"


def _unique_path(folder: Path, filename: str) -> Path:
    """
    Return a unique, deterministic path inside folder for filename.
    If file already exists: append _1, _2, … before the extension.
    Example: 'doc.pdf' → 'doc_1.pdf' → 'doc_2.pdf'
    This is deterministic: repeated calls with the same existing files
    always return the same next path.
    """
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    candidate = folder / filename
    counter = 1
    while candidate.exists():
        candidate = folder / f"{stem}_{counter}{suffix}"
        counter += 1
    return candidate

