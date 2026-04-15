You are a senior Windows automation engineer and Python desktop tool developer.

Your task is to design and implement a LOCAL Windows tool that automatically reads emails from Outlook Web / Microsoft 365 mailbox, downloads attachments, parses data from email/PDF attachments, and writes daily results into Excel files in a network folder.

Important:
- The end users are low-tech.
- The tool must be very easy to use.
- The tool must run on a personal Windows machine.
- The tool must support automatic scheduled execution every day.
- The tool must be robust, idempotent, and safe for repeated runs.

==================================================
1. BUSINESS GOAL
   ==================================================

Build a local Windows tool that:

1. Connects to the user's Microsoft 365 / Outlook Web mailbox
2. Finds the mail folder named "Công văn" WITHOUT case sensitivity
    - Examples that should match:
        - "Công văn"
        - "công văn"
        - "CÔNG VĂN"
3. Reads ALL emails in that folder
4. For each email:
    - determine the email received date
    - create or use the corresponding daily folder based on the email received date
    - download ALL attachments into that daily folder
    - parse data from the email and/or the main PDF attachment
    - create or append to an Excel file in that daily folder
5. Deduplicate within the same day
6. Support running multiple times per day safely without creating duplicates
7. Be easy for low-tech users:
    - ideally packaged as a .exe
    - minimal UI
    - clear logs
    - no terminal usage required

==================================================
2. TARGET ENVIRONMENT
   ==================================================

- OS: Windows
- Mail system: Outlook Web / Microsoft 365 (NOT Outlook desktop dependency)
- Access method: Microsoft Graph API with OAuth sign-in for desktop app
- Network storage root folder:

\\LIENDO\Havip - Tài liệu\NHAN HIEU\@Nhan hieu Vietnam\Nhan cong van tu IPVN\

- The tool runs locally on the user's Windows machine
- The machine may be used by low-tech users
- The tool should be schedulable via Windows Task Scheduler

==================================================
3. FIXED BUSINESS RULES
   ==================================================

These rules are FINAL and must be implemented exactly unless impossible:

1. Mail source folder
    - Read emails only from folder named "Công văn"
    - Folder name search must be case-insensitive

2. Scope of mail
    - Read ALL emails in that folder

3. Attachments
    - Download ALL attachments from each email

4. Processing assumption
    - 1 email = 1 đơn = 1 attachment
    - However, since the requirement also says download ALL attachments, implement this safely:
        - always download all attachments
        - but for import/parsing logic:
            - if exactly 1 attachment: process normally
            - if 0 attachments: mark as error / needs review
            - if more than 1 attachment: still download all, but mark as needs review unless there is a clearly identifiable main file according to a deterministic rule

5. Daily folder logic
    - Must detect the email RECEIVED DATE
    - Must work on the folder of that RECEIVED DATE
    - Folder format: yy.MM.dd
    - Example:
        - email received on 2026-04-14 -> folder "26.04.14"

6. Excel output
    - Inside each daily folder, create or update an Excel file named:
      SO CONG VAN DEN-LIENDO.xlsx
    - If file does not exist, create it
    - If file exists, append new rows

7. Deduplication
    - Deduplicate WITHIN THE SAME DAY
    - Re-running the tool many times in one day must not create duplicate rows for already processed emails of that same daily folder

==================================================
4. FUNCTIONAL REQUIREMENTS
   ==================================================

Implement the following modules.

A. Authentication
- Use Microsoft Graph OAuth login for desktop app
- The first run should allow user sign-in via browser
- Cache token locally securely enough for desktop usage
- Reuse cached token in later runs
- If token expired, refresh or ask user to sign in again gracefully

B. Mail folder discovery
- Find the folder "Công văn" case-insensitively
- Support nested folder traversal if necessary
- If multiple folders match case-insensitively, log warning and use the best exact match first, otherwise first deterministic match

C. Mail retrieval
- Read all emails in that folder
- Retrieve enough fields:
    - message id
    - internet message id if available
    - subject
    - sender
    - receivedDateTime
    - body preview/body if needed
    - attachments metadata

D. Daily folder routing
- For each email, compute the target folder path from receivedDateTime
- Example target path:
  \\LIENDO\Havip - Tài liệu\NHAN HIEU\@Nhan hieu Vietnam\Nhan cong van tu IPVN\26.04.14\
- Create folder if not exists

E. Attachment download
- Download all attachments for each email into the target daily folder
- Ensure stable file naming and avoid overwrite collisions
- If filename already exists, create deterministic suffix, not random chaos
- Prefer preserving original filename if possible

F. Data parsing
Extract as much as possible from email and especially PDF attachment.

Expected fields:
- Ngày nhận mail
- Thư mục ngày
- Tên mail / subject
- Người gửi
- Tên attachment
- Số công văn
- Loại công văn
- Ngày issue công văn
- Số tháng deadline
- Deadline trả lời Cục
- Số đơn
- Loại hình đơn
- Nội dung công văn
- Trạng thái xử lý
- Ghi chú lỗi
- Message ID

For parsing:
- Prefer deterministic rule-based parsing
- No AI/LLM required
- Use PDF text extraction libraries
- Use regex / pattern matching / keyword rules
- Must be maintainable and configurable

G. Excel writing
- In each daily folder, create/update:
  SO CONG VAN DEN-LIENDO.xlsx
- Append rows safely
- Preserve previous rows
- If new file is created, create a proper header row
- Consider 2 sheets:
    1. DATA
    2. META
- DATA stores business rows
- META stores processing metadata / dedup keys / run info

H. Dedup logic
Dedup only within same daily folder/day.

Use layered dedup:
1. technical key
    - internetMessageId if available
    - fallback to Graph message id
2. business key
    - date_folder + so_don
    - fallback to date_folder + attachment_filename

Rules:
- if technical key already exists in that day's processed registry => skip
- if technical key absent but business key already exists in same day => skip or mark suspected duplicate
- tool must be idempotent for repeated runs

I. Logs and error handling
Need simple user-friendly logging:
- success count
- skipped duplicate count
- needs review count
- errors count

Also save logs per daily folder, for example:
- _processed.json
- _error.log
- _run.log

J. Automatic daily execution
- The app itself should support normal manual run
- Also prepare it so it can be triggered by Windows Task Scheduler
- Must be safe if run multiple times a day

==================================================
5. PARSING RULES
   ==================================================

Start with deterministic parsing from known document patterns like these examples:

Examples of content patterns:
- "Số: 53397/SHTT-NH.IP"
- "Hà Nội, ngày 13 tháng 04 năm 2026"
- "Số yêu cầu: CĐ4-2026-00098"
- "Số đơn: 4-2025-20619"
- "Số đơn: 4-2025-22677"
- "Trong thời hạn 02 tháng kể từ ngày ra thông báo này"
- "Trong thời hạn 03 tháng kể từ ngày ký công văn này"
- document types like:
    - dự định từ chối
    - từ chối toàn bộ
    - cấp toàn bộ
    - thông báo kết quả thẩm định nội dung
    - thông báo kết quả thẩm định đơn yêu cầu ghi nhận thay đổi...

Implement parse helpers for:
- so_cong_van
- issue_date
- so_don
- so_yeu_cau if present
- deadline_months
- deadline_date (calculate from issue date + deadline months if possible)
- loai_cong_van
- noi_dung_cong_van
- loai_hinh_don if detectable from content/pattern

Parsing requirements:
- Write robust regex with Vietnamese text in mind
- Normalize whitespace
- Handle OCR-like spacing variations where reasonable
- Keep parsing code modular and testable

Deadline logic:
- If text says "Trong thời hạn 02 tháng kể từ ngày ra thông báo này", parse deadline_months = 2
- If text says "Trong thời hạn 03 tháng kể từ ngày ký công văn này", parse deadline_months = 3
- Then calculate deadline date from issue date if issue date exists
- Clearly document whether the calculation is exact calendar month addition

Document classification suggestions:
- If content contains phrases indicating "dự định từ chối" -> classify accordingly
- If content indicates "từ chối cấp ... đối với toàn bộ ..." -> classify "Từ chối toàn bộ"
- If content indicates "đáp ứng các điều kiện bảo hộ" and asks to pay fee -> classify "Cấp toàn bộ"
- Make classification rule-based and easy to extend

==================================================
6. FILE AND FOLDER DESIGN
   ==================================================

Daily folder example:

\\LIENDO\Havip - Tài liệu\NHAN HIEU\@Nhan hieu Vietnam\Nhan cong van tu IPVN\26.04.14\

Suggested contents:
- SO CONG VAN DEN-LIENDO.xlsx
- downloaded attachments
- _processed.json
- _run.log
- _error.log

Requirements:
- Create folders automatically
- Never write files into wrong date folder
- Date folder must always come from email received date, NOT current run date

==================================================
7. UX REQUIREMENTS FOR LOW-TECH USERS
   ==================================================

Build with low-tech users in mind.

Preferred UX:
- package as Windows executable
- tiny GUI with very few actions

Suggested UI:
- button: "Đăng nhập Microsoft"
- button: "Quét mail"
- button: "Mở thư mục gốc"
- status area / log text box
- optional checkbox or setting: "Tự chạy bằng Task Scheduler"

Manual usage should be:
1. User opens app
2. Clicks sign in once
3. Later only clicks "Quét mail" if needed
4. Daily automation can run without user interaction if token still valid

No command-line requirement for normal users.

==================================================
8. NON-FUNCTIONAL REQUIREMENTS
   ==================================================

- Idempotent
- Maintainable
- Modular
- Clear separation of:
    - Graph client
    - folder discovery
    - attachment handling
    - parsing
    - dedup
    - Excel writing
    - config
    - UI
- Good error handling
- Unicode-safe for Vietnamese paths and filenames
- Works with network path
- Avoid data corruption in Excel
- Use safe write/update patterns
- Use deterministic logic, not brittle hacks

==================================================
9. IMPLEMENTATION PREFERENCES
   ==================================================

Preferred language:
- Python

Suggested libraries:
- msal for Microsoft login
- requests / httpx for Graph API
- PyMuPDF or pdfplumber for PDF text extraction
- openpyxl for Excel
- tkinter or customtkinter for simple GUI
- pathlib, json, logging, re, datetime
- dateutil for month arithmetic
- pyinstaller for packaging .exe

Do NOT depend on Outlook desktop COM because the user uses Outlook Web.

==================================================
10. CONFIGURATION REQUIREMENTS
    ==================================================

Provide a config file, for example config.json, containing:
- tenant/app config if needed
- root output folder
- target mail folder name = "Công văn"
- Excel filename = "SO CONG VAN DEN-LIENDO.xlsx"
- date folder format = "%y.%m.%d"
- whether exact-1-attachment mode is strict
- Graph query page size
- log level

Make config easy to edit.

==================================================
11. OUTPUT EXPECTATIONS
    ==================================================

I want you to produce:

1. A proposed architecture
2. Project folder structure
3. Detailed implementation plan
4. The actual Python code
5. Config sample
6. Example parsing rules
7. Excel schema
8. Dedup design
9. Logging strategy
10. Packaging instructions for Windows .exe
11. Task Scheduler setup instructions
12. Basic tests for parser/dedup/date folder logic
13. Notes for future extension

==================================================
12. IMPORTANT EDGE CASES
    ==================================================

Handle these carefully:

- folder "Công văn" not found
- multiple matching folders by case-insensitive comparison
- email has 0 attachments
- email has >1 attachments
- attachment filename duplicates existing file
- PDF has no extractable text
- mail parse succeeds but PDF parse fails
- issue date missing
- so_don missing
- duplicate email reprocessed in same day
- tool run today processes an older email from previous date
- network path temporarily unavailable
- Excel file locked/opened by user
- token expired
- Unicode Vietnamese path/file issues

==================================================
13. CODING STYLE
    ==================================================

- Write production-minded code
- Prefer readable code over clever code
- Use typed functions where reasonable
- Add comments only where useful
- Avoid giant monolithic functions
- Keep parsing logic isolated and testable
- Make the business rules explicit in code
- Include sample unit tests for key logic

==================================================
14. DO NOT DO THESE
    ==================================================

- Do not use AI/LLM for parsing
- Do not require terminal usage for end users
- Do not depend on Outlook desktop app
- Do not hardcode current date for folder routing
- Do not create duplicates on repeated runs
- Do not ignore Vietnamese filename/path issues
- Do not silently swallow errors

==================================================
15. DELIVERY FORMAT
    ==================================================

Please deliver in this order:

A. Restate the business requirements briefly
B. Propose the architecture
C. Show project structure
D. Explain key technical decisions
E. Implement the code files one by one
F. Provide sample config
G. Provide setup and packaging instructions
H. Provide Task Scheduler instructions
I. Provide test cases
J. Mention limitations and next-step improvements

If something is ambiguous, choose the safest deterministic implementation and clearly document the assumption instead of asking unnecessary questions.