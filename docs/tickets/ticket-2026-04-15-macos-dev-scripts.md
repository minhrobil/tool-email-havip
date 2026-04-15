# Ticket: 2026-04-15 — macOS Dev Scripts and Windows Dist Scheduler

## Section 0 — Bắt buộc (Mandatory)

### 📋 Tiến độ xử lý (Work Progress)
- [x] 🔍 Xác định nguyên nhân gốc rễ
- [x] 🛠️ Triển khai fix trong code
- [ ] 🌐 Thêm key dịch thuật nếu cần
- [x] 🧪 Kiểm thử thủ công
- [x] 📄 Tài liệu ticket hoàn chỉnh

### 🎯 Các vấn đề cần giải quyết / Issues to Resolve
- [x] Repo đang thiên về launcher `.bat`, gây bất tiện khi dev hoàn toàn trên macOS
- [x] Chưa có `setup.sh` để tạo `.venv` và cài dependencies cho macOS
- [x] Default output còn trỏ đến thư mục mạng Windows thay vì `~/Desktop/CongVanExport`
- [x] Bản dist Windows chưa xuất sẵn `setup_scheduler.bat` phù hợp để người dùng cuối chạy ngay

---

## 1. Tóm tắt / Summary

**English:**
> The repository previously assumed Windows-centric launch scripts, which made everyday development awkward on macOS. It also kept a Windows network-share output path as the default, even though output folder selection is already configurable. At the same time, the Windows build output did not stage a scheduler helper tailored for the final `dist` layout.

**Tiếng Việt:**
> Repo trước đó thiên về các file chạy kiểu Windows, nên workflow dev trên macOS bị gượng. Default output vẫn trỏ tới network share Windows dù app đã có tính năng cấu hình output folder. Đồng thời bản build Windows chưa xuất sẵn file scheduler phù hợp với layout thật trong thư mục `dist`.

---

## 2. Nguyên nhân gốc rễ / Root Cause

**English:**
> The repo only shipped `.bat` launchers (`run.bat`, `run_headless.bat`, `setup_scheduler.bat`, `build.bat`). macOS development therefore had no first-class scripts. The default `output.root_folder` also pointed at a Windows-specific network share instead of the cross-platform local default. Also, `build.bat` produced the `.exe` but did not copy a scheduler helper into `dist\ToolXuLyMailCongVan\`.

**Tiếng Việt:**
> Repo chỉ có launcher `.bat`, gồm `run.bat`, `run_headless.bat`, `setup_scheduler.bat`, `build.bat`. Vì vậy dev trên macOS không có script native. Default `output.root_folder` cũng trỏ tới network share Windows thay vì local default cross-platform. Ngoài ra `build.bat` chỉ tạo `.exe` mà chưa copy helper scheduler vào `dist\ToolXuLyMailCongVan\`.

---

## 3. Giải pháp / Solution

**What changed and why:**

```bash
# Added for macOS dev
./setup.sh
./run.sh
./run_headless.sh
./setup_scheduler.sh
./build.sh
```

```bat
:: Added for Windows dist output
packaging\windows\run_headless.dist.bat
packaging\windows\setup_scheduler.dist.bat
```

`build.bat` now copies the dist-ready scheduler helpers into the final Windows output folder.

Default output now points to `~/Desktop/CongVanExport`; `load_config()` expands `~` before use.

---

## 4. Files Changed

| File | Change type | Description |
|---|---|---|
| `setup.sh` | Added | macOS first-time setup script that creates `.venv`, installs dependencies, installs Playwright Chromium, and runs tests |
| `run.sh` | Added | macOS GUI launcher for source development |
| `run_headless.sh` | Added | macOS headless launcher with logging |
| `setup_scheduler.sh` | Added | macOS `launchd` scheduler installer |
| `build.sh` | Added | macOS helper explaining Windows-only build flow |
| `packaging/windows/run_headless.dist.bat` | Added | Dist-ready Windows headless wrapper |
| `packaging/windows/setup_scheduler.dist.bat` | Added | Dist-ready Windows Task Scheduler installer |
| `config.json` | Modified | Changed default `output.root_folder` to `~/Desktop/CongVanExport` |
| `src/config.py` | Modified | Changed default output folder and expands `~` in output paths |
| `src/folder/routing.py` | Modified | Changed fallback output folder to `~/Desktop/CongVanExport` |
| `build.bat` | Modified | Copies Windows scheduler helpers into `dist` |
| `README.md` | Modified | Documents macOS dev flow and Windows dist scheduler flow |

---

## 5. Testing / Kiểm thử

**Manual test steps:**
1. Run `bash -n setup.sh run.sh run_headless.sh setup_scheduler.sh build.sh`
2. Confirm `build.bat` now copies `setup_scheduler.bat` and `run_headless.bat` into `dist\ToolXuLyMailCongVan\`
3. Confirm `load_config()` expands `~/Desktop/CongVanExport` to the user Desktop path
4. Review README sections for `macOS Dev` and Windows deployment flow

**Automated tests:**
```bash
N/A
```

**Expected result:** macOS has native dev scripts, while Windows dist output includes a scheduler script designed for the packaged layout.

---

## 6. Rủi ro / Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `launchctl` behavior can differ across macOS versions | Medium | `setup_scheduler.sh` uses standard LaunchAgents and prints a manual removal command |
| Windows batch scheduler still needs verification on a real Windows machine | Medium | Dist helper scripts are simple and path-local; final UAT should be done on Windows |

---

## 7. Code Reference

```bash
# macOS dev
./setup.sh
./run.sh
./setup_scheduler.sh
```

```bat
:: Windows dist
copy /y "packaging\windows\setup_scheduler.dist.bat" "dist\ToolXuLyMailCongVan\setup_scheduler.bat"
```

---

## 8. Related

- Related ticket: `docs/tickets/ticket-2026-04-15-batch-launcher-hardening.md`
- Related risk: `docs/architecture/async-side-effects.md` section `setup_scheduler.bat / schtasks`
- Related pattern: Pattern 4 in `docs/architecture/pattern-cookbook.md`
