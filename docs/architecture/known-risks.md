# Known Risks — Công Văn Processor

> Ranked list of fragile areas. Read before modifying any of these.
> Updated: 2026-05-05

---

## 🔴 Critical Risks

### RISK-001: Excel File Locked by User
- **Location:** `src/excel/writer.py:ExcelWriter._save()`
- **Risk:** If `SO CONG VAN DEN-LIENDO.xlsx` is open, `ExcelLockedError` is raised. GUI mode offers a retry flow, but headless mode has no user interaction. The email is **not** written and **not** registered in dedup, so it can be processed again on the next run.
- **Mitigation:** GUI pre-scan check + one in-scan retry. Headless mode only logs the failure.

### RISK-002: Wrong Date Folder Due to UTC/Local Time Mismatch
- **Location:** `src/folder/routing.py:get_date_folder_name()`
- **Risk:** Graph returns `receivedDateTime` in UTC. If UTC→local conversion is wrong, files land in the wrong day folder and dedup scope breaks.
- **Mitigation:** `to_local()` uses `astimezone(tz=None)` and all routing is based on `msg.received_datetime`, never `datetime.now()`.

### RISK-003: Portal HTML / Access-Code Flow Changes
- **Location:** `src/portal/browser_downloader.py`, `src/portal/url_extractor.py`
- **Risk:** The IP Vietnam portal can change button text, `.file-item__title` selectors, or access-code input fields. Portal download may fail even when the email itself is valid.
- **Mitigation:** Selectors are configurable in `config.json`; attachment fallback can still save the run if the email also has direct attachments.
- **Important nuance:** Portal failure does **not** always mean final status = `Cần kiểm tra`; the pipeline may still succeed through attachment fallback.

### RISK-004: `CLASSIFICATION_RULES` Ordering
- **Location:** `src/parser/rules.py:CLASSIFICATION_RULES`
- **Risk:** Rule order is first-match-wins. In particular, `"Từ chối hủy bỏ HLC"` must stay before `"Cấp toàn bộ"`.
- **Mitigation:** Preserve ordering comments and run parser tests after any change.

---

## 🟡 Medium Risks

### RISK-005: Dedup State Lives Outside the Export Folder
- **Location:** `src/dedup/manager.py`
- **Risk:** `_processed.json` is stored in `~/.tool_mail_cong_van/<date>/`, while Excel/PDF files live under the chosen export root. If the tool-state folder is deleted, dedup history is lost even though the export files still exist.
- **Mitigation:** Keep the tool-state directory backed up if dedup continuity matters.

### RISK-006: Playwright Chromium Not Installed
- **Location:** `src/portal/browser_downloader.py:download()`
- **Risk:** Portal downloads cannot run without Chromium. Source runs and packaged EXEs both depend on a Playwright browser install on the target machine.
- **Mitigation:** `setup.sh`, `build.bat`, and `.github/workflows/build.yml` install Chromium; README documents target-machine setup.

### RISK-007: Multi-PDF Selection Heuristic
- **Location:** `src/processor/email_processor.py:_find_main_pdf()`
- **Risk:** When multiple PDFs are present, the largest file is treated as the main document. That guess can be wrong.
- **Mitigation:** `strict_single_attachment=true` forces review for multi-file cases.

### RISK-008: Token Cache on Shared / Service Accounts
- **Location:** `src/auth/graph_auth.py`
- **Risk:** `Path.home()` changes with the user profile. On shared machines or service accounts, the token cache may end up in an unexpected home directory.
- **Mitigation:** Intended usage is per-user desktop execution, not shared service deployment.

### RISK-009: Output Folder Unavailable or Misconfigured
- **Location:** `src/config.py`, `src/folder/routing.py`
- **Risk:** `output.root_folder` may be missing or unwritable.
- **Mitigation:** All paths use `.expanduser()`, and `get_daily_folder()` falls back to `fallback_output_folder` or `~/Desktop/CongVanExport`.

### RISK-010: PyInstaller / GitHub Release Packaging Gap
- **Location:** `build.bat`, `.github/workflows/build.yml`, `packaging/windows/`
- **Risk:** PyInstaller bundles Python code but not Playwright Chromium. Also, the GitHub Release created by Actions uploads only `ToolXuLyMailCongVan.exe`, while helper `.bat` files are copied into `dist\ToolXuLyMailCongVan\` and the artifact.
- **Mitigation:** Target machines still need Chromium installed. If users need scheduler helpers, distribute the full dist folder/artifact, not just the release EXE.

---

## 🟢 Low Risks

### RISK-011: Large Email Batches Still Stress Auth / Portal Limits
- **Location:** `src/processor/email_processor.py:run()`, `src/graph/client.py`
- **Risk:** Processing is parallel (up to `parallel_downloads`, default `5`), not sequential. Large ranges can still hit Graph 429 responses, slow portal pages, or long-running scans.
- **Mitigation:** `GraphClient` retries HTTP 429; parallelism is configurable via `portal.parallel_downloads`.

### RISK-012: Parse Gaps Do Not Automatically Flip `run_status`
- **Location:** `src/processor/email_processor.py:_process_one()`, `_write_results()`
- **Risk:** Missing parsed fields (e.g. no `so_cong_van_num`, no deadline, no `nhan_hieu`) produce a red Excel row and increment `missing_data_count`, but `run_status` can still remain `OK` if file acquisition succeeded.
- **Mitigation:** Review both the `Lỗi` column and `missing_data_count`, not just `run_status`.

### RISK-013: Vietnamese Unicode Normalization
- **Location:** `src/parser/rules.py:normalize_text()`, `src/mail/reader.py:_norm()`
- **Risk:** NFD/NFC mismatches can break regexes or folder-name matching.
- **Mitigation:** Both parsing and folder lookup normalize to NFC before matching.

### RISK-014: Auto-Scan Behavior Depends on App Uptime
- **Location:** `src/gui/app.py:_scheduler_loop()`
- **Risk:** Auto-scan only runs while the GUI app is open. Launching the app exactly on a scheduled boundary is intentionally skipped once to avoid surprise immediate scans.
- **Mitigation:** Use OS-level schedulers (`setup_scheduler.sh`, `setup_scheduler.bat`) for unattended runs.

### RISK-015: Excel File Corruption Stops the Day’s Writes
- **Location:** `src/excel/writer.py:_load_or_create()`
- **Risk:** If the workbook becomes corrupted, `openpyxl.load_workbook()` fails and new rows cannot be appended.
- **Mitigation:** The tool surfaces an error instructing the user to rename or delete the broken file and start fresh.
