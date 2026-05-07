"""
Per-day deduplication manager.

Storage: each daily folder contains _processed.json that records every
email processed in that folder.  The manager is scoped to ONE daily folder.

Layered dedup check (priority order):
  1. Portal URL       — primary business key; same URL = same document, skip download
  2. internetMessageId — fallback for emails without portal URL (RFC 2822)
  3. Graph message id  — fallback when internetMessageId unavailable
  4. Downloaded filename — post-download safety net for parallel threads

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

# ── DupCheckResult ─────────────────────────────────────────────────────────

@dataclass
class DupCheckResult:
    """Result of a dedup check.

    is_dup=True, needs_redownload=False  → skip entirely (already processed)
    is_dup=True, needs_redownload=True   → re-download files, skip Excel write
    is_dup=False                         → process as a new email
    """
    is_dup: bool
    reason: str = ""
    needs_redownload: bool = False
    download_url: Optional[str] = None

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
    download_url: Optional[str] = None      # portal URL — stored for fast re-download
    processed_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    run_status: str = "OK"
    # ── Excel row snapshot (used for full Excel regeneration) ──────────────
    excel_seq: Optional[int] = None
    excel_recv_date: Optional[str] = None       # DD/MM/YYYY — for date separator row
    excel_so_cong_van_num: Optional[str] = None
    excel_loai_cong_van: Optional[str] = None
    excel_issue_date_iso: Optional[str] = None  # YYYY-MM-DD
    excel_deadline_months: Optional[int] = None
    excel_so_don: Optional[str] = None
    excel_nhan_hieu: Optional[str] = None
    excel_loi: Optional[str] = None
    excel_is_scan: bool = False
    excel_highlight_red: bool = False


class DedupManager:
    """
    Manages deduplication state for a single daily folder.
    Loads existing records on construction; persists on register().
    """

    def __init__(self, daily_folder: Path):
        self._folder = daily_folder
        # _processed.json lives exclusively in ~/.tool_mail_cong_van/<date>/
        self._file = get_tool_export_folder(daily_folder.name) / _PROCESSED_FILE
        # Keep the actual output folder to detect deleted files
        self._output_folder = daily_folder
        self._records: Dict[str, DedupRecord] = {}   # keyed by message_id
        self._tech_keys: Set[str] = set()            # message_id + internet_message_id
        self._business_keys: Set[str] = set()        # downloaded filenames
        self._url_keys: Set[str] = set()             # portal URLs
        self._id_by_tech_key: Dict[str, str] = {}    # tech_key → message_id
        self._id_by_bkey: Dict[str, str] = {}        # filename → message_id
        self._id_by_url: Dict[str, str] = {}         # portal_url → message_id
        self._load()

    # ── Public ─────────────────────────────────────────────────────────────

    def is_duplicate(
        self,
        message_id: str,
        date_folder: str,
        so_don: Optional[str] = None,
        attachment_filenames: Optional[List[str]] = None,
        portal_url: Optional[str] = None,
    ) -> DupCheckResult:
        """
        Check whether this email was already processed in this daily folder.

        Returns DupCheckResult:
          is_dup=True,  needs_redownload=False  → skip (already processed, files OK)
          is_dup=True,  needs_redownload=True   → re-download files, skip Excel write
          is_dup=False                          → new email, full processing
        """
        matched_rec: Optional[DedupRecord] = None
        reason = ""

        # 1. Portal URL — primary business key (same link = same document)
        if portal_url and portal_url in self._url_keys:
            matched_rec = self._records.get(self._id_by_url.get(portal_url, ""))
            reason = f"portal URL: {portal_url}"

        # 2. Graph message id — technical fallback
        if matched_rec is None and message_id in self._tech_keys:
            matched_rec = self._records.get(message_id)
            reason = f"message_id: {message_id[:20]}…"

        # 4. Downloaded filename — post-download safety net
        if matched_rec is None:
            for fn in (attachment_filenames or []):
                if fn in self._business_keys:
                    matched_rec = self._records.get(self._id_by_bkey.get(fn, ""))
                    reason = f"filename: {fn}"
                    break

        if matched_rec is None:
            return DupCheckResult(is_dup=False)

        # ── File-existence check ───────────────────────────────────────────
        # If any previously downloaded file is missing on disk, signal
        # needs_redownload so the caller re-downloads but skips Excel write.
        stored_files = matched_rec.attachment_filenames or []
        if stored_files:
            missing = [
                f for f in stored_files
                if not (self._output_folder / f).exists()
            ]
            if missing:
                logger.info(
                    "Dedup match (%s) nhưng %d/%d file bị thiếu tại %s → tải lại. "
                    "URL đã lưu: %s",
                    reason, len(missing), len(stored_files),
                    self._output_folder,
                    matched_rec.download_url or "(không có)",
                )
                return DupCheckResult(
                    is_dup=True,
                    reason=reason,
                    needs_redownload=True,
                    download_url=matched_rec.download_url,
                )

        return DupCheckResult(is_dup=True, reason=reason)

    def register(
        self,
        message_id: str,
        date_folder: str,
        so_don: Optional[str] = None,
        attachment_filenames: Optional[List[str]] = None,
        download_url: Optional[str] = None,
        run_status: str = "OK",
        # Excel row snapshot
        excel_seq: Optional[int] = None,
        excel_recv_date: Optional[str] = None,
        excel_so_cong_van_num: Optional[str] = None,
        excel_loai_cong_van: Optional[str] = None,
        excel_issue_date_iso: Optional[str] = None,
        excel_deadline_months: Optional[int] = None,
        excel_so_don: Optional[str] = None,
        excel_nhan_hieu: Optional[str] = None,
        excel_loi: Optional[str] = None,
        excel_is_scan: bool = False,
        excel_highlight_red: bool = False,
    ) -> DedupRecord:
        """
        Record this email as processed and persist to _processed.json.
        Must be called after a successful write to Excel.
        """
        rec = DedupRecord(
            message_id=message_id,
            internet_message_id=None,
            date_folder=date_folder,
            so_don=so_don,
            attachment_filenames=attachment_filenames or [],
            download_url=download_url,
            run_status=run_status,
            excel_seq=excel_seq,
            excel_recv_date=excel_recv_date,
            excel_so_cong_van_num=excel_so_cong_van_num,
            excel_loai_cong_van=excel_loai_cong_van,
            excel_issue_date_iso=excel_issue_date_iso,
            excel_deadline_months=excel_deadline_months,
            excel_so_don=excel_so_don,
            excel_nhan_hieu=excel_nhan_hieu,
            excel_loi=excel_loi,
            excel_is_scan=excel_is_scan,
            excel_highlight_red=excel_highlight_red,
        )
        self._index(rec)
        self._save()
        return rec

    def count(self) -> int:
        return len(self._records)

    def rebuild_excel(self, writer: "ExcelWriter") -> None:
        """Delete and rebuild the entire Excel from stored record snapshots.

        Called when any file was missing and re-downloaded. All records for the
        day are re-written in seq order so the Excel stays consistent.
        Records without an excel_seq snapshot are silently skipped.
        """
        from datetime import date as _date
        # Delete old Excel so we start fresh
        if writer.excel_path.exists():
            writer.excel_path.unlink()

        recs = sorted(
            (r for r in self._records.values() if r.excel_seq is not None),
            key=lambda r: r.excel_seq,
        )
        if not recs:
            return

        # Write date separator row once, before first data row
        first = recs[0]
        if first.excel_recv_date:
            writer.append_date_row(first.excel_recv_date)

        for rec in recs:
            issue_date = None
            if rec.excel_issue_date_iso:
                try:
                    issue_date = _date.fromisoformat(rec.excel_issue_date_iso)
                except ValueError:
                    pass
            row = {
                "Ngày nhận công văn": rec.excel_seq,
                "Số công văn":        rec.excel_so_cong_van_num or "",
                "Loại công văn":      rec.excel_loai_cong_van or "",
                "Ngày issue công văn": issue_date,
                "Số tháng deadline":  rec.excel_deadline_months,
                "Số đơn":             rec.excel_so_don or "",
                "Loại hình đơn":      "",
                "Nội dung công văn":  rec.excel_nhan_hieu or "",
            }
            if rec.excel_loi:
                row["Lỗi"] = rec.excel_loi
            writer.append_data_row(
                row,
                highlight_red=rec.excel_highlight_red,
                highlight_yellow=rec.excel_is_scan,
            )
            writer.append_meta_row({
                "message_id":           rec.message_id,
                "internet_message_id":  rec.internet_message_id or "",
                "date_folder":          rec.date_folder,
                "so_don":               rec.so_don or "",
                "attachment_filenames": "; ".join(rec.attachment_filenames),
                "processed_at":         rec.processed_at,
                "run_status":           rec.run_status,
            })
        logger.info(
            "Rebuilt Excel with %d record(s) → %s", len(recs), writer.excel_path.name
        )

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
                    download_url=r.get("download_url"),
                    processed_at=r.get("processed_at", ""),
                    run_status=r.get("run_status", "OK"),
                    excel_seq=r.get("excel_seq"),
                    excel_recv_date=r.get("excel_recv_date"),
                    excel_so_cong_van_num=r.get("excel_so_cong_van_num"),
                    excel_loai_cong_van=r.get("excel_loai_cong_van"),
                    excel_issue_date_iso=r.get("excel_issue_date_iso"),
                    excel_deadline_months=r.get("excel_deadline_months"),
                    excel_so_don=r.get("excel_so_don"),
                    excel_nhan_hieu=r.get("excel_nhan_hieu"),
                    excel_loi=r.get("excel_loi"),
                    excel_is_scan=r.get("excel_is_scan", False),
                    excel_highlight_red=r.get("excel_highlight_red", False),
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
        self._id_by_tech_key[rec.message_id] = rec.message_id
        for fn in rec.attachment_filenames:
            self._business_keys.add(fn)
            self._id_by_bkey[fn] = rec.message_id
        if rec.download_url:
            self._url_keys.add(rec.download_url)
            self._id_by_url[rec.download_url] = rec.message_id

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

