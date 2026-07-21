# Công Văn Processor — Maintenance Notes

## Tổng quan

- Windows desktop tool, Python 3.10+, Tkinter.
- Entry point: `run_app.py` → `src/main.py`.
- Cấu hình duy nhất: `config.json`, load bởi `src/config.py`.
- Pipeline: Microsoft Graph → portal/attachment → parser → dedup → Excel.
- Chạy test: `venv\Scripts\python.exe -m pytest tests -v`.

## File quan trọng

- `src/processor/email_processor.py`: thứ tự pipeline và write lock.
- `src/dedup/manager.py`: chiến lược chống trùng.
- `src/folder/routing.py`: đổi UTC sang local và chọn folder ngày.
- `src/excel/writer.py`: thứ tự cột DATA/META.
- `src/parser/rules.py`: classification rule; first match wins.
- `src/gui/app.py`: GUI và worker thread.

Đọc toàn bộ file liên quan trước khi sửa. Tài liệu chi tiết nằm trong `docs/architecture/`.

## Invariant bắt buộc

1. Folder output phải dựa trên `message.received_datetime`, không dùng thời điểm chạy.
2. Mỗi scan tạo mới Excel và dedup state của ngày liên quan; không append workbook cũ. Index được dựng lại 1..N theo vị trí email trong toàn bộ kết quả quét, không reset theo ngày và không phụ thuộc số file tải thành công.
3. Email khác nhưng trùng file vẫn có dòng Excel riêng, ghi rõ dòng gốc.
4. Excel write và dedup register phải cùng nằm trong `_write_lock`; tải file nằm ngoài lock.
5. Worker thread chỉ cập nhật Tkinter qua `self.after(...)`.
6. Luôn xử lý `ExcelLockedError` khi ghi Excel.
7. Thứ tự lấy file là portal trước, attachment fallback sau.
8. Dedup state nằm dưới `%USERPROFILE%\.tool_mail_cong_van\`, không đặt trên network output.
9. Không hardcode credentials, folder hay selector; đưa vào `config.json`.

## Quy ước thay đổi

- Giữ diff nhỏ và theo pattern hiện có.
- Dùng type hints, module logger và tiếng Việt có dấu.
- Khi thêm cột Excel, cập nhật cả column list và row mapping.
- Khi thêm rule parser, kiểm tra thứ tự rule và bổ sung test.
- Playwright browser/context phải luôn được đóng.
- Chạy toàn bộ test trước khi bàn giao.
