# Pattern Cookbook — Công Văn Processor

> Copy-paste templates for common coding tasks. Cite real file paths.
> Updated: 2026-04-15

---

## Import Paths Quick Reference

```python
from src.config import load_config, AppConfig, PortalConfig
from src.auth.graph_auth import GraphAuth
from src.graph.client import GraphClient
from src.mail.reader import MailReader, MailMessage, MailFolder
from src.mail.downloader import AttachmentDownloader, AttachmentInfo
from src.portal.url_extractor import extract_first_portal_url, extract_portal_urls
from src.portal.browser_downloader import BrowserDownloader, PortalDownloadResult
from src.parser.rules import parse_document, ParsedDocument, CLASSIFICATION_RULES
from src.excel.writer import ExcelWriter, ExcelLockedError, DATA_COLUMNS, META_COLUMNS
from src.dedup.manager import DedupManager, DedupRecord
from src.folder.routing import get_daily_folder, get_date_folder_name, get_tool_export_folder
from src.processor.email_processor import EmailProcessor, ProcessResult, ScanCancelledError, AuthRequiredError
```

*Inside `src/` package — use relative imports:* `from ..config import load_config`

---

## Pattern 1 — Add a New Document Classification Rule

**When:** A new type of "công văn" appears that isn't being classified correctly.

**File:** `src/parser/rules.py`

**Steps:**
1. Identify the unique Vietnamese phrase(s) that appear in this document type (use the email body or PDF text).
2. Append a tuple to `CLASSIFICATION_RULES` **at the right position** (first-match-wins, read comments on ordering).

```python
# In src/parser/rules.py — CLASSIFICATION_RULES list:
CLASSIFICATION_RULES: List[tuple] = [
    ("Dự định từ chối",            ["dự định từ chối"]),
    ("Từ chối hủy bỏ HLC",         ["từ chối", "hủy bỏ hiệu lực"]),
    # ... existing rules ...
    ("Thông báo chấp nhận đơn",    ["chấp nhận đơn", "hợp lệ"]),  # ← NEW
]
```

**⚠ Pitfalls:**
- All phrases in a tuple must ALL be present (AND logic, not OR).
- The first matching rule wins — put more specific rules BEFORE general ones.
- "Từ chối hủy bỏ HLC" MUST stay before "Cấp toàn bộ" — both phrases can co-exist in a rejection doc.

**Test:** Add a test case to `tests/test_parser.py`:
```python
def test_new_classification():
    parsed = parse_document("... chấp nhận đơn ... hợp lệ ...")
    assert parsed.loai_cong_van == "Thông báo chấp nhận đơn"
```

---

## Pattern 2 — Add a New Excel Column

**When:** Need to capture a new field in the Excel output.

**Steps:**

**Step 1** — Add to `DATA_COLUMNS` in `src/excel/writer.py`:
```python
DATA_COLUMNS: List[str] = [
    # ... existing columns ...
    "Tên cột mới",   # ← append at the end (never reorder; "Lỗi" must stay last)
]
```

**Step 2** — Add field to `ParsedDocument` in `src/parser/rules.py` (if it's a parsed field):
```python
@dataclass
class ParsedDocument:
    # ... existing fields ...
    new_field: Optional[str] = None
```

**Step 3** — Extract the field (add regex + extraction function in `src/parser/rules.py`):
```python
_RE_NEW_FIELD = re.compile(r"pattern here", re.UNICODE)

def extract_new_field(text: str) -> Optional[str]:
    m = _RE_NEW_FIELD.search(text)
    return m.group(1).strip() if m else None

# Inside parse_document():
result.new_field = extract_new_field(combined)
```

**Step 4** — Add to row dict in `src/processor/email_processor.py:_write_results()`:
```python
row = {
    # ... existing fields ...
    "Tên cột mới": parsed.new_field or "",
}
```

**⚠ Pitfalls:**
- Never reorder `DATA_COLUMNS` — existing Excel files will have columns in the old order.
- The `ExcelWriter.append_data_row()` uses `header_map` lookup — backward-compatible.

---

## Pattern 3 — Add a New Portal URL Pattern

**When:** A new government portal domain appears in email bodies.

**File:** `config.json`

```json
{
  "portal": {
    "url_patterns": [
      "ipvietnam.gov.vn",
      "dichvucong.ipvietnam",
      "newportal.gov.vn"   ← add here
    ]
  }
}
```

No code changes needed. Patterns are loaded via `PortalConfig.url_patterns` in `src/config.py`.

**To also support a new download button selector:**
```json
{
  "portal": {
    "download_button_selectors": [
      "button:has-text('Tải tất cả')",
      "button:has-text('Download All')"   ← add here
    ]
  }
}
```

---

## Pattern 4 — Run the Full Pipeline Programmatically (No GUI)

**When:** Writing a script, test, or new headless workflow.

```python
from pathlib import Path
from datetime import datetime
from src.config import load_config
from src.auth.graph_auth import GraphAuth
from src.processor.email_processor import EmailProcessor

cfg = load_config(Path("config.json"))
auth = GraphAuth(
    client_id=cfg.azure.client_id,
    authority=cfg.azure.authority,
    scopes=cfg.azure.scopes,
)

if not auth.is_authenticated():
    print("Chạy GUI trước để đăng nhập.")
    exit(1)

from src.auth.graph_auth import AuthRequiredError

processor = EmailProcessor(cfg, auth)
try:
    result = processor.run(
        progress=lambda c, t, m, s=None: print(f"[{c}/{t}] {m}"),
        date_from=datetime(2026, 4, 14),
        date_to=datetime(2026, 4, 14, 23, 59),
        output_folder_override=None,   # uses config root_folder
    )
except AuthRequiredError:
    print("Token revoked or account blocked — re-authenticate via GUI.")
    exit(1)
print(result.summary())
```

---

## Pattern 5 — Parse a Single Document (Unit Test / Debug)

**When:** Debugging parsing failures or writing tests.

```python
from pathlib import Path
from src.parser.rules import parse_document

# From email body text only
parsed = parse_document(text="""
    Hà Nội, ngày 13 tháng 04 năm 2026
    Số: 53397/SHTT-NH.IP
    Về việc: Kết quả thẩm định nội dung đơn đăng ký nhãn hiệu
    Số đơn: 4-2025-20619
    Trong thời hạn 02 tháng kể từ ngày ra thông báo này
""")
print(parsed.so_cong_van)      # "53397/SHTT-NH.IP"
print(parsed.so_don)           # "4-2025-20619"
print(parsed.loai_cong_van)    # "KQTĐ nội dung"
print(parsed.deadline_months)  # 2
print(parsed.deadline_date)    # date(2026, 6, 13)

# From PDF file
parsed_with_pdf = parse_document(
    text=email_body_preview,
    pdf_path=Path("tests/fixtures/sample.pdf"),
)
```

---

## Pattern 6 — Check and Register Deduplication

**When:** Processing any new email in the pipeline.

```python
from pathlib import Path
from src.dedup.manager import DedupManager
from src.folder.routing import get_date_folder_name

daily_folder = Path("~/Desktop/CongVanExport/26.04.14").expanduser()
folder_name = get_date_folder_name(msg.received_datetime, "%y.%m.%d")
dedup = DedupManager(daily_folder)

# Pre-check (before acquiring files — tech key only)
is_dup, reason = dedup.is_duplicate(
    message_id=msg.id,
    internet_message_id=msg.internet_message_id,
    date_folder=folder_name,
    # so_don=None,  attachment_filenames=None  ← not yet known
)
if is_dup:
    print(f"Skipping duplicate: {reason}")
    return

# ... acquire files, parse ...

# Full check (after parsing — business keys available)
is_dup, reason = dedup.is_duplicate(
    message_id=msg.id,
    internet_message_id=msg.internet_message_id,
    date_folder=folder_name,
    so_don=parsed.so_don,
    attachment_filenames=["1-thongbao.pdf"],
)

# After successful Excel write:
dedup.register(
    message_id=msg.id,
    internet_message_id=msg.internet_message_id,
    date_folder=folder_name,
    so_don=parsed.so_don,
    attachment_filenames=["1-thongbao.pdf"],
    run_status="OK",
)
```

---

## Pattern 7 — Write to Excel (Safe Write with Lock Handling)

**When:** Adding a new row to the Excel file.

```python
from src.excel.writer import ExcelWriter, ExcelLockedError
from pathlib import Path

daily_folder = Path("~/Desktop/CongVanExport/26.04.14").expanduser()
writer = ExcelWriter(daily_folder, "SO CONG VAN DEN-LIENDO.xlsx")
seq = writer.next_sequence_number()   # reads existing file, returns next STT

row = {
    "STT":                  seq,
    "Ngày nhận mail":       "2026-04-14",
    "Tên mail (Subject)":   "Thông báo kết quả thẩm định",
    "Người gửi":            "IPVN <ipvn@example.com>",
    "Tên attachment":       "1-thongbao.pdf",
    "Số công văn":          "53397/SHTT-NH.IP",
    "Loại công văn":        "KQTĐ nội dung",
    # ... all 17 DATA_COLUMNS fields
}

for attempt in range(2):
    try:
        writer.append_data_row(row)
        writer.append_meta_row({"message_id": msg.id, ...})
        break
    except ExcelLockedError as exc:
        if attempt == 0:
            print(f"Excel is open: {exc.excel_path}. Please close it.")
            input("Press Enter after closing Excel...")
        else:
            raise
```

---

## Pattern 8 — Add a GUI Dialog (tkinter, Thread-Safe)

**When:** Need to show a dialog from the worker thread during processing.

```python
# In CongVanApp class (src/gui/app.py):
def _ask_user_something(self, param: str) -> bool:
    """
    Called from scan worker thread. Shows dialog on main thread.
    Returns True/False based on user choice.
    BLOCKS worker thread until user responds.
    """
    import threading
    event = threading.Event()
    result = [False]

    def _show() -> None:
        dlg = tk.Toplevel(self)
        dlg.title("Confirm")
        dlg.grab_set()
        dlg.transient(self)

        tk.Label(dlg, text=f"Question about: {param}").pack(pady=10)

        def _yes():
            result[0] = True
            dlg.destroy()
            event.set()

        def _no():
            result[0] = False
            dlg.destroy()
            event.set()

        tk.Button(dlg, text="Yes", command=_yes).pack(side=tk.LEFT, padx=10, pady=10)
        tk.Button(dlg, text="No", command=_no).pack(side=tk.LEFT, padx=10, pady=10)

    self.after(0, _show)    # schedule on main thread
    event.wait()            # block worker thread
    return result[0]
```

**⚠ Pitfall:** Never call `tk.Toplevel()` directly from a worker thread — always use `self.after(0, ...)`.

---

## Pattern 9 — Run Tests

```bash
# All tests
python -m pytest tests/ -v

# Single file
python -m pytest tests/test_parser.py -v

# Specific test
python -m pytest tests/test_parser.py::test_so_cong_van_extraction -v

# With output visible
python -m pytest tests/ -v -s
```

---

## Pattern 10 — Add a New Config Key

**When:** Adding a new configurable behavior.

**Step 1** — Add field to the appropriate dataclass in `src/config.py`:
```python
@dataclass
class PortalConfig:
    # ... existing fields ...
    my_new_setting: bool = False   # ← with sensible default
```

**Step 2** — Read from JSON in `load_config()`:
```python
portal = PortalConfig(
    # ... existing fields ...
    my_new_setting=bool(portal_raw.get("my_new_setting", False)),
)
```

**Step 3** — Add to `config.json` (optional — default handles missing key):
```json
{
  "portal": {
    "my_new_setting": true
  }
}
```

---

## Pattern 11 — Extract Portal URL from Email Body

**When:** Need to test URL extraction logic or process custom email content.

```python
from src.portal.url_extractor import extract_portal_urls, extract_first_portal_url

body_html = '<a href="https://dichvucong.ipvietnam.gov.vn/tra-cuu?so=53397">Xem hồ sơ</a>'
body_text = "Xem tại https://dichvucong.ipvietnam.gov.vn/tra-cuu?so=53397"
url_patterns = ["ipvietnam.gov.vn", "dichvucong.ipvietnam"]

# Get all portal URLs (deduplicated)
all_urls = extract_portal_urls(body_html, body_text, url_patterns)

# Get first one only (used by processor)
first_url = extract_first_portal_url(body_html, body_text, url_patterns)
```

---

## Pattern 12 — Download Files from Portal (Browser Automation)

**When:** Manually triggering a portal download outside the main pipeline.

```python
from pathlib import Path
from src.portal.browser_downloader import BrowserDownloader

downloader = BrowserDownloader(
    button_selectors=[
        "button:has-text('Tải tất cả')",
        "a:has-text('Tải tất cả')",
    ],
    page_load_timeout_ms=15000,
    wait_after_click_ms=8000,
    headless=False,   # False = show browser window for debugging
)
# Strategy 1 (bulk button) is tried first; strategy 2 (individual .file-item__title links) is the fallback.
# Only the caller should add notes to result.notes — do not add notes inside strategy methods.

result = downloader.download(
    portal_url="https://dichvucong.ipvietnam.gov.vn/tra-cuu?so=53397",
    target_folder=Path(r"C:\temp\downloads"),
)

if result.success:
    for path in result.downloaded_paths:
        print(f"Downloaded: {path}")
else:
    print("Failed:", result.notes)
```

**⚠ Debug tip:** Set `headless=False` to see the browser and diagnose button selector failures.
