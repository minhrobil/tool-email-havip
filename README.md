# 📬 Công Văn Processor

> Local Windows tool that automatically reads emails from Outlook Web / Microsoft 365,
> extracts portal links from the email body, uses browser automation to download documents,
> parses document fields, and writes daily reports to Excel.

---

## 🤖 AI Agents — Start Here

If you are an AI coding agent (GitHub Copilot, Claude, Cursor, ChatGPT, etc.) working on this repository:

1. **Read [`AGENTS.md`](./AGENTS.md) first** — architecture overview, pipeline, critical rules, pre-submit checklist.
2. **Use [`CLAUDE.md`](./CLAUDE.md)** — fast lookup: key files, access patterns, important commands.
3. **Check [`docs/architecture/pattern-cookbook.md`](./docs/architecture/pattern-cookbook.md)** — copy-paste templates for every common task.
4. **Check [`docs/tickets/`](./docs/tickets/)** — previous fixes in related areas before starting.
5. **Create a ticket file** from [`docs/tickets/_TEMPLATE.md`](./docs/tickets/_TEMPLATE.md) before writing any code.

| File | Purpose |
|---|---|
| [`AGENTS.md`](./AGENTS.md) | Full operating manual — READ THIS FIRST |
| [`CLAUDE.md`](./CLAUDE.md) | Quick reference — key files, access patterns |
| [`.github/copilot-instructions.md`](./.github/copilot-instructions.md) | Code style, naming, mandatory workflow rules |
| [`docs/architecture/feature-map.md`](./docs/architecture/feature-map.md) | Where every feature lives in the code |
| [`docs/architecture/data-flow.md`](./docs/architecture/data-flow.md) | Exact email → Excel pipeline |
| [`docs/architecture/pattern-cookbook.md`](./docs/architecture/pattern-cookbook.md) | 12 copy-paste patterns |
| [`docs/architecture/known-risks.md`](./docs/architecture/known-risks.md) | 15 ranked fragile areas |
| [`docs/architecture/api-map.md`](./docs/architecture/api-map.md) | Microsoft Graph endpoints used |
| [`docs/tickets/_TEMPLATE.md`](./docs/tickets/_TEMPLATE.md) | Template for new ticket docs |

---

## How It Works

Each email in the "Công văn" folder contains a **link to the IP Vietnam document portal**
(not a direct file attachment). The tool:

1. Reads the email body to extract the portal lookup URL
2. Opens the portal page automatically in a headless Chromium browser (Playwright)
3. Clicks the **"Tải tất cả"** button to download all document files
4. Saves the downloaded files to the correct daily folder
5. Parses the PDF to extract document fields (Số công văn, Số đơn, Deadline…)
6. Appends a row to the Excel file in that daily folder

**Fallback**: If no portal URL is found in the email body, the tool falls back to
checking for direct email attachments (configurable via `portal.fallback_to_attachments`).

---

## Quick Start (End Users)

1. **First-time setup**: Edit `config.json` → set your `azure.client_id` (see below)
2. **Install Playwright browser** (one-time): open a terminal and run:
   ```
   pip install playwright
   playwright install chromium
   ```
3. Double-click **`run.bat`** to open the application
4. Click **"🔑 Đăng nhập Microsoft"** → sign in once in the browser
5. Click **"📥 Quét mail"** to process emails
6. Click **"📂 Mở thư mục gốc"** to open the output folder in Explorer

After the first sign-in, you never need to sign in again (token cached automatically).

---

## Azure App Registration (one-time setup)

You need to register a free Azure AD application to allow the tool to read your mailbox.

1. Go to https://portal.azure.com → search "App registrations" → **New registration**
2. Name: `ToolXuLyMailCongVan` (any name)
3. Supported account types: **Accounts in any organizational directory and personal Microsoft accounts**
4. Redirect URI: select **"Mobile and desktop applications"** → enter `http://localhost`
5. Click **Register**
6. Copy the **Application (client) ID** → paste into `config.json` → `azure.client_id`
7. Go to **API permissions** → **Add a permission** → Microsoft Graph → Delegated permissions
   - Add: `Mail.Read`
   - Add: `Mail.ReadBasic`
8. Click **Grant admin consent** (or ask your IT admin)

---

## Configuration (`config.json`)

```json
{
  "azure": {
    "client_id": "YOUR_CLIENT_ID_HERE",
    "tenant_id": "common",
    "scopes": ["https://graph.microsoft.com/Mail.Read"]
  },
  "mail": {
    "target_folder_name": "Công văn",
    "page_size": 50
  },
  "output": {
    "root_folder": "\\\\LIENDO\\Havip - Tài liệu\\NHAN HIEU\\@Nhan hieu Vietnam\\Nhan cong van tu IPVN",
    "excel_filename": "SO CONG VAN DEN-LIENDO.xlsx",
    "date_folder_format": "%y.%m.%d"
  },
  "processing": {
    "strict_single_attachment": false,
    "log_level": "INFO"
  },
  "portal": {
    "url_patterns": ["ipvietnam.gov.vn", "dichvucong.ipvietnam"],
    "download_button_selectors": [
      "button:has-text('Tải tất cả')",
      "a:has-text('Tải tất cả')",
      "button:has-text('Tải xuống tất cả')"
    ],
    "page_load_timeout_ms": 15000,
    "wait_after_click_ms": 8000,
    "headless": true,
    "fallback_to_attachments": true
  }
}
```

### Portal config explained

| Key | Default | Description |
|-----|---------|-------------|
| `url_patterns` | `["ipvietnam.gov.vn"]` | Substrings that identify a portal URL in the email body |
| `download_button_selectors` | (see above) | CSS/text selectors tried in order to find the download button |
| `page_load_timeout_ms` | `15000` | Max ms to wait for page to load |
| `wait_after_click_ms` | `8000` | Time to wait after clicking for downloads to start |
| `headless` | `true` | `false` = show browser window (useful for debugging) |
| `fallback_to_attachments` | `true` | If no portal URL found, try direct email attachments |

---

## Output Structure

```
\\LIENDO\Havip - Tài liệu\NHAN HIEU\@Nhan hieu Vietnam\Nhan cong van tu IPVN\
└── 26.04.14\                          ← one folder per email received date
    ├── SO CONG VAN DEN-LIENDO.xlsx   ← Excel with DATA and META sheets
    ├── thong_bao_12345.pdf            ← downloaded from portal
    ├── _processed.json                ← deduplication registry
    └── _run.log                       ← processing log
```

### Excel Columns (DATA sheet)

| Column | Description |
|--------|-------------|
| Ngày nhận mail | Email received date |
| Thư mục ngày | Daily folder name |
| Tên mail (Subject) | Email subject |
| Người gửi | Sender name and email |
| Tên attachment | Downloaded file name(s) |
| Số công văn | e.g. `53397/SHTT-NH.IP` |
| Loại công văn | Classified type (Dự định từ chối, Cấp toàn bộ, …) |
| Ngày issue công văn | Document date |
| Số tháng deadline | e.g. `2` or `3` |
| Deadline trả lời Cục | Calculated reply deadline |
| Số đơn | e.g. `4-2025-20619` |
| Loại hình đơn | Nhãn hiệu / Sáng chế / … |
| Nội dung công văn | First substantive paragraph |
| Trạng thái xử lý | OK / Cần kiểm tra |
| Ghi chú lỗi | Parsing warnings |
| Message ID | Email identifier for traceability |

---

## Building a Standalone .exe

```bat
build.bat
```

Output: `dist\ToolXuLyMailCongVan\ToolXuLyMailCongVan.exe`

**Note**: Playwright's Chromium browser must be separately installed on the target machine:
```bat
playwright install chromium
```
Or copy `%LOCALAPPDATA%\ms-playwright\` from the build machine.

---

## Deploying the .exe to Another Machine

Sau khi build, copy toàn bộ thư mục `dist\ToolXuLyMailCongVan\` sang máy đích.

| Việc | Dùng Python (source) | Dùng `.exe` (deploy) |
|---|---|---|
| Chạy GUI | `run.bat` | `ToolXuLyMailCongVan.exe` |
| Đăng nhập lần đầu | `run.bat` → click Đăng nhập | `ToolXuLyMailCongVan.exe` → click Đăng nhập |
| Chạy headless thủ công | `run_headless.bat` | `ToolXuLyMailCongVan.exe --headless` |
| Cài schedule tự động | `setup_scheduler.bat` | `setup_scheduler.bat` (tự dùng `.exe` nếu đã build) |
| Cần Python? | ✅ Có | ❌ Không |

> **`setup_scheduler.bat` tự phát hiện**: nếu `.exe` đã tồn tại trong `dist\`, scheduler sẽ
> gọi `ToolXuLyMailCongVan.exe --headless` thay vì `run_headless.bat`.

---

## Automatic Daily Execution (Task Scheduler)

1. Đăng nhập lần đầu bằng cách chạy GUI (`run.bat` hoặc `ToolXuLyMailCongVan.exe`) → click **"Đăng nhập Microsoft"**
2. Right-click **`setup_scheduler.bat`** → **Run as administrator**
3. The tool will automatically run at 08:00 every day

To manually trigger: right-click **`run_headless.bat`** → Run (hoặc chạy `ToolXuLyMailCongVan.exe --headless`)  
To view logs: open `_scheduler_run.log` in the application folder

---

## Running Tests

```bat
pip install pytest python-dateutil
python -m pytest tests/ -v
```

Tests cover: parser rules, dedup logic, folder routing, and portal URL extraction.

---

## File Acquisition Flow

```
Email received
    │
    ▼
Extract portal URL from body_html / body_text
    │
    ├── URL found ──► Open in headless Chromium
    │                     │
    │                     ▼
    │               Wait for page load
    │                     │
    │                     ▼
    │               Click "Tải tất cả" button
    │                     │
    │                     ├── Success ──► Save files to daily folder
    │                     │
    │                     └── Failure ──► Mark "Cần kiểm tra" + notes
    │
    └── No URL found
            │
            ├── fallback_to_attachments = true
            │       └── Check direct email attachments
            │                │
            │                ├── Has attachments ──► Download to daily folder
            │                └── No attachments  ──► "Cần kiểm tra"
            │
            └── fallback_to_attachments = false ──► "Cần kiểm tra"
```

---

## Document Type Classification Rules

| Loại công văn | Keyword phrases required |
|---|---|
| Dự định từ chối | "dự định từ chối" |
| Từ chối toàn bộ | "từ chối cấp" + "toàn bộ" |
| Từ chối một phần | "từ chối cấp" |
| Cấp toàn bộ | "đáp ứng các điều kiện bảo hộ" |
| KQTĐ nội dung | "kết quả thẩm định nội dung" |
| KQTĐ hình thức | "kết quả thẩm định hình thức" |

To add a new rule: edit `src/parser/rules.py` → `CLASSIFICATION_RULES` list.

---

## Deduplication Logic

Within each daily folder (priority order):

1. `internetMessageId` (RFC 2822) — most reliable
2. Graph `message.id`
3. `date_folder + so_don`
4. `date_folder + downloaded_filename`

---

## Troubleshooting

| Symptom | Solution |
|---------|----------|
| "Playwright chưa cài đặt" | Run: `pip install playwright && playwright install chromium` |
| "Không tìm thấy nút 'Tải tất cả'" | Check `portal.download_button_selectors`; set `headless: false` to see what the page looks like |
| "Trang portal trả về lỗi" | The portal link may be expired; check the email manually |
| "Không tìm thấy link portal" | The URL patterns may not match; check `portal.url_patterns` in config.json |
| "config.json not found" | Place `config.json` next to `run.bat` / `.exe` |
| "azure.client_id is not set" | Set your Azure App client_id in `config.json` |
| "Không tìm thấy thư mục Công văn" | Check folder name in Outlook Web; update `mail.target_folder_name` |
| "Cannot save Excel — file may be open" | Close the Excel file and re-run |
| Network folder unreachable | Reconnect VPN/LAN; check `\\LIENDO` is accessible |
| Token expired in headless mode | Run `run.bat` once to refresh login |

---

## Project Structure

```
mail-extract/
├── src/
│   ├── config.py                   Configuration loader (includes PortalConfig)
│   ├── main.py                     Entry point (GUI + headless)
│   ├── auth/graph_auth.py          MSAL OAuth, token cache
│   ├── graph/client.py             Graph API HTTP client
│   ├── mail/reader.py              Folder discovery, message retrieval (incl. body)
│   ├── mail/downloader.py          Direct attachment download (fallback)
│   ├── portal/url_extractor.py     Extract portal URL from email HTML/text body
│   ├── portal/browser_downloader.py  Playwright: open portal, click "Tải tất cả"
│   ├── parser/rules.py             Vietnamese document parser (regex)
│   ├── excel/writer.py             Excel writer (openpyxl)
│   ├── dedup/manager.py            Deduplication (_processed.json)
│   ├── folder/routing.py           Daily folder routing
│   ├── processor/email_processor.py  Main pipeline orchestrator
│   └── gui/app.py                  tkinter GUI
├── tests/
│   ├── test_parser.py
│   ├── test_dedup.py
│   ├── test_folder_routing.py
│   └── test_portal_extractor.py    ← NEW
├── config.json                     ← Edit this (includes portal section)
├── requirements.txt                ← includes playwright
├── run.bat                         Launch GUI
├── run_headless.bat                Launch headless (Task Scheduler)
├── setup_scheduler.bat             Register daily task
└── build.bat                       Build .exe
```
