"""
Per-day deduplication manager.

Storage: each daily folder contains _processed.json that records every
email processed in that folder.  The manager is scoped to ONE daily folder.

Layered dedup check (priority order):
  1. internetMessageId  — most reliable; globally unique per RFC 2822
  2. Graph message id   — Graph-internal; stable within a mailbox
  3. Business key: date_folder + so_don
  4. Business key: date_folder + attachment_filename

The tool is idempotent: running it multiple times in one day never creates
duplicate rows because:
  - Step 1/2 catches the same email object
  - Step 3/4 catches structurally equivalent records even if message id changed

is_duplicate() is called BEFORE writing to Excel.
register()     is called AFTER a successful write.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..folder.routing import get_tool_export_folder

logger = logging.getLogger(__name__)

_PROCESSED_FILE = "_processed.json"


@dataclass
class DedupRecord:
    message_id: str
    internet_message_id: Optional[str]
    date_folder: str
    so_don: Optional[str]
    attachment_filenames: List[str] = field(default_factory=list)
    processed_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    run_status: str = "OK"


class DedupManager:
    """
    Manages deduplication state for a single daily folder.
    Loads existing records on construction; persists on register().
    """

    def __init__(self, daily_folder: Path):
        self._folder = daily_folder
        # _processed.json lives exclusively in ~/.tool_mail_cong_van/<date>/
        self._file = get_tool_export_folder(daily_folder.name) / _PROCESSED_FILE
        self._records: Dict[str, DedupRecord] = {}   # keyed by message_id
        self._tech_keys: Set[str] = set()            # message_id + internet_message_id
        self._business_keys: Set[str] = set()        # date_folder|so_don, date_folder|filename
        self._load()

    # ── Public ─────────────────────────────────────────────────────────────

    def is_duplicate(
        self,
        message_id: str,
        internet_message_id: Optional[str],
        date_folder: str,
        so_don: Optional[str] = None,
        attachment_filenames: Optional[List[str]] = None,
    ) -> Tuple[bool, str]:
        """
        Check whether this email was already processed in this daily folder.
        Returns (is_dup: bool, reason: str).

        Reason is a human-readable explanation for logging.
        """
        # 1. internet_message_id (RFC 2822, most reliable)
        if internet_message_id and internet_message_id in self._tech_keys:
            return True, f"internetMessageId match: {internet_message_id[:40]}"

        # 2. Graph message id
        if message_id in self._tech_keys:
            return True, f"message_id match: {message_id[:20]}…"

        # 3. Business key: folder + so_don
        if so_don:
            bk = _bkey(date_folder, so_don)
            if bk in self._business_keys:
                return True, f"business key (so_don): {bk}"

        # 4. Business key: folder + attachment filename
        for fn in (attachment_filenames or []):
            bk = _bkey(date_folder, fn)
            if bk in self._business_keys:
                return True, f"business key (filename): {bk}"

        return False, ""

    def register(
        self,
        message_id: str,
        internet_message_id: Optional[str],
        date_folder: str,
        so_don: Optional[str] = None,
        attachment_filenames: Optional[List[str]] = None,
        run_status: str = "OK",
    ) -> DedupRecord:
        """
        Record this email as processed and persist to _processed.json.
        Must be called after a successful write to Excel.
        """
        rec = DedupRecord(
            message_id=message_id,
            internet_message_id=internet_message_id,
            date_folder=date_folder,
            so_don=so_don,
            attachment_filenames=attachment_filenames or [],
            run_status=run_status,
        )
        self._index(rec)
        self._save()
        return rec

    def count(self) -> int:
        return len(self._records)

    # ── Private ────────────────────────────────────────────────────────────

    def _load(self) -> None:
        if not self._file.exists():
            return
        try:
            raw = json.loads(self._file.read_text(encoding="utf-8"))
            for r in raw.get("records", []):
                rec = DedupRecord(
                    message_id=r["message_id"],
                    internet_message_id=r.get("internet_message_id"),
                    date_folder=r.get("date_folder", ""),
                    so_don=r.get("so_don"),
                    attachment_filenames=r.get("attachment_filenames", []),
                    processed_at=r.get("processed_at", ""),
                    run_status=r.get("run_status", "OK"),
                )
                self._index(rec)
            logger.debug(
                "Loaded %d dedup records from %s", len(self._records), self._file
            )
        except Exception as exc:
            logger.warning(
                "Cannot load dedup file %s (%s) — starting fresh for this run.", self._file, exc
            )

    def _index(self, rec: DedupRecord) -> None:
        self._records[rec.message_id] = rec
        self._tech_keys.add(rec.message_id)
        if rec.internet_message_id:
            self._tech_keys.add(rec.internet_message_id)
        if rec.so_don:
            self._business_keys.add(_bkey(rec.date_folder, rec.so_don))
        for fn in rec.attachment_filenames:
            self._business_keys.add(_bkey(rec.date_folder, fn))

    def _save(self) -> None:
        # self._file already points to ~/.tool_mail_cong_van/<date>/_processed.json
        # (directory created by get_tool_export_folder in __init__)
        payload = {
            "records": [asdict(r) for r in self._records.values()]
        }
        content = json.dumps(payload, ensure_ascii=False, indent=2)
        try:
            self._file.write_text(content, encoding="utf-8")
        except OSError as exc:
            logger.warning("Cannot write _processed.json to tool folder: %s", exc)


def _bkey(date_folder: str, value: str) -> str:
    """Build a business dedup key string."""
    return f"{date_folder}|{value}"

