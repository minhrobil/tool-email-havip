"""
EmailProcessor — main orchestrator for the Công Văn processing pipeline.

Updated pipeline per email:
  1.  Determine daily folder from receivedDateTime
  2.  Pre-dedup check (technical key only, before any I/O)
  3a. Extract portal URL from email body HTML/text
  3b. If URL found → use Playwright BrowserDownloader to fetch files
  3c. If URL not found AND fallback enabled → try email direct attachments
  3d. If neither → mark as "Cần kiểm tra"
  4.  Parse document (email body preview + main PDF)
  5.  Full dedup check (business keys now available)
  6.  Write to Excel (DATA row + META row)
  7.  Register in dedup manager
  8.  Append to _run.log
"""
from __future__ import annotations

import logging
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from ..auth.graph_auth import GraphAuth
from ..config import AppConfig
from ..dedup.manager import DedupManager
from ..excel.writer import ExcelLockedError, ExcelWriter, format_date
from ..folder.routing import get_daily_folder, get_date_folder_name
from ..graph.client import GraphClient
from ..mail.downloader import AttachmentDownloader
from ..mail.reader import MailMessage, MailReader
from ..parser.rules import ParsedDocument, parse_document
from ..portal.browser_downloader import BrowserDownloader
from ..portal.url_extractor import extract_first_portal_url, extract_portal_access_code

logger = logging.getLogger(__name__)

ProgressFn = Optional[Callable[..., None]]
# Called as: progress(current_idx, total, message, stats_dict)
# stats_dict keys: total, success, review, dup, error
# For non-email steps (auth, folder search): progress(0, 0, message, stats_dict)

_STATUS_OK = "OK"
_STATUS_REVIEW = "Cần kiểm tra"


class ScanCancelledError(Exception):
    """Raised when the user explicitly cancels the scan (e.g. via the Excel-locked dialog)."""


# ── Result dataclass ───────────────────────────────────────────────────────

@dataclass
class ProcessResult:
    success_count: int = 0
    scan_count: int = 0         # emails with scan/image PDF (OCR failed or partial)
    duplicate_count: int = 0
    review_count: int = 0       # kept for summary text
    error_count: int = 0
    file_error_count: int = 0   # emails where file download/acquisition failed
    missing_data_count: int = 0 # emails with missing required fields (red rows in Excel)
    fallback_count: int = 0      # emails saved to Desktop fallback (network was down)
    total_emails: int = 0
    errors: List[str] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None

    def summary(self) -> str:
        duration = ""
        if self.end_time:
            secs = (self.end_time - self.start_time).total_seconds()
            duration = f" ({secs:.1f}s)"
        fallback_note = f" | {self.fallback_count} dùng Desktop" if self.fallback_count else ""
        file_err_note = f" | {self.file_error_count} lỗi tải file" if self.file_error_count else ""
        missing_note  = f" | {self.missing_data_count} thiếu data" if self.missing_data_count else ""
        scan_note     = f" | {self.scan_count} file scan (cần kiểm tra)" if self.scan_count else ""
        return (
            f"Hoàn thành{duration}: "
            f"{self.success_count} thành công | "
            f"{self.duplicate_count} bỏ qua (trùng)"
            f"{scan_note}{file_err_note}{missing_note} | "
            f"{self.error_count} lỗi{fallback_note}  /  tổng {self.total_emails} email"
        )


# ── EmailProcessor ─────────────────────────────────────────────────────────

class EmailProcessor:
    """Orchestrates the full email processing pipeline."""

    def __init__(self, config: AppConfig, auth: GraphAuth):
        self._cfg = config
        self._auth = auth
        self._output_folder_override: Optional[str] = None   # set by run()
        self._on_excel_locked: Optional[Callable] = None     # set by run()
        # Serialises Excel writes + dedup registrations so parallel downloads are safe
        self._write_lock = threading.Lock()
    def run(
        self,
        progress: ProgressFn = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        output_folder_override: Optional[str] = None,
        on_excel_locked: Optional[Callable] = None,
    ) -> ProcessResult:
        """
        Run the full pipeline.

        date_from / date_to : optional local datetime bounds — applied as an OData
            $filter on receivedDateTime so only emails in the given window are fetched.
        output_folder_override : if set, overrides config.output.root_folder as the
            root export directory (date sub-folders are still created inside it).
        on_excel_locked : optional callback(excel_path: Path) -> bool called when the
            Excel file is locked.  Return True to close Excel and retry, False to cancel
            the scan entirely.  If not set, the error is recorded and processing continues.
        """
        self._output_folder_override = output_folder_override
        self._on_excel_locked = on_excel_locked
        result = ProcessResult()

        def _stats() -> dict:
            return {
                "total":        result.total_emails,
                "success":      result.success_count,
                "file_err":     result.file_error_count,
                "scan":         result.scan_count,
                "missing_data": result.missing_data_count,
                "dup":          result.duplicate_count,
                "error":        result.error_count,
            }

        def log(msg: str, cur: int = 0, tot: int = 0) -> None:
            logger.info(msg)
            if progress:
                progress(cur, tot, msg, _stats())

        messages, att_downloader, browser_dl, error = self._setup(
            result, log, date_from=date_from, date_to=date_to
        )
        if error:
            result.end_time = datetime.now()
            return result

        result.total_emails = len(messages)
        log(f"Tìm thấy {len(messages)} email.")

        total = len(messages)
        parallel = self._cfg.portal.parallel_downloads

        def _run_one(idx: int, msg: "MailMessage") -> None:
            log(f"Đang xử lý {idx}/{total}: {msg.subject}", idx, total)
            self._process_one(msg, att_downloader, browser_dl, result, log)

        with ThreadPoolExecutor(max_workers=parallel) as pool:
            futures = {
                pool.submit(_run_one, idx, msg): (idx, msg)
                for idx, msg in enumerate(messages, start=1)
            }
            for fut in as_completed(futures):
                idx, msg = futures[fut]
                try:
                    fut.result()
                except ScanCancelledError:
                    for f in futures:
                        f.cancel()
                    log("⛔ Quét bị hủy bởi người dùng.")
                    result.end_time = datetime.now()
                    return result
                except Exception as exc:
                    err = f"Lỗi xử lý email '{msg.subject[:50]}': {exc}"
                    logger.error(err)
                    logger.debug(traceback.format_exc())
                    with self._write_lock:
                        result.errors.append(err)
                        result.error_count += 1

        result.end_time = datetime.now()
        log(result.summary())
        return result

    def _setup(
        self,
        result: ProcessResult,
        log: Callable[[str], None],
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ):
        """
        Authenticate, build clients, find folder, fetch messages.
        Returns (messages, attachment_downloader, browser_downloader, had_error).
        """
        log("Đang xác thực với Microsoft 365...")

        def _auth_tick(remaining: int) -> None:
            mins = remaining // 60
            secs = remaining % 60
            log(f"Đang chờ đăng nhập trình duyệt…  {mins}:{secs:02d}  (đóng trình duyệt để hủy)")

        token = self._auth.get_token(on_tick=_auth_tick)
        # AuthRequiredError (account blocked / token revoked) is intentionally
        # NOT caught here — it propagates to the GUI which will show the login screen.

        client = GraphClient(token)
        reader = MailReader(client, page_size=self._cfg.mail.page_size)
        att_downloader = AttachmentDownloader(client)
        browser_dl = BrowserDownloader(
            button_selectors=self._cfg.portal.download_button_selectors,
            page_load_timeout_ms=self._cfg.portal.page_load_timeout_ms,
            wait_after_click_ms=self._cfg.portal.wait_after_click_ms,
            headless=self._cfg.portal.headless,
        )

        sender = self._cfg.mail.sender_email
        log(f"Đang tìm email từ '{sender}' trong hộp thư đến...")
        messages = reader.get_messages_by_sender(
            sender,
            received_after=date_from,
            received_before=date_to,
        )
        return messages, att_downloader, browser_dl, False

    # ── Per-message pipeline ───────────────────────────────────────────────

    def _process_one(
        self,
        msg: MailMessage,
        att_downloader: AttachmentDownloader,
        browser_dl: BrowserDownloader,
        result: ProcessResult,
        log: Callable[[str], None],
    ) -> None:
        cfg = self._cfg
        root = self._output_folder_override or cfg.output.root_folder
        daily_folder, used_fallback = get_daily_folder(
            msg.received_datetime,
            root,
            cfg.output.date_folder_format,
            cfg.output.fallback_output_folder,
        )
        if used_fallback:
            log(f"  ⚠ Thư mục output không khả dụng → lưu vào Desktop: {daily_folder}")
        folder_name = get_date_folder_name(msg.received_datetime, cfg.output.date_folder_format)

        # ── Pre-dedup: quick technical check before expensive download ──────
        # (runs under lock so duplicate_count stays thread-safe)
        with self._write_lock:
            dedup = DedupManager(daily_folder)
            skip, _redownload = self._check_dup(dedup, msg, folder_name, None, None, "kỹ thuật", log, result)
            if skip:
                return

        # ── PARALLEL PHASE: portal download + PDF parse (no lock) ──────────
        att_filenames, downloaded_paths, notes, status, portal_url = self._acquire_files(
            msg, att_downloader, browser_dl, daily_folder, cfg, log
        )
        file_had_error = status == _STATUS_REVIEW

        parsed = parse_document(
            text=msg.body_preview, pdf_path=_find_main_pdf(downloaded_paths)
        )
        if not parsed.so_don and not parsed.so_cong_van:
            notes.append("Không parse được số đơn / số công văn từ nội dung")

        # ── SERIAL PHASE: dedup + Excel write (exclusive lock) ──────────────
        with self._write_lock:
            # Reload dedup so we see any registrations made by parallel threads
            dedup = DedupManager(daily_folder)
            if not _redownload:
                skip2, _redownload2 = self._check_dup(
                    dedup, msg, folder_name, parsed.so_don, att_filenames, "nghiệp vụ", log, result
                )
                if skip2:
                    return
                if _redownload2:
                    _redownload = True

            if file_had_error:
                result.file_error_count += 1

            if _redownload:
                # Files were missing — re-downloaded successfully.
                # Update dedup record with fresh parse data, then rebuild entire Excel.
                log(f"  ↳ ↻ Đã tải lại {len(att_filenames)} file → gen lại Excel toàn bộ")

                # Build Lỗi string same way as _write_results
                missing_fields: List[str] = []
                if not parsed.so_cong_van_num:
                    missing_fields.append("Thiếu số công văn")
                if not parsed.issue_date:
                    missing_fields.append("Thiếu ngày issue công văn")
                if parsed.deadline_months is None and parsed.loai_cong_van not in ("TB0DL", "CNĐ"):
                    missing_fields.append("Thiếu số tháng deadline")
                if not parsed.loai_cong_van:
                    missing_fields.append("Không khớp rule phân loại")
                loi_str: Optional[str] = None
                if missing_fields:
                    loi_str = "\n".join(f"{i}: {e}" for i, e in enumerate(missing_fields, start=1))
                if parsed.is_scan:
                    loi_str = ("File scan, please check again\n" + (loi_str or "")).strip()
                highlight_red = bool(missing_fields)

                # Look up original seq from existing dedup record
                existing_rec = dedup._records.get(msg.id)
                redownload_seq = existing_rec.excel_seq if existing_rec else None

                dedup.register(
                    message_id=msg.id,
                    internet_message_id=msg.internet_message_id,
                    date_folder=folder_name,
                    so_don=parsed.so_don,
                    attachment_filenames=att_filenames,
                    download_url=portal_url,
                    run_status=status,
                    excel_seq=redownload_seq,
                    excel_recv_date=existing_rec.excel_recv_date if existing_rec else None,
                    excel_so_cong_van_num=parsed.so_cong_van_num,
                    excel_loai_cong_van=parsed.loai_cong_van,
                    excel_issue_date_iso=parsed.issue_date.isoformat() if parsed.issue_date else None,
                    excel_deadline_months=parsed.deadline_months,
                    excel_so_don=parsed.so_don,
                    excel_nhan_hieu=parsed.nhan_hieu,
                    excel_loi=loi_str,
                    excel_is_scan=parsed.is_scan,
                    excel_highlight_red=highlight_red,
                )

                # Rebuild entire Excel from all records
                writer = ExcelWriter(daily_folder, cfg.output.excel_filename)
                for _attempt in range(2):
                    try:
                        dedup.rebuild_excel(writer)
                        break
                    except ExcelLockedError as exc:
                        if _attempt == 0 and self._on_excel_locked:
                            should_retry = self._on_excel_locked(exc.excel_path)
                            if not should_retry:
                                raise ScanCancelledError("Người dùng hủy quét do file Excel đang mở") from exc
                            writer = ExcelWriter(daily_folder, cfg.output.excel_filename)
                        else:
                            raise

                self._record_outcome(status, notes, parsed, log, result, used_fallback)
                return

            # Get per-day sequence number, rename files, then write
            writer = ExcelWriter(daily_folder, cfg.output.excel_filename)
            seq = writer.next_sequence_number()
            if downloaded_paths:
                downloaded_paths, att_filenames = _rename_downloaded_files(
                    downloaded_paths, seq
                )

            # Write with optional retry when Excel is locked
            for _attempt in range(2):
                try:
                    self._write_results(msg, parsed, daily_folder, folder_name, att_filenames, status, notes, dedup, writer=writer, seq=seq, result=result, portal_url=portal_url)
                    break  # success
                except ExcelLockedError as exc:
                    if _attempt == 0 and self._on_excel_locked:
                        should_retry = self._on_excel_locked(exc.excel_path)
                        if not should_retry:
                            raise ScanCancelledError("Người dùng hủy quét do file Excel đang mở") from exc
                        writer = ExcelWriter(daily_folder, cfg.output.excel_filename)
                    else:
                        raise

            _log_run_summary(msg, parsed, status, notes)
            self._record_outcome(status, notes, parsed, log, result, used_fallback)

    def _check_dup(
        self,
        dedup: DedupManager,
        msg: MailMessage,
        folder_name: str,
        so_don: Optional[str],
        att_filenames: Optional[List[str]],
        label: str,
        log: Callable[[str], None],
        result: ProcessResult,
    ) -> Tuple[bool, bool]:
        """Returns (skip, needs_redownload).

        skip=True, needs_redownload=False  → email already processed, skip entirely
        skip=False, needs_redownload=True  → email processed but files missing, re-download only
        skip=False, needs_redownload=False → new email, process fully
        """
        dup = dedup.is_duplicate(
            message_id=msg.id,
            internet_message_id=msg.internet_message_id,
            date_folder=folder_name,
            so_don=so_don,
            attachment_filenames=att_filenames,
        )
        if dup.is_dup and not dup.needs_redownload:
            log(f"  ↳ Bỏ qua (trùng {label}): {dup.reason}")
            result.duplicate_count += 1
            return True, False
        if dup.needs_redownload:
            log(f"  ↳ File bị xóa ({label}): {dup.reason} — sẽ tải lại")
            return False, True
        return False, False

    @staticmethod
    def _record_outcome(
        status: str,
        notes: List[str],
        parsed: "ParsedDocument",
        log: Callable[[str], None],
        result: ProcessResult,
        used_fallback: bool = False,
    ) -> None:
        if used_fallback:
            result.fallback_count += 1
        if status == _STATUS_REVIEW:
            log(f"  ↳ ⚠ Cần kiểm tra: {'; '.join(notes)}")
            result.review_count += 1
        elif parsed.is_scan:
            log(f"  ↳ ⚠ File scan (OCR)  số đơn={parsed.so_don or '?'}  loại={parsed.loai_cong_van or '?'}")
            result.scan_count += 1
        else:
            log(f"  ↳ ✓ OK  số đơn={parsed.so_don or '?'}  loại={parsed.loai_cong_van or '?'}")
            result.success_count += 1


    def _acquire_files(
        self,
        msg: MailMessage,
        att_downloader: AttachmentDownloader,
        browser_dl: BrowserDownloader,
        daily_folder: Path,
        cfg: AppConfig,
        log: Callable,
    ) -> Tuple[List[str], List[Path], List[str], str, Optional[str]]:
        """
        Acquire document files for an email using the portal-first strategy.

        Priority:
          1. Extract portal URL from email body → browser download via Playwright
          2. If no portal URL found AND fallback enabled → direct email attachments
          3. Neither available → empty list, mark as Cần kiểm tra

        Returns:
            (att_filenames, downloaded_paths, notes, status, portal_url)
            portal_url is the URL used for download (None if direct attachments or no URL found)
        """
        notes: List[str] = []
        status = _STATUS_OK

        # ── Strategy 1: Portal URL in email body ───────────────────────────
        portal_url = extract_first_portal_url(
            body_html=msg.body_html,
            body_text=msg.body_text or msg.body_preview,
            url_patterns=cfg.portal.url_patterns,
        )
        access_code = extract_portal_access_code(
            body_text=msg.body_text or msg.body_preview,
            body_html=msg.body_html,
        )
        if access_code:
            logger.debug("Access code extracted: %s…", access_code[:14])

        if portal_url:
            log(f"  ↳ Link portal: {portal_url[:80]}")
            portal_result = browser_dl.download(portal_url, daily_folder, access_code=access_code)
            notes.extend(portal_result.notes)

            if portal_result.success:
                downloaded_paths = portal_result.downloaded_paths
                att_filenames = [p.name for p in downloaded_paths]
                file_count = len(downloaded_paths)
                log(f"  ↳ Tải được {file_count} file từ portal")
                if file_count > 1:
                    notes.append(f"{file_count} files từ portal — cần xác nhận file chính")
                    if cfg.processing.strict_single_attachment:
                        status = _STATUS_REVIEW
                return att_filenames, downloaded_paths, notes, status, portal_url

            # Portal download failed
            notes.append(f"Tải từ portal thất bại: {portal_url}")
            log(f"  ↳ ⚠ Tải portal thất bại — thử fallback...")

        else:
            notes.append("Không tìm thấy link portal trong email body")
            log("  ↳ Không có link portal trong email")

        # ── Strategy 2: Direct email attachments (fallback) ────────────────
        if not cfg.portal.fallback_to_attachments:
            status = _STATUS_REVIEW
            return [], [], notes, status, portal_url

        if msg.has_attachments:
            attachments = att_downloader.list_attachments(msg.id)
            downloaded_paths = att_downloader.download_all(msg.id, daily_folder, attachments)
            att_count = len(attachments)
            att_filenames = [p.name for p in downloaded_paths]

            if att_count == 0:
                notes.append("Email không có attachment (fallback)")
                status = _STATUS_REVIEW
            elif att_count > 1:
                notes.append(f"{att_count} attachments (fallback) — cần xác nhận file chính")
                if cfg.processing.strict_single_attachment:
                    status = _STATUS_REVIEW
            else:
                notes.append("Dùng attachment trực tiếp (không có link portal)")

            return att_filenames, downloaded_paths, notes, status, portal_url

        # ── No files available ─────────────────────────────────────────────
        notes.append("Không tải được file (không có portal link và không có attachment)")
        status = _STATUS_REVIEW
        return [], [], notes, status, portal_url

    def _write_results(
        self,
        msg: MailMessage,
        parsed: "ParsedDocument",
        daily_folder: Path,
        folder_name: str,
        att_filenames: List[str],
        status: str,
        notes: List[str],
        dedup: DedupManager,
        writer: Optional[ExcelWriter] = None,
        seq: Optional[int] = None,
        result: Optional["ProcessResult"] = None,
        portal_url: Optional[str] = None,
    ) -> None:
        """Write Excel rows and register dedup record.

        Row structure:
          - When seq == 1 (first document of the day): first write a date separator
            row with only col A = received date; then write the data row.
          - Data row fills only: A (seq), B (numeric cv), D (issue date MM/DD/YYYY),
            F (deadline date MM/DD/YYYY), I (nhãn hiệu name). All other cols blank.
        """
        if writer is None:
            writer = ExcelWriter(daily_folder, self._cfg.output.excel_filename)

        # Date from received_datetime (YYYY-MM-DD → DD/MM/YYYY)
        recv_dt = msg.received_datetime.split("T")[0]   # "YYYY-MM-DD"
        try:
            from datetime import datetime as _dt
            recv_date_str = _dt.strptime(recv_dt, "%Y-%m-%d").strftime("%d/%m/%Y")
        except ValueError:
            recv_date_str = recv_dt

        # Write date separator row on the first document of the day
        if seq == 1:
            writer.append_date_row(recv_date_str)

        def _fmt_mdY(d) -> str:
            """Format a date as MM/DD/YYYY (portal/Excel convention)."""
            if d is None:
                return ""
            from datetime import date as _date
            if isinstance(d, _date):
                return d.strftime("%m/%d/%Y")
            return str(d)

        row = {
            "Ngày nhận công văn":  seq,
            "Số công văn":         parsed.so_cong_van_num or "",
            "Loại công văn":       parsed.loai_cong_van or "",
            "Ngày issue công văn": parsed.issue_date,        # date object — EDATE formula requires this
            "Số tháng deadline":   parsed.deadline_months,   # col E; formula in col F uses =EDATE(D,E)
            # "Deadline trả lời Cục" intentionally omitted — master file has =IFERROR(EDATE(D,E),"0DL")
            "Số đơn":              parsed.so_don or "",
            "Loại hình đơn":       "",
            "Nội dung công văn":   parsed.nhan_hieu or "",
        }

        # Validate required fields — collect missing reasons
        missing: List[str] = []
        if not parsed.so_cong_van_num:
            missing.append("Thiếu số công văn")
        if not parsed.issue_date:
            missing.append("Thiếu ngày issue công văn")
        if parsed.deadline_months is None and parsed.loai_cong_van not in ("TB0DL", "CNĐ"):
            missing.append("Thiếu số tháng deadline")
        if not parsed.loai_cong_van:
            missing.append("Không khớp rule phân loại")

        # Only data-validation failures go into the Excel "Lỗi" column.
        # Technical pipeline notes (portal errors, download failures) stay in logs only.
        if missing:
            numbered = "\n".join(f"{i}: {e}" for i, e in enumerate(missing, start=1))
            row["Lỗi"] = numbered

        if parsed.is_scan:
            existing = row.get("Lỗi", "")
            row["Lỗi"] = ("File scan, please check again\n" + existing).strip() if existing else "File scan, please check again"

        highlight_red = bool(missing)
        if highlight_red and result is not None:
            result.missing_data_count += 1
        writer.append_data_row(row, highlight_red=highlight_red, highlight_yellow=parsed.is_scan)
        writer.append_meta_row({
            "message_id":           msg.id,
            "internet_message_id":  msg.internet_message_id or "",
            "date_folder":          folder_name,
            "so_don":               parsed.so_don or "",
            "attachment_filenames": "; ".join(att_filenames),
            "processed_at":         datetime.now().isoformat(timespec="seconds"),
            "run_status":           status,
        })
        dedup.register(
            message_id=msg.id,
            internet_message_id=msg.internet_message_id,
            date_folder=folder_name,
            so_don=parsed.so_don,
            attachment_filenames=att_filenames,
            download_url=portal_url,
            run_status=status,
            excel_seq=seq,
            excel_recv_date=recv_date_str,
            excel_so_cong_van_num=parsed.so_cong_van_num,
            excel_loai_cong_van=parsed.loai_cong_van,
            excel_issue_date_iso=parsed.issue_date.isoformat() if parsed.issue_date else None,
            excel_deadline_months=parsed.deadline_months,
            excel_so_don=parsed.so_don,
            excel_nhan_hieu=parsed.nhan_hieu,
            excel_loi=row.get("Lỗi"),
            excel_is_scan=parsed.is_scan,
            excel_highlight_red=highlight_red,
        )


# ── Module-level helpers ───────────────────────────────────────────────────

def _make_seq_filename(seq: int, stem: str, suffix: str) -> str:
    """
    Build the renamed filename: {seq}-{stem}{suffix}
    Example:  3-thongbao.pdf
    """
    return f"{seq}-{stem}{suffix}"


def _rename_downloaded_files(
    paths: List[Path],
    seq: int,
) -> Tuple[List[Path], List[str]]:
    """
    Rename each downloaded file to {seq}-{original_name}.
    Falls back to the original name on OS error.
    Returns (new_path_list, new_filename_list).
    """
    new_paths: List[Path] = []
    for path in paths:
        if not path.exists():
            new_paths.append(path)
            continue

        new_name = _make_seq_filename(seq, path.stem, path.suffix)
        new_path = path.parent / new_name

        # Avoid clobbering an unrelated file with the same target name
        counter = 1
        while new_path.exists() and new_path.resolve() != path.resolve():
            new_path = path.parent / f"{seq}-{path.stem}_{counter}{path.suffix}"
            counter += 1

        try:
            path.rename(new_path)
            new_paths.append(new_path)
            logger.debug("Renamed attachment: %s → %s", path.name, new_path.name)
        except OSError as exc:
            logger.warning("Cannot rename %s → %s: %s", path.name, new_path.name, exc)
            new_paths.append(path)

    return new_paths, [p.name for p in new_paths]


def _fail(result: ProcessResult, msg: str) -> None:
    """Record a fatal error into ProcessResult."""
    logger.error(msg)
    result.errors.append(msg)
    result.error_count += 1


def _find_main_pdf(paths: List[Path]) -> Optional[Path]:
    """
    Select the main PDF from a list of downloaded paths.
    Rules (deterministic):
      - 1 PDF found → use it
      - >1 PDFs found → use the largest one (most likely the full document)
      - 0 PDFs → return None
    """
    pdfs = [p for p in paths if p.suffix.lower() == ".pdf"]
    if not pdfs:
        return None
    if len(pdfs) == 1:
        return pdfs[0]
    return max(pdfs, key=lambda p: p.stat().st_size)


def _log_run_summary(
    msg: MailMessage,
    parsed: ParsedDocument,
    status: str,
    notes: List[str],
) -> None:
    """Log a per-email processing summary via the standard logger."""
    notes_str = "; ".join(notes) if notes else "-"
    logger.info(
        "  ↳ [%s] so_don=%s | so_cv=%s | notes=%s",
        status,
        parsed.so_don or "?",
        parsed.so_cong_van or "?",
        notes_str,
    )
