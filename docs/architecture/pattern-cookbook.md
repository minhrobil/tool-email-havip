# Pattern Cookbook — Công Văn Processor

> Copy-paste templates for common coding tasks. Cite real file paths.
> Updated: 2026-05-05

---

## Import Paths Quick Reference

```python
from src.config import load_config, AppConfig, PortalConfig
from src.auth.graph_auth import GraphAuth, AuthRequiredError
from src.graph.client import GraphClient
from src.mail.reader import MailReader, MailMessage, MailFolder
from src.mail.downloader import AttachmentDownloader, AttachmentInfo
from src.portal.url_extractor import (
    extract_first_portal_url,
    extract_portal_urls,
    extract_portal_access_code,
)
from src.portal.browser_downloader import BrowserDownloader, PortalDownloadResult
from src.parser.rules import parse_document, ParsedDocument, CLASSIFICATION_RULES
from src.excel.writer import ExcelWriter, ExcelLockedError, DATA_COLUMNS, META_COLUMNS
from src.dedup.manager import DedupManager, DedupRecord
from src.folder.routing import get_daily_folder, get_date_folder_name, get_tool_export_folder
from src.processor.email_processor import EmailProcessor, ProcessResult, ScanCancelledError
from src.web.server import create_app
```

*Inside `src/` package — use relative imports:* `from ..config import load_config`

---

## Pattern 1 — Add a New Document Classification Rule

**When:** A new type of "công văn" appears that isn't being classified correctly.

**File:** `src/parser/rules.py`

**Steps:**
1. Identify the unique Vietnamese phrase(s) that appear in this document type.
2. Append a tuple to `CLASSIFICATION_RULES` **at the right position** (first-match-wins).

```python
CLASSIFICATION_RULES: List[tuple] = [
    ("Dự định từ chối",            ["dự định từ chối"]),
    ("Từ chối hủy bỏ HLC",         ["từ chối", "hủy bỏ hiệu lực"]),
    # ... existing rules ...
    ("Thông báo chấp nhận đơn",    ["chấp nhận đơn", "hợp lệ"]),
]
```

**⚠ Pitfalls:**
- All phrases in a tuple must all be present.
- The first matching rule wins.
- Always rerun `tests/test_parser.py`.

---

## Pattern 2 — Add a New Excel Column

**When:** Need to capture a new field in the Excel output.

**Step 1** — Append to `DATA_COLUMNS` in `src/excel/writer.py`:
```python
DATA_COLUMNS: List[str] = [
    # ... existing columns ...
    "Tên cột mới",   # append only; do not reorder existing columns
]
```

**Step 2** — Add a matching display header if needed:
```python
DATA_COLUMN_HEADERS: List[str] = [
    # ... existing headers ...
    "Tên cột mới",
]
```

**Step 3** — Populate it in `_write_results()`:
```python
row = {
    "Ngày nhận công văn": seq,
    "Số công văn": parsed.so_cong_van_num or "",
    "Tên cột mới": parsed.new_field or "",
}
```

**⚠ Pitfalls:**
- `ExcelWriter.append_data_row()` writes by `DATA_COLUMNS` key order, not by a header map.
- Keep `"Lỗi"` as the last business column unless you intentionally redesign the workbook.

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
      "newportal.gov.vn"
    ]
  }
}
```

No code changes needed. Patterns are loaded through `PortalConfig.url_patterns` in `src/config.py`.

---

## Pattern 4 — Run the Full Pipeline Programmatically (No GUI)

```python
from datetime import datetime
from src.config import load_config
from src.auth.graph_auth import GraphAuth, AuthRequiredError
from src.processor.email_processor import EmailProcessor

cfg = load_config()
auth = GraphAuth(
    client_id=cfg.azure.client_id,
    authority=cfg.azure.authority,
    scopes=cfg.azure.scopes,
)

if not auth.is_authenticated():
    raise SystemExit("Chạy GUI trước để đăng nhập.")

processor = EmailProcessor(cfg, auth)
try:
    result = processor.run(
        progress=lambda c, t, m, s=None: print(f"[{c}/{t}] {m}"),
        date_from=datetime(2026, 4, 14, 0, 0),
        date_to=datetime(2026, 4, 14, 23, 59),
        output_folder_override=None,
    )
except AuthRequiredError:
    raise SystemExit("Token revoked or account blocked — re-authenticate via GUI.")

print(result.summary())
```

---

## Pattern 5 — Parse a Single Document (Unit Test / Debug)

```python
from pathlib import Path
from src.parser.rules import parse_document

parsed = parse_document(text="""
Hà Nội, ngày 13 tháng 04 năm 2026
Số: 53397/SHTT-NH.IP
Về việc: Kết quả thẩm định nội dung đơn đăng ký nhãn hiệu
Số đơn: 4-2025-20619
Trong thời hạn 02 tháng kể từ ngày ra thông báo này
""")
print(parsed.so_cong_van)
print(parsed.so_don)
print(parsed.loai_cong_van)
print(parsed.deadline_date)

parsed_with_pdf = parse_document(
    text="Trích đoạn bodyPreview",
    pdf_path=Path("tests/fixtures/sample.pdf"),
)
```

---

## Pattern 6 — Check and Register Deduplication

```python
from pathlib import Path
from src.dedup.manager import DedupManager
from src.folder.routing import get_date_folder_name

daily_folder = Path("~/Desktop/CongVanExport/26.04.14").expanduser()
folder_name = get_date_folder_name(msg.received_datetime, "%y.%m.%d")
dedup = DedupManager(daily_folder)

is_dup, reason = dedup.is_duplicate(
    message_id=msg.id,
    internet_message_id=msg.internet_message_id,
    date_folder=folder_name,
)
if is_dup:
    print(f"Skipping duplicate: {reason}")
    raise SystemExit

# ... acquire files + parse ...

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

## Pattern 7 — Write to Excel (Current Workbook Layout)

```python
from datetime import datetime
from pathlib import Path
from src.excel.writer import ExcelWriter, ExcelLockedError

daily_folder = Path("~/Desktop/CongVanExport/26.04.14").expanduser()
writer = ExcelWriter(daily_folder, "SO CONG VAN DEN-LIENDO.xlsx")
seq = writer.next_sequence_number()

if seq == 1:
    writer.append_date_row("14/04/2026")

row = {
    "Ngày nhận công văn": seq,
    "Số công văn": parsed.so_cong_van_num or "",
    "Ngày issue công văn": parsed.issue_date.strftime("%m/%d/%Y") if parsed.issue_date else "",
    "Deadline trả lời Cục": parsed.deadline_date.strftime("%m/%d/%Y") if parsed.deadline_date else "",
    "Nội dung công văn": parsed.nhan_hieu or "",
}

missing = []
if not parsed.so_cong_van_num:
    missing.append("Thiếu số công văn")
if not parsed.issue_date:
    missing.append("Thiếu ngày issue công văn")
if not parsed.deadline_date:
    missing.append("Thiếu deadline")
if not parsed.nhan_hieu:
    missing.append("Thiếu nhãn hiệu")
if missing:
    row["Lỗi"] = "\n".join(f"{i}: {e}" for i, e in enumerate(missing, start=1))

for attempt in range(2):
    try:
        writer.append_data_row(row, highlight_red=bool(missing))
        writer.append_meta_row({
            "message_id": msg.id,
            "internet_message_id": msg.internet_message_id or "",
            "date_folder": "26.04.14",
            "so_don": parsed.so_don or "",
            "attachment_filenames": "; ".join(att_filenames),
            "processed_at": datetime.now().isoformat(timespec="seconds"),
            "run_status": status,
        })
        break
    except ExcelLockedError as exc:
        if attempt == 0:
            print(f"Close Excel and retry: {exc.excel_path}")
        else:
            raise
```

**Note:** The current workbook layout leaves many legacy business columns blank; `_write_results()` only fills the fields shown above plus `Lỗi` when validation fails.

---

## Pattern 8 — Add a GUI Dialog (tkinter, Thread-Safe)

```python
import threading
import tkinter as tk

def _ask_user_something(self, param: str) -> bool:
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

    self.after(0, _show)
    event.wait()
    return result[0]
```

**⚠ Pitfall:** Never call `tk.Toplevel()` directly from a worker thread.

---

## Pattern 9 — Run Tests

```bash
python -m pytest tests/ -v
python -m pytest tests/test_parser.py -v
python -m pytest tests/test_portal_extractor.py -v
python -m pytest tests/test_file_naming.py -v
```

---

## Pattern 10 — Add a New Config Key

```python
from dataclasses import dataclass

@dataclass
class PortalConfig:
    my_new_setting: bool = False
```

```python
portal = PortalConfig(
    my_new_setting=bool(portal_raw.get("my_new_setting", False)),
)
```

```json
{
  "portal": {
    "my_new_setting": true
  }
}
```

---

## Pattern 11 — Extract Portal URL and Access Code

```python
from src.portal.url_extractor import (
    extract_portal_urls,
    extract_first_portal_url,
    extract_portal_access_code,
)

body_html = '<a href="https://dichvucong.ipvietnam.gov.vn/tra-cuu?so=53397&amp;x=1">Xem hồ sơ</a>'
body_text = "Nhập mã eaf68de2849446a481472877dc83486a nếu trang yêu cầu"
url_patterns = ["ipvietnam.gov.vn", "dichvucong.ipvietnam"]

all_urls = extract_portal_urls(body_html, body_text, url_patterns)
first_url = extract_first_portal_url(body_html, body_text, url_patterns)
access_code = extract_portal_access_code(body_text, body_html)
```

---

## Pattern 12 — Download Files from Portal (Browser Automation)

```python
from pathlib import Path
from src.portal.browser_downloader import BrowserDownloader

downloader = BrowserDownloader(
    button_selectors=[
        "button:has-text('Tải tất cả')",
        "a:has-text('Tải tất cả')",
    ],
    page_load_timeout_ms=30000,
    wait_after_click_ms=8000,
    headless=False,
)

result = downloader.download(
    portal_url="https://dichvucong.ipvietnam.gov.vn/tra-cuu?so=53397",
    target_folder=Path.home() / "Downloads" / "cong-van-debug",
    access_code="eaf68de2849446a481472877dc83486a",
)

if result.success:
    for path in result.downloaded_paths:
        print(path)
else:
    print(result.notes)
```
