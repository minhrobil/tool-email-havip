# Ticket: 2026-04-15 — Batch Launcher Hardening

## Section 0 — Bắt buộc (Mandatory)

### 📋 Tiến độ xử lý (Work Progress)
- [x] 🔍 Xác định nguyên nhân gốc rễ
- [x] 🛠️ Triển khai fix trong code
- [ ] 🌐 Thêm key dịch thuật nếu cần
- [x] 🧪 Kiểm thử thủ công
- [x] 📄 Tài liệu ticket hoàn chỉnh

- [x] `setup.bat`, `run.bat` và `run_headless.bat` đang phụ thuộc cứng vào một đường dẫn Python cố định hoặc logic dò Python cũ
- [x] `setup_scheduler.bat` phức tạp hơn mức cần thiết cho source tree và dễ vướng quoting
- [x] Windows `.exe` build cần copy `config.json` ra cạnh executable để người dùng chỉnh cấu hình sau khi deploy

---

## 1. Tóm tắt / Summary

**English:**
> The Windows source scripts were fragile and too Windows-dev oriented. `setup.bat` hardcoded a Python install path, while `run.bat` and `run_headless.bat` tried to resolve multiple Python locations even though source development is now macOS-first. Task Scheduler setup also needed safer quoting for paths with spaces, and the Windows `.exe` build needed an editable `config.json` next to the executable.

**Tiếng Việt:**
> Các file batch source trên Windows còn khá mong manh và thiên về dev Windows. `setup.bat` hardcode đường dẫn Python, còn `run.bat` và `run_headless.bat` dò nhiều vị trí Python dù source development hiện đã macOS-first. Phần Task Scheduler cũng cần quoting an toàn hơn cho path có khoảng trắng, và bản build `.exe` cần có `config.json` chỉnh được nằm cạnh executable.

---

## 2. Nguyên nhân gốc rễ / Root Cause

**English:**
> `setup.bat` used `C:\Program Files\Python312\python.exe` directly. `run.bat` and `run_headless.bat` used broader Python resolution logic that is no longer needed for macOS-first development. `setup_scheduler.bat` tried to auto-detect multiple execution modes instead of just scheduling the source-tree `run_headless.bat`, which made quoting and maintenance more fragile. PyInstaller's internal data placement also cannot be relied on as the editable config location for end users.

**Tiếng Việt:**
> `setup.bat` dùng trực tiếp `C:\Program Files\Python312\python.exe`. `run.bat` và `run_headless.bat` dùng logic dò Python rộng không còn cần thiết khi dev chính là macOS. `setup_scheduler.bat` cố auto-detect nhiều mode chạy thay vì chỉ schedule `run_headless.bat` của source tree, làm script khó bảo trì hơn. Vị trí data nội bộ của PyInstaller cũng không nên được xem là vị trí config chỉnh được cho người dùng cuối.

Example:
```
File: setup.bat
Issue: Python path was hardcoded to C:\Program Files\Python312\python.exe.

File: run.bat
Issue: Python detection was unnecessary for macOS-first source development.

File: run_headless.bat
Issue: Headless launcher used the same narrow Python assumptions.

File: setup_scheduler.bat
Issue: Source-tree scheduler logic was more complex than needed.

File: build.bat / src/config.py
Issue: Frozen Windows app could miss the editable config beside the .exe.
```

---

## 3. Giải pháp / Solution

**What changed and why:**

```bat
:: Before
set PYTHON="C:\Program Files\Python312\python.exe"

:: After
set "PYTHON=py -3"
set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"
call "%PYTHON_EXE%" run_app.py %*
```

```bat
:: Before
set TASK_CMD=...

:: After
set "HEADLESS_BAT=%~dp0run_headless.bat"
set "TASK_CMD=%COMSPEC% /d /c ""%HEADLESS_BAT%"""
schtasks /create /tr "%TASK_CMD%" ...
```

```bat
:: Windows dist build
copy /y "config.json" "dist\ToolXuLyMailCongVan\config.json"
```

---

## 4. Files Changed

| File | Change type | Description |
|---|---|---|
| `setup.bat` | Modified | Removed hardcoded `C:\Program Files\Python312\python.exe`; marked as legacy Windows source setup |
| `run.bat` | Modified | Removed broad Python lookup; uses only `venv\Scripts\python.exe` for legacy Windows source runs |
| `run_headless.bat` | Modified | Removed broad Python lookup; uses only `venv\Scripts\python.exe` for legacy Windows source runs |
| `setup_scheduler.bat` | Modified | Simplified source-tree scheduler and executes `run_headless.bat` through `cmd.exe /d /c` for safer quoting |
| `build.bat` | Modified | Uses `venv\Scripts\python.exe`, removes global tool assumptions, validates packaging templates, and copies editable `config.json` to dist |
| `packaging/windows/setup_scheduler.dist.bat` | Modified | Uses `cmd.exe /d /c` for safer scheduled execution from dist folders with spaces |
| `src/config.py` | Modified | Searches the frozen `.exe` directory first when loading `config.json` |
| `docs/tickets/ticket-2026-04-15-batch-launcher-hardening.md` | Added | Recorded root cause, fix, and verification notes |

---

## 5. Testing / Kiểm thử

**Manual test steps:**
1. Review `setup.bat` to confirm the hardcoded Python install path was removed
2. Review `run.bat` and `run_headless.bat` to confirm they no longer perform broad Python lookup
3. Review `setup_scheduler.bat` and `packaging/windows/setup_scheduler.dist.bat` to confirm scheduled actions go through `%COMSPEC% /d /c`
4. Attempted local shell validation on macOS; Windows `cmd` is not available in this environment

**Automated tests:**
```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/ -v
```

**Result:** `109 passed`. Source-tree and dist Windows launcher scripts are simpler and safer, but final behavioral verification must still be done on a real Windows machine.

---

## 6. Rủi ro / Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Windows batch quoting may still behave differently across shells | Medium | Final verification should be done with `cmd.exe` and Task Scheduler on Windows |
| `py` launcher may be absent on some Windows machines | Low | `setup.bat` is legacy only; macOS dev uses `setup.sh` |
| Playwright Chromium may be missing on the target Windows machine | Medium | Build output still documents installing Chromium or copying `%LOCALAPPDATA%\ms-playwright` |

---

## 7. Code Reference

```bat
:: run.bat
call "%PYTHON_EXE%" run_app.py %*

:: setup_scheduler.bat
schtasks /create /tr "%TASK_CMD%" ...
```

---

## 8. Related

- Related ticket: [none]
- Related risk: `docs/architecture/async-side-effects.md` section `setup_scheduler.bat / schtasks`
- Related pattern: [none]
