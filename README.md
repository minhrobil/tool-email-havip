# Công Văn Processor

Ứng dụng Windows đọc email từ Microsoft 365, tải công văn từ portal IP Vietnam hoặc attachment, phân tích PDF và ghi báo cáo Excel theo ngày.

## Yêu cầu

- Windows 10/11
- Python 3.10+ từ python.org, có Python Launcher (`py`) và Tkinter
- Azure App Registration có delegated permissions `Mail.Read` và `Mail.ReadBasic`

Tesseract OCR chỉ cần khi xử lý PDF scan. `setup.bat` sẽ thử cài bằng `winget` nếu máy chưa có.

## Chạy từ source trên Windows

Mở PowerShell tại thư mục project:

```powershell
cd "C:\Users\minh.nguyenq3\Documents\QuangMinh\Work\Code\HomeX\Repositories\tool-email-havip"
./setup.bat
```

`setup.bat` tạo `venv`, cài dependency, cài Playwright Chromium và chạy test. Sau đó kiểm tra `azure.client_id`, `mail.target_folder_name` và `output.root_folder` trong `config.json`.

Chạy GUI:

```powershell
./run.bat
```

Hoặc chạy trực tiếp để debug:

```powershell
./venv/Scripts/python.exe ./run_app.py
```

Lần đầu, bấm **Đăng nhập Microsoft** để tạo token cache, rồi bấm **Quét mail**.

Mỗi lần quét thành công sẽ xóa workbook của ngày liên quan và tạo lại Excel từ toàn bộ email tìm thấy; ứng dụng không append vào workbook của lần chạy trước.

## Chạy headless

Phải đăng nhập thành công bằng GUI ít nhất một lần trước khi chạy:

```powershell
./run_headless.bat
```

Chạy theo khoảng thời gian:

```powershell
./venv/Scripts/python.exe ./run_app.py --headless `
  --from-datetime "20/07/2026 00:00" `
  --to-datetime "20/07/2026 23:59"
```

Cài lịch chạy hằng ngày lúc 08:00 (mở PowerShell bằng quyền Administrator):

```powershell
./setup_scheduler.bat
```

Log của scheduler nằm tại `_scheduler_run.log` ở thư mục ứng dụng.

## Test và build

```powershell
# Test
./venv/Scripts/python.exe -m pytest tests -v

# Build bản Windows
./build.bat
```

Bản build nằm tại `dist\ToolXuLyMailCongVan\`. Khi deploy, copy toàn bộ thư mục này; không chỉ copy file `.exe`.

## Cấu hình chính

| Section | Ý nghĩa |
|---|---|
| `azure` | Azure client ID, tenant và Microsoft Graph scopes |
| `mail` | Tên thư mục Outlook và page size |
| `output` | Thư mục output, tên Excel và fallback folder |
| `processing` | Log level và quy tắc attachment |
| `portal` | URL portal, selector tải file, timeout, headless và số luồng tải |

Token được lưu tại `%USERPROFILE%\.tool_mail_cong_van\token_cache.bin`. Xóa file này nếu cần đăng nhập lại từ đầu.

## Lỗi thường gặp

| Lỗi | Cách xử lý |
|---|---|
| Không tìm thấy `venv` | Chạy `setup.bat` |
| Thiếu Playwright Chromium | Chạy `./venv/Scripts/python.exe -m playwright install chromium` |
| Headless báo chưa đăng nhập | Chạy `run.bat` và đăng nhập lại |
| Không tìm thấy thư mục Công văn | Kiểm tra `mail.target_folder_name` trong `config.json` |
| Không ghi được Excel | Đóng file Excel output đang mở |
| Output không truy cập được | Đổi `output.root_folder`; ứng dụng sẽ dùng fallback trên Desktop |

## Cấu trúc

```text
src/
  auth/       Microsoft login và token cache
  graph/      Microsoft Graph client
  mail/       Đọc email và attachment
  portal/     Tải tài liệu bằng Playwright
  parser/     Phân tích nội dung công văn
  folder/     Chọn thư mục output theo ngày nhận mail
  dedup/      Chống xử lý trùng
  excel/      Ghi báo cáo
  processor/  Điều phối pipeline
  gui/        Giao diện Tkinter
tests/        Automated tests
```

Chi tiết dành cho người bảo trì nằm trong `AGENTS.md` và `docs/architecture/`.
