# Feature Map — Công Văn Processor

> Maps every feature to its code location. Updated: 2026-05-05.

---

## Feature Index

| Feature | Entry point | Key files |
|---|---|---|
| GUI application | `src/gui/app.py:run_gui()` | `CongVanApp` class |
| Headless/CLI mode | `src/main.py:_run_headless()` | `src/main.py`, `run_app.py` |
| Microsoft 365 OAuth | `src/auth/graph_auth.py` | `GraphAuth.get_token()`, `AuthRequiredError` |
| Email folder discovery | `src/mail/reader.py` | `MailReader.find_cong_van_folder()` |
| Email message retrieval | `src/mail/reader.py` | `MailReader.get_messages()` |
| Portal URL extraction | `src/portal/url_extractor.py` | `extract_first_portal_url()`, `extract_portal_access_code()` |
| Browser-based portal download | `src/portal/browser_downloader.py` | `BrowserDownloader.download()` |
| Direct attachment download | `src/mail/downloader.py` | `AttachmentDownloader.download_all()` |
| Vietnamese document parsing | `src/parser/rules.py` | `parse_document()` |
| Document classification | `src/parser/rules.py` | `classify_document()`, `CLASSIFICATION_RULES` |
| Deduplication | `src/dedup/manager.py` | `DedupManager` |
| Daily folder routing | `src/folder/routing.py` | `get_daily_folder()` |
| Excel export | `src/excel/writer.py` | `ExcelWriter` |
| File rename with sequence prefix | `src/processor/email_processor.py` | `_rename_downloaded_files()` |
| Auto-scan scheduler | `src/gui/app.py` | `_start_scheduler()`, `_scheduler_loop()`, `_do_auto_scan()` |
| Open export folder (cross-platform) | `src/gui/app.py` | `_open_folder_in_file_manager()` |
| Windows source launchers | `run.bat`, `run_headless.bat`, `setup_scheduler.bat` | source-tree helpers |
| Windows dist packaging | `packaging/windows/` | `run_headless.dist.bat`, `setup_scheduler.dist.bat` |
| GitHub Actions build + release | `.github/workflows/build.yml` | Windows build, artifact upload, GitHub Release |

---

## Feature Details

### 1. GUI Application (`src/gui/app.py`)

- **Class:** `CongVanApp(tk.Tk)`
- **Entry:** `run_gui()`
- **Screens:** login frame ↔ main frame
- **Main controls:**
  - Date range (`_from_date_var`, `_to_date_var`)
  - Mail folder override (`_mail_folder_var`)
  - Export folder chooser (`_export_folder_var`)
  - Auto-scan checkbox + frequency combobox
  - Activity log tab backed by `ScrolledText`
- **Cross-platform helper:** `_open_folder_in_file_manager()` uses `open` / `explorer` / `xdg-open`
- **Startup behavior:** preloads aggregate stats from `~/.tool_mail_cong_van/<date>/_processed.json`
- **Excel lock UX:** pre-scan dialog plus in-scan retry dialog; automatic close uses Windows `taskkill`

### 2. Headless / CLI Mode (`src/main.py`, `run_app.py`)

- `run_app.py` is the PyInstaller-friendly top-level launcher
- `src.main:main()` parses:
  - `--headless`
  - `--config`
  - `--log-file`
  - `--from-datetime`
  - `--to-datetime`
  - `--output-folder`
- `_run_headless()` requires a cached login (`auth.is_authenticated()`)
- Default headless export root is `~/Desktop/CongVanExport`

### 3. Authentication (`src/auth/graph_auth.py`)

- **Class:** `GraphAuth`
- **Cache path:** `~/.tool_mail_cong_van/token_cache.bin`
- **Flow:** silent token → interactive browser login fallback
- **Failure model:** fatal account/token problems raise `AuthRequiredError`
- **Special behavior:** `validate_authority=False` defers tenant discovery network work until login

### 4. Email Processing Pipeline (`src/processor/email_processor.py`)

- **Class:** `EmailProcessor`
- **Result type:** `ProcessResult`
- **Concurrency:** `ThreadPoolExecutor(max_workers=cfg.portal.parallel_downloads)`
- **Workbook lifecycle:** every scan deletes and regenerates each affected day's Excel; it never appends to a previous run
- **Per-email flow:**
  1. Resolve daily folder from `msg.received_datetime`
  2. Download and retain files with a per-email numeric prefix
  3. Parse body preview + main PDF
  4. Check duplicates after download; retain both files and mark the later Excel row with the original row number
  6. Get sequence number
  7. Rename files to `{seq}-{original_name}`
  8. Write DATA + META rows
  9. Register dedup record
  10. Update `ProcessResult`
- **Serialization rule:** only Excel write + dedup register are inside `_write_lock`

### 5. Portal Acquisition (`src/portal/`)

- **URL extraction:**
  - `_hrefs_from_html()`
  - `_bare_urls()` with `html.unescape()`
  - `extract_portal_access_code()`
  - fallback constructed URL: `https://thongbao.ipvietnam.gov.vn/tra-cuu-don/{code}`
- **Browser automation:**
  - `page.goto(..., timeout=30000)`
  - optional access-code form fill
  - bulk download button first
  - `a.file-item__title` fallback second

### 6. Document Parser (`src/parser/rules.py`)

- **Entry:** `parse_document(text, pdf_path)`
- **PDF parser:** PyMuPDF (`fitz`)
- **Extracted fields:** số công văn, số đơn, số yêu cầu, số GCN, issue date, deadline months/date, loại công văn, loại hình đơn, nội dung, nhãn hiệu
- **Classification rules:** currently **10** ordered rules in `CLASSIFICATION_RULES`
- **Deadline behavior:** month-based values win; day-based values are converted to rounded months

### 7. Dedup + Excel State (`src/dedup/manager.py`, `src/excel/writer.py`)

- **Dedup storage:** `~/.tool_mail_cong_van/<date>/_processed.json`
- **Key priority:** internetMessageId → Graph message id → `date_folder + so_don` → `date_folder + filename`
- **Excel sheets:** `DATA`, `META`
- **First row of day:** `append_date_row("DD/MM/YYYY")`
- **Business row currently fills:** sequence, numeric document number, issue date, deadline date, trademark name, optional `Lỗi`

### 8. Repo Scripts & Packaging

- **Windows source workflow:** `run.bat`, `run_headless.bat`, `setup_scheduler.bat`, `build.bat`
- **Dist helpers:** `packaging/windows/*.dist.bat` are copied into `dist\ToolXuLyMailCongVan\`
- **Config loading for dist:** `src/config.py:load_config()` checks `sys.frozen` and prefers `config.json` next to the `.exe`

### 9. GitHub Actions Build / Release (`.github/workflows/build.yml`)

- Triggered on push to `master` and manual dispatch
- Builds on `windows-latest`
- Injects `AZURE_CLIENT_ID` secret into `config.json`
- Installs Playwright Chromium before PyInstaller
- Uploads `dist\ToolXuLyMailCongVan\` as an artifact
- Creates a GitHub Release containing the `.exe`
