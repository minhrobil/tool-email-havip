# 🤖 AGENTS.md — Công Văn Processor: Operating Manual for AI Agents

> **START HERE.** Read this file before touching any code.
> Last updated: 2026-04-15

---

## ⚡ Quick-Start Table (Priority Order)

| Priority | File | Purpose |
|---|---|---|
| 🔴 Always | `AGENTS.md` (this file) | Repo overview, architecture rules, coding patterns |
| 🔴 Always | `docs/architecture/pattern-cookbook.md` | Copy-paste templates for every common task |
| 🟡 For features | `docs/architecture/feature-map.md` | Where each feature lives in the code |
| 🟡 For bugs | `docs/architecture/known-risks.md` | Known fragile areas ranked by severity |
| 🟡 For data flow | `docs/architecture/data-flow.md` | Exact pipeline: email → Excel |
| 🟢 Reference | `docs/architecture/api-map.md` | All Microsoft Graph endpoints used |
| 🟢 Before tickets | `docs/tickets/` | Previous fixes in related areas |

---

## 📦 Repository Overview

| Property | Value |
|---|---|
| **Project name** | Công Văn Processor |
| **Type** | Desktop automation tool (Windows) |
| **Language** | Python 3.10+ |
| **Key frameworks** | MSAL, Microsoft Graph API, Playwright, openpyxl, tkinter |
| **Distribution** | Standalone `.exe` (PyInstaller) or run from source |
| **Architecture pattern** | Pipeline / Orchestrator pattern |
| **State** | No in-memory global state; token cached on disk |

**What it does:** Reads emails from an Outlook 365 "Công văn" folder, extracts portal links from email bodies, uses a headless Chromium browser to download PDF documents from the IP Vietnam government portal, parses the PDFs to extract legal document metadata, and writes daily Excel reports.

---

## 🗂️ Folder Structure

```
mail-extract/
├── src/
│   ├── config.py                    ← Typed config dataclasses + loader
│   ├── main.py                      ← CLI entry point (GUI + headless modes)
│   ├── auth/
│   │   └── graph_auth.py            ← MSAL OAuth, token cache (~/.tool_mail_cong_van/), AuthRequiredError
│   ├── graph/
│   │   └── client.py                ← Microsoft Graph HTTP client (retries, pagination)
│   ├── mail/
│   │   ├── reader.py                ← Folder discovery + message retrieval
│   │   └── downloader.py            ← Direct attachment download (fallback)
│   ├── portal/
│   │   ├── url_extractor.py         ← Extract portal URLs from email HTML/text
│   │   └── browser_downloader.py    ← Playwright: navigate portal, click download
│   ├── parser/
│   │   └── rules.py                 ← Vietnamese document regex parser
│   ├── excel/
│   │   └── writer.py                ← openpyxl Excel writer (DATA + META sheets)
│   ├── dedup/
│   │   └── manager.py               ← Per-day deduplication (_processed.json)
│   ├── folder/
│   │   └── routing.py               ← Daily folder path routing + fallback
│   ├── processor/
│   │   └── email_processor.py       ← Main pipeline orchestrator
│   └── gui/
│       └── app.py                   ← tkinter GUI (CongVanApp class; custom tab bar: Main / Activities)
├── tests/
│   ├── test_parser.py
│   ├── test_dedup.py
│   ├── test_folder_routing.py
│   ├── test_portal_extractor.py
│   └── test_file_naming.py
├── docs/
│   ├── architecture/                ← All architecture docs
│   └── tickets/                     ← Per-ticket documentation
├── config.json                      ← ⚠ EDIT THIS — Azure client_id, output folder
├── requirements.txt                 ← pip dependencies
├── run.bat                          ← Launch GUI
├── run_headless.bat                 ← Headless mode (Task Scheduler)
├── setup_scheduler.bat              ← Register Windows Task Scheduler
└── build.bat                        ← PyInstaller build
```

---

## 🏗️ Architecture

### Pattern: Pipeline / Orchestrator (Parallel Download)

```
EmailProcessor.run()
    │
    ├── _setup()        → Auth, GraphClient, MailReader, find folder, fetch messages
    │
    └── ThreadPoolExecutor(max_workers=cfg.portal.parallel_downloads)
            │  Up to 5 emails download simultaneously
            │
            ├── _process_one() [thread 1]
            ├── _process_one() [thread 2]
            └── _process_one() [thread N]
                    ├── get_daily_folder()           folder/routing.py
                    ├── DedupManager.is_duplicate()  dedup/manager.py  (pre-check, tech key)
                    ├── _acquire_files()             [concurrent — no lock]
                    │       ├── Strategy 1: extract_first_portal_url() → BrowserDownloader.download()
                    │       │       ├── (1) click "Tải tất cả" bulk button
                    │       │       └── (2) click individual .file-item__title links (fallback)
                    │       └── Strategy 2: AttachmentDownloader.download_all()
                    ├── parse_document()             parser/rules.py
                    │
                    └── [acquire _write_lock]        ← serializes Excel write + dedup register
                            ├── DedupManager.is_duplicate()  (post-parse, business key)
                            ├── ExcelWriter.append_data_row()
                            ├── ExcelWriter.append_meta_row()
                            ├── DedupManager.register()
                            └── _log_run_summary()   (standard logging)
```

### Module Communication Rules

- All modules communicate through **direct function/method calls** — no event bus or message queue.
- The `EmailProcessor` is the single orchestrator — all cross-module calls go through it.
- `GraphAuth` → `GraphClient` → `MailReader` / `AttachmentDownloader` (token injected via constructor).
- `DedupManager` is scoped to ONE daily folder per instantiation.
- GUI (`CongVanApp`) runs the scan in a **daemon thread** and communicates with the main thread exclusively via `self.after(0, callback)`.

### Data Flow Summary

```
Microsoft 365 Mailbox
    → Graph API (GraphClient)
        → MailReader (folder + messages)
            → portal URL extraction (portal/url_extractor.py)
                → Playwright BrowserDownloader (downloads PDF)
            → OR: AttachmentDownloader (direct attachment)
        → parse_document() → ParsedDocument
        → [_write_lock] DedupManager (check + register)
        → [_write_lock] ExcelWriter (DATA row + META row)
        → _log_run_summary() (standard logging)
    → ProcessResult (returned to GUI or headless runner)
```

---

## ⚙️ Configuration

The single source of truth is `config.json` (at repo root). It is loaded by `src/config.py:load_config()` into typed dataclasses:

| Dataclass | Section | Key fields |
|---|---|---|
| `AzureConfig` | `azure` | `client_id` (**required**), `tenant_id`, `scopes` |
| `MailConfig` | `mail` | `target_folder_name` ("Công văn"), `page_size` (50) |
| `OutputConfig` | `output` | `root_folder` (network path), `excel_filename`, `fallback_output_folder` |
| `ProcessingConfig` | `processing` | `strict_single_attachment`, `log_level` |
| `PortalConfig` | `portal` | `url_patterns`, `download_button_selectors`, `headless`, `parallel_downloads` (int, default 5) |

**⚠ NEVER hardcode values** that belong in `config.json`.

---

## 🔐 Authentication Flow

1. `GraphAuth.__init__()` loads token cache from `~/.tool_mail_cong_van/token_cache.bin`; `validate_authority=False` avoids a network call at startup
2. `get_token()` → tries silent acquisition first; falls back to interactive browser login
3. Interactive login runs in a **daemon thread** with a 120-second timeout
4. Token cached automatically after successful login
5. `AuthRequiredError` — raised when the token is revoked or the account is blocked; the GUI catches this and redirects to the login screen
6. Headless mode (`main.py:_run_headless`) requires token pre-cached — exits if not authenticated

---

## 📊 Excel Output Structure

File: `SO CONG VAN DEN-LIENDO.xlsx` inside each daily folder.

| Sheet | Purpose | Columns |
|---|---|---|
| `DATA` | Business rows (one per email) | STT, Ngày nhận mail, Tên mail, Người gửi, Tên attachment, Số công văn, Loại công văn, Ngày issue, Số tháng deadline, Deadline, Số đơn, Loại hình đơn, Nội dung, Trạng thái, Message ID, Lỗi |
| `META` | Dedup/run metadata | message_id, internet_message_id, date_folder, so_don, attachment_filenames, processed_at, run_status |

The **"Lỗi"** column (last column in DATA) contains numbered validation errors, e.g. `"1: Thiếu số công văn\n2: Thiếu nhãn hiệu"`. Rows with errors are highlighted red. Old "Ghi chú" / "Ghi chú lỗi" columns have been removed.

**To add a new column:** edit `DATA_COLUMNS` or `META_COLUMNS` list in `src/excel/writer.py`. Backward-compatible: existing files get the new column only on next write.

---

## 🧪 Testing

```bash
pip install pytest python-dateutil
python -m pytest tests/ -v
```

| Test file | Covers |
|---|---|
| `test_parser.py` | Vietnamese regex rules, classification, deadline calculation |
| `test_dedup.py` | Deduplication logic (all 4 key strategies) |
| `test_folder_routing.py` | UTC→local datetime, folder name formatting |
| `test_portal_extractor.py` | URL extraction from HTML/text bodies |
| `test_file_naming.py` | File rename / collision handling |

---

## 🔨 Build / Run Commands

```bat
:: Run GUI
run.bat

:: Run headless (Task Scheduler)
run_headless.bat

:: Run headless with date range
python run_app.py --headless --from-datetime "14/04/2026 00:00" --to-datetime "14/04/2026 23:59"

:: Register daily Task Scheduler (run as administrator)
setup_scheduler.bat

:: Build .exe
build.bat

:: Run tests
python -m pytest tests/ -v
```

---

## 📐 Architecture Rules (Non-Negotiable)

1. **Folder name = email received date (LOCAL time)** — NEVER use `datetime.now()` for folder routing. See `src/folder/routing.py` comments.
2. **Dedup before Excel write** — always call `DedupManager.is_duplicate()` before writing a row.
3. **Register after write** — always call `DedupManager.register()` only after a successful Excel write.
4. **GUI ↔ worker thread** — all GUI updates from worker threads must go through `self.after(0, callback)`. Direct tkinter calls from non-main threads will crash.
5. **ExcelLockedError handling** — always wrap `ExcelWriter` calls in a try/except for `ExcelLockedError`.
6. **Portal-first, attachment-fallback** — acquisition strategy order must not change: portal URL → direct attachment.
7. **_processed.json lives in `~/.tool_mail_cong_van/<date>/`** — NOT in the network output folder. This ensures dedup works even when the network is down.
8. **`_write_lock` serializes Excel write + dedup register** — `_process_one()` acquires `self._write_lock` before calling `ExcelWriter` and `DedupManager.register()`. File I/O (`_acquire_files`) runs concurrently outside the lock.

---

## ⚠️ Critical Files (Read Fully Before Modifying)

| File | Why Critical |
|---|---|
| `src/processor/email_processor.py` | Main pipeline — changing order of steps breaks dedup/Excel consistency |
| `src/dedup/manager.py` | Dedup state — changing key strategies could cause duplicate rows or false positives |
| `src/folder/routing.py` | Folder date logic — UTC→local conversion is critical |
| `src/excel/writer.py` | DATA_COLUMNS / META_COLUMNS order — breaking this corrupts existing Excel files |
| `src/parser/rules.py` | CLASSIFICATION_RULES order matters — first match wins |
| `config.json` | Production config — contains real Azure client_id and network paths |

---

## 🚨 Common Pitfalls

1. **Vietnamese diacritics in regex** — use literal chars in character classes, not `\w`. See `src/parser/rules.py` pattern comments.
2. **Playwright must be installed separately** — `pip install playwright && playwright install chromium`. The `.exe` also needs Chromium present.
3. **Excel file locked** — if `SO CONG VAN DEN-LIENDO.xlsx` is open in Excel, writes fail with `ExcelLockedError`. GUI handles this with a dialog; headless mode raises.
4. **Network path unreachable** — `get_daily_folder()` auto-falls back to `~/Desktop/ToolXuLyMailCongVan`. Files are saved there and a warning is logged.
5. **Token cache location** — `~/.tool_mail_cong_van/token_cache.bin`. Delete this file to force re-login.
6. **Headless mode requires pre-authentication** — must run GUI once first to cache the token.
7. **CLASSIFICATION_RULES order** — "Từ chối hủy bỏ HLC" must come BEFORE "Cấp toàn bộ" because cancellation-rejection docs also contain the grant phrase.
8. **Parallel downloads and `_write_lock`** — `_acquire_files()` runs concurrently (up to 5 threads). Only the Excel write + dedup register phase is serialised by `_write_lock`. Do NOT move I/O inside the lock — it will kill throughput.

---

## ✅ Pre-Submit Checklist

- [ ] No hardcoded paths, credentials, or magic strings
- [ ] No `datetime.now()` used for folder routing (use `msg.received_datetime`)
- [ ] Vietnamese text uses correct diacritics (người dùng, không phải nguoi dung)
- [ ] New columns added to both `DATA_COLUMNS` and the Excel row dict in `email_processor.py`
- [ ] Regex patterns tested against Vietnamese text with diacritics
- [ ] GUI updates only via `self.after(0, callback)` in worker threads
- [ ] Any new I/O in `_process_one()` outside the lock; only Excel write + `DedupManager.register()` inside `_write_lock`
- [ ] Tests pass: `python -m pytest tests/ -v`
- [ ] Ticket doc created in `docs/tickets/`

