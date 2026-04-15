# CLAUDE.md — Quick Reference for AI Agents

> Fast lookup. Do NOT spend time re-reading source files — use this map first.

---

## 🗺️ Fast Repo Map (Key Files)

| File | One-line description |
|---|---|
| `src/main.py` | CLI entry — routes to `_run_gui()` or `_run_headless()` |
| `src/config.py` | `load_config()` → `AppConfig` dataclass from `config.json` |
| `src/auth/graph_auth.py` | `GraphAuth` — MSAL token cache (`~/.tool_mail_cong_van/token_cache.bin`), `get_token()`, `is_authenticated()`, `AuthRequiredError` |
| `src/graph/client.py` | `GraphClient` — `get()`, `get_bytes()`, `paginate()` with retry/rate-limit |
| `src/mail/reader.py` | `MailReader.find_cong_van_folder()`, `get_messages()` → `List[MailMessage]` |
| `src/mail/downloader.py` | `AttachmentDownloader.list_attachments()`, `download_all()` |
| `src/portal/url_extractor.py` | `extract_first_portal_url(body_html, body_text, url_patterns)` |
| `src/portal/browser_downloader.py` | `BrowserDownloader.download(portal_url, target_folder)` → `PortalDownloadResult` |
| `src/parser/rules.py` | `parse_document(text, pdf_path)` → `ParsedDocument`; `CLASSIFICATION_RULES` |
| `src/excel/writer.py` | `ExcelWriter.append_data_row()`, `append_meta_row()`, `next_sequence_number()` |
| `src/dedup/manager.py` | `DedupManager.is_duplicate()`, `register()` |
| `src/folder/routing.py` | `get_daily_folder()`, `get_date_folder_name()`, `get_tool_export_folder()` |
| `src/processor/email_processor.py` | `EmailProcessor.run()` — parallel pipeline (ThreadPoolExecutor); `_write_lock` serialises Excel+dedup |
| `src/gui/app.py` | `CongVanApp(tk.Tk)` — `run_gui()` entry; custom tab bar (Main / Activities); pre-loads stats from `_processed.json`; scan log written to `~/.tool_mail_cong_van/<date>/scan_<range>.log` |
| `config.json` | Runtime config (Azure client_id, output folder, portal settings) |
| `requirements.txt` | `msal, requests, PyMuPDF, openpyxl, python-dateutil, playwright, pyinstaller` |

---

## 🔑 Access Patterns for Core Objects

### Get config
```python
from src.config import load_config
cfg = load_config()          # searches config.json at package root or cwd
cfg.azure.client_id          # str
cfg.output.root_folder       # str (network path)
cfg.portal.url_patterns      # List[str]
```

### Get auth token
```python
from src.auth.graph_auth import GraphAuth
auth = GraphAuth(client_id=cfg.azure.client_id,
                 authority=cfg.azure.authority,
                 scopes=cfg.azure.scopes)
token = auth.get_token()     # None if login fails
auth.is_authenticated()      # bool — check before headless run
```

### Get emails
```python
from src.graph.client import GraphClient
from src.mail.reader import MailReader
client = GraphClient(token)
reader = MailReader(client, page_size=50)
folder = reader.find_cong_van_folder("Công văn")  # MailFolder | None
messages = reader.get_messages(folder.id,
                                received_after=datetime(2026,4,14),
                                received_before=datetime(2026,4,14,23,59))
# messages: List[MailMessage]
# msg.body_html, msg.body_text, msg.body_preview, msg.has_attachments
```

### Extract portal URL
```python
from src.portal.url_extractor import extract_first_portal_url
url = extract_first_portal_url(msg.body_html, msg.body_text, cfg.portal.url_patterns)
# url: str | None
```

### Download from portal (Playwright)
```python
from src.portal.browser_downloader import BrowserDownloader
dl = BrowserDownloader(button_selectors=cfg.portal.download_button_selectors,
                        headless=cfg.portal.headless)
result = dl.download(url, target_folder)
# result.success: bool
# result.downloaded_paths: List[Path]
# result.notes: List[str]
```

### Parse document
```python
from src.parser.rules import parse_document
parsed = parse_document(text=msg.body_preview, pdf_path=Path("file.pdf"))
# parsed.so_cong_van, parsed.so_don, parsed.loai_cong_van
# parsed.issue_date, parsed.deadline_months, parsed.deadline_date
```

### Check/register dedup
```python
from src.dedup.manager import DedupManager
dedup = DedupManager(daily_folder)   # loads _processed.json
is_dup, reason = dedup.is_duplicate(message_id=msg.id,
                                      internet_message_id=msg.internet_message_id,
                                      date_folder=folder_name,
                                      so_don=parsed.so_don)
dedup.register(...)                  # call AFTER successful Excel write
```

### Write Excel
```python
from src.excel.writer import ExcelWriter
writer = ExcelWriter(daily_folder, cfg.output.excel_filename)
seq = writer.next_sequence_number()
writer.append_data_row({"STT": seq, "Số đơn": "4-2025-20619", ...})
writer.append_meta_row({"message_id": msg.id, ...})
```

### Get daily folder
```python
from src.folder.routing import get_daily_folder, get_date_folder_name
daily_folder, used_fallback = get_daily_folder(
    msg.received_datetime,          # ISO UTC string from Graph
    cfg.output.root_folder,
    cfg.output.date_folder_format,
    cfg.output.fallback_output_folder,
)
folder_name = get_date_folder_name(msg.received_datetime, cfg.output.date_folder_format)
# e.g. "26.04.14"
```

---

## 🚫 What NOT to Break

| Area | Risk | Rule |
|---|---|---|
| `CLASSIFICATION_RULES` order in `rules.py` | Wrong document type assigned | "Từ chối hủy bỏ HLC" must come before "Cấp toàn bộ" |
| `DATA_COLUMNS` order in `writer.py` | Corrupts existing Excel files | Append only — never reorder |
| `routing.py` UTC→local conversion | Wrong date folder | Never use `datetime.now()` for folder routing |
| `DedupManager._file` path | Dedup breaks | Always uses `~/.tool_mail_cong_van/`, not network path || `ExcelWriter._save()` lock check | Silent data loss | Always check for `~$` lock file before saving |
| GUI thread safety | App crash | Only use `self.after(0, cb)` to update GUI from threads |

---

## 🏃 Important Commands

```bat
:: Run app (GUI)
python run_app.py

:: Run headless
python run_app.py --headless --from-datetime "15/04/2026 00:00"

:: Run tests
python -m pytest tests/ -v

:: Install Playwright browser (one-time)
pip install playwright && playwright install chromium

:: Build exe
build.bat
```

---

## 📁 Output Locations

| Item | Location |
|---|---|
| Daily output folder | `\\LIENDO\...\Nhan cong van tu IPVN\26.04.14\` |
| Excel file | `<daily_folder>\SO CONG VAN DEN-LIENDO.xlsx` |
| Dedup registry | `~/.tool_mail_cong_van/<date>/_processed.json` |
| Scan log | `~/.tool_mail_cong_van/<date>/scan_<range>.log` |
| Token cache | `~/.tool_mail_cong_van/token_cache.bin` |
| Fallback output | `~/Desktop/ToolXuLyMailCongVan/<date>/` |

