# Data Flow — Công Văn Processor

> Traces the exact path data takes through the system.
> Updated: 2026-04-15

---

## Read Path (Email → Excel)

```
Microsoft 365 Mailbox ("Công văn" folder)
        │
        │  MSAL OAuth (token from ~/.tool_mail_cong_van/token_cache.bin)
        ▼
GraphClient.paginate("/me/mailFolders")
        │
        │  Find folder by name (case-insensitive, NFC-normalized, recursive)
        ▼
MailFolder.id
        │
GraphClient.paginate("/me/mailFolders/{id}/messages")
        │  $select includes full `body` (HTML + text) for URL extraction
        │  $filter on receivedDateTime (UTC ISO 8601)
        │  $orderby receivedDateTime desc
        ▼
List[MailMessage]
        │  .id, .internet_message_id, .subject, .sender
        │  .received_datetime (UTC ISO string)
        │  .body_html, .body_text, .body_preview
        │  .has_attachments
        │
        ├──────────────────────────────────────────────────────────────
        │  Per email (up to cfg.portal.parallel_downloads=5 concurrently):
        │
        ▼
get_date_folder_name(received_datetime, "%y.%m.%d")
        │  UTC → local time conversion (datetime.astimezone(tz=None))
        │  e.g. "2026-04-14T01:30:00Z" → local "2026-04-14" → "26.04.14"
        ▼
get_daily_folder(received_datetime, root_folder, format, fallback)
        │  Tries ~/Desktop/CongVanExport/26.04.14/ by default (mkdir)
        │  On OSError → fallback_output_folder or ~/Desktop/CongVanExport/26.04.14/
        ▼
Path (daily_folder), bool (used_fallback)
        │
        ▼
DedupManager(daily_folder)
        │  Loads ~/.tool_mail_cong_van/26.04.14/_processed.json
        │  Pre-check: message_id + internet_message_id only
        │  → if dup → skip email
        │
        ▼
_acquire_files()
        │
        ├── Strategy 1: extract_first_portal_url(body_html, body_text, url_patterns)
        │       │  Parse href="..." from HTML
        │       │  Scan bare URLs in text/HTML
        │       │  Filter by domain patterns (ipvietnam.gov.vn)
        │       │  Returns first matching URL or None
        │       │
        │       └── BrowserDownloader.download(url, daily_folder)
        │               │  sync_playwright → chromium.launch(headless=True)
        │               │  context(accept_downloads=True)
        │               │  page.goto(url, timeout=15000, wait_until=networkidle)
        │               │  Strategy 1: click "Tải tất cả" bulk button
               │  Strategy 2 (fallback): click individual .file-item__title links
        │               │  page.wait_for_timeout(8000)
        │               │  For each download: download.save_as(dest)
        │               │  browser.close()
        │               └── PortalDownloadResult{downloaded_paths, success, notes}
        │
        └── Strategy 2 (fallback): AttachmentDownloader
                │  GET /me/messages/{id}/attachments (metadata)
                │  For each: GET contentBytes (≤4MB) OR GET /$value (large)
                │  Write bytes to daily_folder
                └── List[Path]
        │
        ▼
parse_document(text=body_preview, pdf_path=main_pdf)
        │  normalize_text() → NFC, collapse whitespace
        │  If pdf_path: extract_text_from_pdf() via PyMuPDF, merge with email text
        │  Run all regex patterns on combined text
        ▼
ParsedDocument
        │  .so_cong_van, .so_don, .so_gcn, .so_yeu_cau
        │  .issue_date, .deadline_months, .deadline_date
        │  .loai_cong_van, .loai_hinh_don, .noi_dung_cong_van
        │
        ▼
DedupManager.is_duplicate() (full check)
        │  Additional business keys: date_folder+so_don, date_folder+filename
        │  → if dup → skip
        │
        ▼
ExcelWriter.next_sequence_number()
        │  Reads existing DATA sheet row count → returns next STT (1-based)
        │
_rename_downloaded_files(paths, seq)
        │  Renames each file to {seq}-{original_name} (e.g. "3-thongbao.pdf")
        │
        ▼
ExcelWriter.append_data_row(row_dict)
        │  _load_or_create(excel_path) → openpyxl Workbook
        │  Checks ~$<filename> lock file → raises ExcelLockedError if locked
        │  Writes row to DATA sheet using header_map lookup (backward-compatible)
        │  wb.save(excel_path)
        │
ExcelWriter.append_meta_row(meta_dict)
        │  Writes row to META sheet
        │
        ▼
DedupManager.register(message_id, internet_message_id, date_folder, so_don, filenames)
        │  Adds to in-memory sets
        │  Saves ~/.tool_mail_cong_van/26.04.14/_processed.json
        │
_log_run_summary()   (standard logging — replaces old _append_run_log)
        │
        ▼
ProcessResult.success_count++ (or file_error_count / missing_data_count / error_count)
```

---

## Write Path (User Action → Excel)

```
User clicks "📥 Quét mail" in GUI
        │
CongVanApp._do_scan()
        │  Parses date range from UI fields
        │  Pre-scan: checks for locked Excel files (_find_locked_excel_files())
        │  If locked: shows _confirm_close_excel() dialog (may run taskkill EXCEL.EXE)
        │
        ▼
threading.Thread → EmailProcessor.run(progress=..., date_from=..., date_to=..., output_folder_override=..., on_excel_locked=...)
        │
        │  [ThreadPoolExecutor — up to parallel_downloads=5 concurrent workers]
        │
        ├── Auth (GraphAuth.get_token)
        ├── Find folder (MailReader.find_cong_van_folder)
        ├── Fetch messages (MailReader.get_messages)
        │
        └── Per-email: _process_one()  [see Read Path above]
                │
                │  On ExcelLockedError during write:
                │      → on_excel_locked callback → GUI shows dialog → user closes Excel
                │      → retry once with fresh ExcelWriter
                │
                └── progress(current, total, message, stats_dict)
                        │
                        ▼
                CongVanApp._on_progress()  [dispatched via self.after(0, ...)]
                        │  Updates progress bar, step label, stat cards, dashboard
```

---

## Startup / Initialization Sequence

```
run.bat → python run_app.py
        │
run_app.py:
        from src.main import main
        main()
        │
        ▼ (no --headless flag)
_run_gui()
        │
        ▼
CongVanApp.__init__()
        │  Build login frame + main frame (both created but only one shown)
        │
        ▼
_load_config_and_route()
        │  load_config() → searches config.json at package root / cwd
        │  GraphAuth(client_id=...) → loads token cache
        │
        ├── is_authenticated() == True  → _show_main()  → _start_scheduler()
        └── is_authenticated() == False → _show_login()
```

---

## File Output Locations

| File | Path | Created by |
|---|---|---|
| Daily folder | `~/Desktop/CongVanExport/26.04.14/` by default, or selected output folder | `folder/routing.py:get_daily_folder()` |
| Excel report | `<daily_folder>\SO CONG VAN DEN-LIENDO.xlsx` | `excel/writer.py:ExcelWriter` |
| Downloaded PDF | `<daily_folder>\{seq}thongbao_12345.pdf` | `portal/browser_downloader.py` or `mail/downloader.py` |
| Dedup registry | `~/.tool_mail_cong_van/<date>/_processed.json` | `dedup/manager.py` |
| Scan log | `~/.tool_mail_cong_van/<date>/scan_<range>.log` | `processor/email_processor.py:_log_run_summary()` |
| Token cache | `~/.tool_mail_cong_van/token_cache.bin` | `auth/graph_auth.py` |
