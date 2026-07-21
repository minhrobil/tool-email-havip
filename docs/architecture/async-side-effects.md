# Async Side Effects — Công Văn Processor

> Background jobs, timers, threads, event listeners, and scheduler scripts.
> Updated: 2026-05-05

---

## Background Threads

### 1. GUI Scan Launcher Thread (`src/gui/app.py:_do_scan()`)

```
CongVanApp._do_scan()
    └── threading.Thread(target=_thread, daemon=True).start()
            └── EmailProcessor.run(...)
```

- **Daemon:** Yes
- **Communication back to GUI:** `self.after(0, callback)` only
- **Purpose:** Keeps tkinter responsive while the full pipeline runs

### 2. Per-Email Worker Pool (`src/processor/email_processor.py:run()`)

```
EmailProcessor.run()
    └── ThreadPoolExecutor(max_workers=cfg.portal.parallel_downloads)
            ├── _process_one(msg #1)
            ├── _process_one(msg #2)
            └── ...
```

- **Concurrency control:** `cfg.portal.parallel_downloads` (default `5`)
- **Parallel work:** file acquisition + parsing
- **Serialized work:** Excel write + dedup register inside `self._write_lock`
- **Impact:** Portal/browser work can overlap across multiple emails in one scan

### 3. Auto-Scan Scheduler Thread (`src/gui/app.py:_start_scheduler()`)

```
CongVanApp._show_main()
    └── _start_scheduler()
            └── threading.Thread(target=_scheduler_loop, daemon=True).start()
                    └── while True:
                            time.sleep(30)
                            # If scheduled slot matches → self.after(0, self._do_auto_scan)
```

- **Daemon:** Yes
- **Poll interval:** 30 seconds
- **Fire condition:** `now.hour % freq_h == 0 AND now.minute < 2 AND slot not already fired`
- **Slot key:** `(day_of_year, hour)`

### 4. Interactive Login Thread (`src/auth/graph_auth.py:get_token_interactive_force()`)

```
GraphAuth.get_token_interactive_force()
    └── threading.Thread(target=_acquire, daemon=True).start()
            └── self._app.acquire_token_interactive(...)
```

- **Daemon:** Yes
- **Timeout:** 120 seconds
- **Countdown callback:** `on_tick(remaining_seconds)`

### 5. Excel Close Helper Thread (`src/gui/app.py:_ask_excel_locked()`)

```
self.after(0, _show)   → dialog on main thread
event.wait()           → worker thread blocks

User clicks "Đóng Excel & Thử lại":
    threading.Thread(target=_kill_and_signal, daemon=True).start()
        └── subprocess.run(["taskkill", "/IM", "EXCEL.EXE"])
            time.sleep(2.0)
            event.set()
```

- **Daemon:** Yes
- **Platform note:** Auto-close only works on Windows because it shells out to `taskkill`
- **Risk:** Kills all Excel processes for the current session

---

## Event Listeners

### Playwright Download Events (`src/portal/browser_downloader.py:_run()`)

```python
downloads_received = []
page.on("download", lambda d: downloads_received.append(d))
```

- **Registered on:** Each Playwright `page`
- **Lifetime:** Until `browser.close()`
- **Action:** Collects download handles for later `save_as()`

### GUI Progress Dispatch (`src/gui/app.py:_on_progress()`)

```python
self.after(0, lambda: self._update_step(message, current, total, stats))
self.after(0, lambda: self._append_log(message))
```

- **Purpose:** Safely cross the worker-thread → tkinter main-thread boundary
- **Rule:** No direct tkinter widget mutation from worker threads

---

## Timers / Waits

### Portal Page Load Timeout
- **Location:** `src/portal/browser_downloader.py:_run()`
- **Config:** `portal.page_load_timeout_ms` (default `30000` ms)
- **Code:** `page.goto(url, timeout=self._page_load_timeout, wait_until="networkidle")`
- **On timeout:** Falls back to `wait_for_load_state("domcontentloaded", timeout=5000)`

### Portal Download Wait
- **Location:** `src/portal/browser_downloader.py:_run()`
- **Config:** `portal.wait_after_click_ms` (default `8000` ms)
- **Code:** `page.wait_for_timeout(self._wait_after_click)`
- **Purpose:** Gives browser downloads time to start before fallback logic or save phase

### Excel Close Wait
- **Location:** `src/gui/app.py:_confirm_close_excel()` and `_ask_excel_locked()`
- **Duration:** 2 seconds
- **Purpose:** Let Excel release file handles before retrying write

### Login Countdown
- **Location:** `src/auth/graph_auth.py:get_token_interactive_force()`
- **Duration:** Up to 120 seconds
- **Code:** `done.wait(timeout=1.0)` inside a per-second polling loop

### Scheduler Poll Loop
- **Location:** `src/gui/app.py:_scheduler_loop()`
- **Duration:** 30-second sleep between checks
- **Purpose:** Avoid busy-waiting while still catching the first 2 minutes of each scheduled slot

---

## Subprocess / External Scheduler Calls

### `taskkill EXCEL.EXE`
- **Location:** `src/gui/app.py:_do_close_excel()`, `_ask_excel_locked()`
- **Command:** `subprocess.run(["taskkill", "/IM", "EXCEL.EXE"], capture_output=True, timeout=8)`
- **When:** User chooses automatic Excel close in GUI

### Open Export Folder
- **Location:** `src/gui/app.py:_open_folder_in_file_manager()`
- **Command on supported platform:** Windows `explorer`
- **Style:** Non-blocking via `subprocess.Popen(...)`

### Windows Task Scheduler Setup
- **Location:** `setup_scheduler.bat`, `packaging/windows/setup_scheduler.dist.bat`
- **Command:** `schtasks /create ...`
- **When:** User installs a daily Task Scheduler job for source or dist mode

---

## Practical Implications

- The tkinter GUI starts scan work on background threads.
- The actual heavy work is **not single-threaded**: `EmailProcessor.run()` fans out into a worker pool.
- Only the Excel write + dedup register phase is protected by `_write_lock`; download/parsing work remains concurrent by design.
