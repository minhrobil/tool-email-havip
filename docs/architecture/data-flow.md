# Data Flow — Công Văn Processor

> Traces the exact path data takes through the system.
> Updated: 2026-05-05

---

## Read Path (Email → Files → Excel)

```
Microsoft 365 Mailbox (folder name from config, default: "Công văn")
        │
        │  MSAL OAuth (token cache: ~/.tool_mail_cong_van/token_cache.bin)
        ▼
GraphClient.paginate("/me/mailFolders")
        │
        │  Find folder by name (case-insensitive, NFC-normalized, recursive)
        ▼
MailFolder.id
        │
GraphClient.paginate("/me/mailFolders/{id}/messages")
        │  $select: id, internetMessageId, subject, sender,
        │           receivedDateTime, hasAttachments, bodyPreview, body
        │  $orderby receivedDateTime desc
        │  optional $filter on receivedDateTime (UTC ISO 8601)
        ▼
List[MailMessage]
        │  .id, .internet_message_id, .subject, .sender
        │  .received_datetime (UTC ISO string)
        │  .body_html, .body_text, .body_preview
        │  .has_attachments
        │
        ├──────────────────────────────────────────────────────────────
        │  Per email (up to cfg.portal.parallel_downloads=5 concurrently)
        │
        ▼
get_date_folder_name(received_datetime, "%y.%m.%d")
        │  UTC → local time conversion via `astimezone(tz=None)`
        ▼
get_daily_folder(received_datetime, root_folder, format, fallback)
        │  root_folder = CLI override OR config.output.root_folder
        │  Path(...).expanduser() is always applied
        │  Primary default: ~/Desktop/CongVanExport/<date>/
        │  On OSError → fallback_output_folder OR ~/Desktop/CongVanExport/<date>/
        ▼
Path(daily_folder), bool(used_fallback)
        │
        ▼
DedupManager(daily_folder)
        │  Loads ~/.tool_mail_cong_van/<date>/_processed.json
        │  Pre-check: message_id + internet_message_id only
        │  → if duplicate → skip email before file I/O
        │
        ▼
_acquire_files()
        │
        ├── Strategy 1: portal-first
        │       │
        │       ├── extract_first_portal_url(body_html, body_text, url_patterns)
        │       │       ├── parse href="..."
        │       │       ├── scan bare URLs in text + HTML
        │       │       ├── html.unescape() on extracted URLs
        │       │       └── filter + dedup against configured portal patterns
        │       │
        │       ├── extract_portal_access_code(body_text, body_html)
        │       │       └── if no link exists, extractor can still construct
        │       │          https://thongbao.ipvietnam.gov.vn/tra-cuu-don/{code}
        │       │
        │       └── BrowserDownloader.download(portal_url, daily_folder, access_code)
        │               ├── sync_playwright() → chromium.launch(headless=cfg.portal.headless)
        │               ├── page.goto(..., timeout=30000, wait_until="networkidle")
        │               ├── optionally fill access-code input + submit
        │               ├── Strategy 1: click bulk "Tải tất cả"
        │               ├── Strategy 2: click each `a.file-item__title`
        │               └── save downloads into daily_folder
        │
        └── Strategy 2: attachment fallback
                │  only if cfg.portal.fallback_to_attachments == True
                │  GET /attachments metadata
                │  GET contentBytes or /$value bytes
                └── write files into daily_folder
        │
        ▼
parse_document(text=msg.body_preview, pdf_path=_find_main_pdf(downloaded_paths))
        │  normalize_text() → NFC + whitespace normalization
        │  if a PDF exists: extract_text_from_pdf() via PyMuPDF and merge with body preview
        ▼
ParsedDocument
        │  .so_cong_van, .so_cong_van_num, .so_don, .so_yeu_cau, .so_gcn
        │  .issue_date, .deadline_months, .deadline_date
        │  .loai_cong_van, .loai_hinh_don, .noi_dung_cong_van, .nhan_hieu
        │
        ▼
DedupManager.is_duplicate()   (full check under _write_lock)
        │  additional business keys: date_folder+so_don, date_folder+filename
        │  → if duplicate → skip
        │
        ▼
ExcelWriter.next_sequence_number()
        │  scans DATA sheet rows where column A is numeric
        │  returns next 1-based sequence for that day
        │
_rename_downloaded_files(paths, seq)
        │  renames each file to `{seq}-{original_name}`
        │  example: `3-thongbao.pdf`
        │
        ▼
_write_results(...)
        │  if seq == 1 → append_date_row("DD/MM/YYYY") first
        │  then append_data_row({
        │      "Ngày nhận công văn": seq,
        │      "Số công văn": parsed.so_cong_van_num,
        │      "Ngày issue công văn": MM/DD/YYYY,
        │      "Deadline trả lời Cục": MM/DD/YYYY,
        │      "Nội dung công văn": parsed.nhan_hieu,
        │      "Lỗi": numbered validation errors (if any)
        │  })
        │  append_meta_row({... run_status, filenames, so_don ...})
        ▼
DedupManager.register(...)
        │  persists ~/.tool_mail_cong_van/<date>/_processed.json
        ▼
_log_run_summary() + ProcessResult counters
```

---

## Write Path (User Action → Excel)

```
User clicks "📥 Quét mail" in GUI
        │
CongVanApp._do_scan()
        │  parses date range from UI
        │  chooses output folder (UI value or default ~/Desktop/CongVanExport)
        │  optionally overrides mail.target_folder_name at runtime
        │  pre-checks for locked Excel files under output root
        │
        ▼
threading.Thread(target=_thread, daemon=True)
        │
        ▼
EmailProcessor.run(progress=..., date_from=..., date_to=..., output_folder_override=..., on_excel_locked=...)
        │
        ├── _setup(): auth → GraphClient → MailReader → folder → messages
        ├── ThreadPoolExecutor(max_workers=parallel_downloads)
        └── _process_one() per email
                │
                │  if ExcelLockedError occurs during write:
                │    GUI callback may show dialog → user closes Excel → retry once
                │
                └── progress(current, total, message, stats_dict)
                        │
                        ▼
                CongVanApp._on_progress()
                        └── self.after(0, ...) updates labels, progress bar, dashboard, log panel
```

---

## Headless / CLI Path

```
run_app.py
    └── src.main:main()
            ├── --headless absent → _run_gui()
            └── --headless present → _run_headless()
                    ├── load_config(config_path)
                    ├── GraphAuth(...)
                    ├── auth.is_authenticated() must already be True
                    ├── EmailProcessor.run(..., output_folder_override=cli_value)
                    └── sys.exit(1 if result.error_count > 0 else 0)
```

- If no cached login exists, headless mode exits with code `2`
- Default CLI output folder is `~/Desktop/CongVanExport`

---

## Startup / Initialization Sequence

```
run_app.py
    ├── sys.path.insert(0, repo_root_or_exe_dir)
    └── from src.main import main
            └── main()
                    ├── argparse parses GUI/headless mode
                    ├── logging.basicConfig(...)
                    └── _run_gui() or _run_headless()
```

### `load_config()` search order

If `config_path` is not explicitly passed, `src/config.py:load_config()` searches:
1. `config.json` next to the frozen `.exe` (when `sys.frozen` is true)
2. `config.json` at the package root (repo root during source runs)
3. `config.json` in the current working directory

All configured output paths use `Path(...).expanduser()` before use.

---

## Optional Local Web Flow (Present in Source)

`src/web/server.py:create_app()` defines an alternate execution path:

```
POST /api/scan
    └── background thread
            └── EmailProcessor.run(...)
                    └── pushes progress into asyncio.Queue
                            └── GET /api/scan/stream (SSE)
```

`run_web.py` is still a placeholder, so this flow exists in code but is not currently wired to a repo launcher script.

---

## File Output Locations

| File | Path | Created by |
|---|---|---|
| Daily folder | `<output_root>\26.04.14\` (default root: `~/Desktop/CongVanExport`) | `src/folder/routing.py:get_daily_folder()` |
| Excel report | `<daily_folder>\SO CONG VAN DEN-LIENDO.xlsx` | `src/excel/writer.py:ExcelWriter` |
| Downloaded files | `<daily_folder>\{seq}-{original_name}` | `src/processor/email_processor.py:_rename_downloaded_files()` |
| Dedup registry | `~/.tool_mail_cong_van/<date>/_processed.json` | `src/dedup/manager.py` |
| GUI scan log | `~/.tool_mail_cong_van/<from_date>/scan_<range>.log` | `src/gui/app.py:_add_scan_log_handler()` |
| Scheduler wrapper log | repo root or dist root: `_scheduler_run.log` | `run_headless.sh`, `run_headless.bat`, `packaging/windows/run_headless.dist.bat` |
| Token cache | `~/.tool_mail_cong_van/token_cache.bin` | `src/auth/graph_auth.py` |
