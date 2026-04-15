# Feature Map — Công Văn Processor

> Maps every feature to its code location. Updated: 2026-04-15.

---

## Feature Index

| Feature | Entry point | Key files |
|---|---|---|
| GUI application | `src/gui/app.py:run_gui()` | `CongVanApp` class |
| Headless/CLI mode | `src/main.py:_run_headless()` | `EmailProcessor.run()` |
| Microsoft 365 OAuth | `src/auth/graph_auth.py` | `GraphAuth.get_token()` |
| Email folder discovery | `src/mail/reader.py` | `MailReader.find_cong_van_folder()` |
| Email message retrieval | `src/mail/reader.py` | `MailReader.get_messages()` |
| Portal URL extraction | `src/portal/url_extractor.py` | `extract_first_portal_url()` |
| Browser-based download | `src/portal/browser_downloader.py` | `BrowserDownloader.download()` |
| Direct attachment download | `src/mail/downloader.py` | `AttachmentDownloader.download_all()` |
| Vietnamese document parsing | `src/parser/rules.py` | `parse_document()` |
| Document type classification | `src/parser/rules.py` | `classify_document()`, `CLASSIFICATION_RULES` |
| Deadline calculation | `src/parser/rules.py` | `calculate_deadline_date()` |
| Deduplication | `src/dedup/manager.py` | `DedupManager` |
| Daily folder routing | `src/folder/routing.py` | `get_daily_folder()` |
| Excel export | `src/excel/writer.py` | `ExcelWriter` |
| Auto-scan scheduler | `src/gui/app.py` | `_scheduler_loop()`, `_do_auto_scan()` |
| Excel-locked dialog | `src/gui/app.py` | `_ask_excel_locked()`, `_confirm_close_excel()` |
| Output folder fallback | `src/folder/routing.py` | `get_daily_folder()` fallback path |
| Run log / scan summary | `src/processor/email_processor.py` | `_log_run_summary()` (standard logging) |
| Task Scheduler setup | `setup_scheduler.bat` | Windows schtasks |

---

## Feature Details

### 1. GUI Application (`src/gui/app.py`)

- **Class:** `CongVanApp(tk.Tk)` — custom tab bar (Main tab / Activities tab)
- **Entry:** `run_gui()` at module bottom
- **Screens:** Login frame (`_build_login_frame()`) ↔ Main frame (`_build_main_frame()`)
- **Controls:**
  - Date range picker (`_from_date_var`, `_to_date_var`)
  - Mail folder name (`_mail_folder_var`)
  - Export folder (`_export_folder_var`)
  - Auto-scan checkbox + frequency combobox
  - "📥 Quét mail" scan button → `_do_scan()`
  - "📂 Mở folder export" button (shown after first export)
- **Dashboard:** stat cards — Thành công | Lỗi tải file | Thiếu data | Đã có | Lỗi
- **Progress:** `ttk.Progressbar` with `CongVan.Horizontal.TProgressbar` style
- **Thread model:** Scan runs in daemon thread; GUI updates via `self.after(0, callback)`
- **Startup:** pre-loads stats from `_processed.json`; stats accumulate across scans (no reset on new scan)
- **Scan logs:** written to `~/.tool_mail_cong_van/<date>/scan_<range>.log`; viewable in the Activities tab

### 2. Authentication (`src/auth/graph_auth.py`)

- **Class:** `GraphAuth`
- **Token cache:** `~/.tool_mail_cong_van/token_cache.bin` (MSAL `SerializableTokenCache`)
- **`validate_authority=False`** — avoids a network call at startup
- **Flow:**
  1. `get_token()` → tries silent (`acquire_token_silent`) → falls back to interactive
  2. `get_token_interactive_force()` → opens browser, 120s timeout, countdown via `on_tick` callback
- **`AuthRequiredError`** — raised when token is revoked or account is blocked; GUI catches and redirects to login screen
- **Headless check:** `is_authenticated()` → returns `False` if no cached accounts → headless mode exits

### 3. Email Pipeline (`src/processor/email_processor.py`)

- **Class:** `EmailProcessor`
- **Method:** `run(progress, date_from, date_to, output_folder_override, on_excel_locked)`
- **Returns:** `ProcessResult` with counts (success, duplicate, file_error_count, missing_data_count, error, fallback)
- **Concurrency:** `ThreadPoolExecutor(max_workers=cfg.portal.parallel_downloads)` — up to 5 emails processed simultaneously; `_write_lock` serialises the Excel write + dedup register phase
- **Per-email steps in `_process_one()`:**
  1. `get_daily_folder()` → resolve output path
  2. Pre-dedup (tech key only — before I/O)
  3. `_acquire_files()` → portal URL → browser download OR attachment fallback  *(runs concurrently)*
  4. `parse_document()` → extract metadata  *(runs concurrently)*
  5. `[acquire _write_lock]`
  6. Full dedup (business keys: so_don, filename)
  7. `ExcelWriter.next_sequence_number()` + file rename with sequence prefix
  8. `ExcelWriter.append_data_row()` + `append_meta_row()` (with Excel-locked retry)
  9. `DedupManager.register()`
  10. `[release _write_lock]`
  11. `_log_run_summary()` (standard logging)

### 4. Document Parser (`src/parser/rules.py`)

- **Entry:** `parse_document(text, pdf_path)` → `ParsedDocument`
- **PDF text extraction:** `extract_text_from_pdf(pdf_path)` using PyMuPDF (`fitz`)
- **Text normalization:** `normalize_text()` — NFC, collapse whitespace, unify line endings
- **Extracted fields:**
  - `so_cong_van`: regex `_RE_SO_CONG_VAN` → "53397/SHTT-NH.IP"
  - `so_don`: regex `_RE_SO_DON` → "4-2025-20619"
  - `so_yeu_cau`: regex `_RE_SO_YEU_CAU` → "CĐ4-2026-00098"
  - `so_gcn`: regex `_RE_SO_GCN` → GCNĐKNH number
  - `issue_date`: regex `_RE_ISSUE_DATE` → "ngày DD tháng MM năm YYYY"
  - `deadline_months`: months from `_RE_DEADLINE` or days from `_RE_DEADLINE_DAYS` ÷ 30
  - `loai_cong_van`: `CLASSIFICATION_RULES` → first match (11 rules)
  - `loai_hinh_don`: `LOAI_HINH_RULES` → 6 application types
  - `noi_dung_cong_van`: first "Về việc…" line or first long substantive paragraph
- **To add a classification rule:** append to `CLASSIFICATION_RULES` (first-match-wins — order matters!)

### 5. Deduplication (`src/dedup/manager.py`)

- **Class:** `DedupManager(daily_folder)`
- **Storage:** `~/.tool_mail_cong_van/<date_folder>/_processed.json`
- **Key hierarchy (priority order):**
  1. `internet_message_id` (RFC 2822 — globally unique)
  2. `message_id` (Graph internal)
  3. `date_folder + so_don`
  4. `date_folder + attachment_filename`
- **Usage pattern:** `is_duplicate()` before write → `register()` after write
- **Pre-check vs full-check:** Pre-check uses only tech keys (before acquiring files); full check uses business keys (after parsing)

### 6. Excel Writer (`src/excel/writer.py`)

- **Class:** `ExcelWriter(daily_folder, excel_filename)`
- **Sheets:** `DATA` (business rows), `META` (dedup metadata)
- **Column definitions:** `DATA_COLUMNS` (last column: "Lỗi" — numbered validation errors, e.g. `"1: Thiếu số công văn\n2: Thiếu nhãn hiệu"`), `META_COLUMNS` (7 cols)
- **Lock detection:** checks for `~$<filename>` Excel lock file before saving
- **Error:** `ExcelLockedError(PermissionError)` with `excel_path` attribute
- **Sequence number:** `next_sequence_number()` reads existing file to get STT for next row

### 7. Portal Download (`src/portal/`)

- **URL extraction** (`url_extractor.py`):
  - `_hrefs_from_html()` — parses `href="..."` from HTML
  - `_bare_urls()` — finds raw http(s) URLs in any text
  - `_filter_and_dedup()` — filters by `url_patterns` from config
- **Browser download** (`browser_downloader.py`):
  - Opens headless Chromium via Playwright sync API
  - Sets `accept_downloads=True` on context
  - **Strategy 1:** clicks "Tải tất cả" bulk button
  - **Strategy 2 (fallback):** clicks individual `.file-item__title` links
  - Only the *caller* adds notes to `PortalDownloadResult` — individual strategies do not
  - Captures all `page.on("download", ...)` events
  - Saves files with `dl.save_as()` BEFORE `browser.close()`
  - Returns `PortalDownloadResult`

### 8. Auto-scan Scheduler (`src/gui/app.py`)

- **Method:** `_scheduler_loop()` runs in daemon thread, checks every 30s
- **Fires when:** `auto_scan_var=True` AND `hour % freq_h == 0` AND `minute < 2` AND slot not already fired
- **Frequency options:** 1h, 2h, 4h, 6h, 8h, 12h, 24h
- **Slot key:** `(day_of_year, hour)` — prevents double-fire in same hour
- **Entry:** `_do_auto_scan()` → updates date vars → calls `_do_scan()`

### 9. Output Folder Fallback (`src/folder/routing.py`)

- `get_daily_folder()` tries primary `root_folder` (default `~/Desktop/CongVanExport`)
- On `OSError`: falls back to `fallback_output_folder` or `~/Desktop/CongVanExport`
- Returns `(path, used_fallback)` tuple
- `_processed.json` always goes to `~/.tool_mail_cong_van/` (always local)
