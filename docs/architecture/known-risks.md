# Known Risks — Công Văn Processor

> Ranked list of fragile areas. Read before modifying any of these.
> Updated: 2026-04-15

---

## 🔴 Critical Risks

### RISK-001: Excel File Locked by User
- **Location:** `src/excel/writer.py:ExcelWriter._save()`
- **Risk:** If the user has `SO CONG VAN DEN-LIENDO.xlsx` open in Excel when the scan runs, `ExcelLockedError` is raised. In GUI mode, a dialog appears. In headless/scheduled mode, the email IS processed and parsed but the Excel row is NOT written, and dedup is NOT registered — so the email may be processed again on the next run (not a duplicate skip, because it was never registered).
- **Mitigation:** GUI shows dialog allowing user to close Excel and retry (1 retry). Headless mode has no mitigation beyond the error log. Pre-scan check in `_do_scan()` uses `_find_locked_excel_files()` to warn before starting.
- **⚠ Silent failure path:** If the second attempt also fails, the exception propagates to `_process_one()`, which catches it as a generic error and increments `error_count` — but the email is not registered in dedup. **Next run will reprocess it.**

### RISK-002: Wrong Date Folder Due to UTC/Local Time Mismatch
- **Location:** `src/folder/routing.py:get_date_folder_name()`
- **Risk:** Microsoft Graph returns `receivedDateTime` in UTC. An email received at 23:30 UTC on April 13 is 06:30 local time on April 14 (UTC+7). If UTC→local conversion is broken, emails land in the wrong day folder and the Excel date column is wrong.
- **Mitigation:** `to_local()` uses `astimezone(tz=None)` which attaches the system local timezone. Works correctly if the Windows timezone is set correctly.
- **⚠ Do NOT** use `datetime.now()` for folder routing under any circumstances.

### RISK-003: Portal Page Structure Changes
- **Location:** `src/portal/browser_downloader.py:_click_download_button()`
- **Risk:** The IP Vietnam portal (`ipvietnam.gov.vn`) may change its HTML structure, button text, or URL format. If none of the configured `download_button_selectors` match, the download fails silently and the email is marked "Cần kiểm tra".
- **Mitigation:** `portal.download_button_selectors` is configurable in `config.json`. Set `portal.headless: false` to view the page for debugging.
- **Impact:** All emails requiring portal download will fail until selectors are updated.

### RISK-004: CLASSIFICATION_RULES Ordering
- **Location:** `src/parser/rules.py:CLASSIFICATION_RULES` (line 136)
- **Risk:** The "Từ chối hủy bỏ HLC" rule must come before "Cấp toàn bộ". Cancellation-rejection documents contain "đáp ứng các điều kiện bảo hộ" in their body (the phrase that triggers "Cấp toàn bộ") even though they are rejections. If order changes, they will be misclassified.
- **Mitigation:** Comment in the rules list explains this. Test in `tests/test_parser.py`.
- **⚠ Always run tests after modifying `CLASSIFICATION_RULES`.**

---

## 🟡 Medium Risks

### RISK-005: Dedup State Split Between Disk Locations
- **Location:** `src/dedup/manager.py`, `src/folder/routing.py`
- **Risk:** `_processed.json` lives in `~/.tool_mail_cong_van/<date>/` (always local). The Excel file and PDF documents live in the configured output folder. If the local `~/.tool_mail_cong_van/` is wiped, dedup records are lost and all previously processed emails will be re-processed.
- **Mitigation:** On re-process, duplicate rows will appear in Excel. Manual dedup needed.

### RISK-006: Playwright Chromium Not Installed
- **Location:** `src/portal/browser_downloader.py:download()`
- **Risk:** If `playwright install chromium` was not run, all portal downloads fail with an error message. The tool falls back to direct attachments (if enabled), but portal emails without attachments become "Cần kiểm tra".
- **Mitigation:** Error message is user-friendly. Added to `README.md` troubleshooting table.

### RISK-007: Multi-PDF Selection Heuristic
- **Location:** `src/processor/email_processor.py:_find_main_pdf()`
- **Risk:** When multiple PDFs are downloaded, the largest file is assumed to be the "main" document. This heuristic may be wrong if the main document is smaller than a supporting document.
- **Mitigation:** When `strict_single_attachment: true`, multi-file emails are marked "Cần kiểm tra". User can review manually.

### RISK-008: Token Cache on Shared Machines
- **Location:** `src/auth/graph_auth.py`
- **Risk:** Token cache is stored at `~/.tool_mail_cong_van/token_cache.bin` in the user's home directory. If multiple Windows users share the same machine profile, tokens are separate (correct). But if the tool is deployed as a system service running as SYSTEM, `Path.home()` may not point to the expected user directory.
- **Mitigation:** Intended for personal desktop use only.

### RISK-009: Output Folder Unavailable
- **Location:** `config.json:output.root_folder`
- **Risk:** The configured output folder may be missing, unavailable, or not writable.
- **Mitigation:** `get_daily_folder()` catches `OSError` and falls back to `fallback_output_folder` or `~/Desktop/CongVanExport`.

### RISK-010: PyInstaller + Playwright Bundling
- **Location:** `build.bat`
- **Risk:** `playwright install chromium` installs Chromium in `%LOCALAPPDATA%\ms-playwright\`. PyInstaller bundles Python code but NOT Chromium. The standalone `.exe` requires Chromium to be separately present on the target machine.
- **Mitigation:** README documents this. `build.bat` could copy the `ms-playwright` folder but currently does not.

---

## 🟢 Low Risks

### RISK-011: Large Email Batches
- **Location:** `src/mail/reader.py:get_messages()`
- **Risk:** `page_size: 50` fetches up to 50 emails per page. For large date ranges, many emails may be fetched. Processing is sequential; a long run may hit token expiry (~1 hour by default for MSAL).
- **Mitigation:** MSAL auto-refreshes tokens. If refresh fails, `GraphClient` raises `PermissionError` on HTTP 401.

### RISK-012: PDF Text Extraction Failure
- **Location:** `src/parser/rules.py:extract_text_from_pdf()`
- **Risk:** Some PDFs are scanned images (no embedded text). PyMuPDF returns empty string. Parsing falls back to email body preview only, which may be truncated at 255 chars (Graph `bodyPreview`).
- **Mitigation:** Warning logged. Fields that couldn't be extracted are `None`. Row is written with "Cần kiểm tra" status and note.

### RISK-013: Vietnamese Text Normalization
- **Location:** `src/parser/rules.py:normalize_text()`, `src/mail/reader.py:_norm()`
- **Risk:** Vietnamese text may arrive as NFD (decomposed) or NFC (composed) Unicode. Regex matching may fail if normalization is inconsistent.
- **Mitigation:** `normalize_text()` always applies `unicodedata.normalize("NFC", text)` before any regex. `_norm()` also applies NFC for folder name comparison.

### RISK-014: Auto-scan Double-Fire on App Launch
- **Location:** `src/gui/app.py:_start_scheduler()`
- **Risk:** If the app is launched exactly at a scheduled hour (e.g., 08:00), the scheduler could immediately trigger a scan before the user is ready.
- **Mitigation:** `_start_scheduler()` checks if app is launched within the first 2 minutes of a scheduled slot and marks it as already fired (`_last_auto_scan_slot = current_key`).

### RISK-015: Excel File Corruption
- **Location:** `src/excel/writer.py:_load_or_create()`
- **Risk:** If the Excel file is corrupted (e.g., partial write during power outage), `openpyxl.load_workbook()` raises `IOError`. The tool stops processing all emails for that day.
- **Mitigation:** Error message suggests renaming/deleting the file to start fresh. No automatic recovery.
