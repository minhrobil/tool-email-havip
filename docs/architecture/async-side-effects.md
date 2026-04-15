# Async Side Effects — Công Văn Processor

> Background jobs, timers, threads, and event listeners.
> Updated: 2026-04-15

---

## Background Threads

### 1. Scan Worker Thread (`src/gui/app.py:_do_scan()`)

```
CongVanApp._do_scan()
    └── threading.Thread(target=_thread, daemon=True).start()
            │
            └── EmailProcessor.run(...)
                    │  [Runs entire pipeline — auth, fetch, process, write]
                    │
                    ├── self._running = True   (set before thread start)
                    └── self._running = False  (set in finally block)
```

- **Daemon:** Yes — killed when main window closes
- **Communication back to GUI:** `self.after(0, callback)` only
- **Duration:** Seconds to minutes depending on email count and portal speed

### 2. Auto-Scan Scheduler Thread (`src/gui/app.py:_start_scheduler()`)

```
CongVanApp._show_main()
    └── _start_scheduler()
            └── threading.Thread(target=_scheduler_loop, daemon=True).start()
                    │
                    └── while True:
                            time.sleep(30)
                            # Check if scan should fire (hour % freq == 0, minute < 2)
                            # If yes: self.after(0, self._do_auto_scan)
```

- **Daemon:** Yes
- **Poll interval:** 30 seconds
- **Fire condition:** `now.hour % freq_h == 0 AND now.minute < 2 AND slot not already fired`
- **Slot key:** `(day_of_year, hour)` — one fire per scheduled hour per day

### 3. Interactive Login Thread (`src/auth/graph_auth.py:get_token_interactive_force()`)

```
GraphAuth.get_token_interactive_force()
    └── threading.Thread(target=_acquire, daemon=True).start()
            │
            └── self._app.acquire_token_interactive(...)  [opens browser]
                    │
                    └── done.set()  (threading.Event)

# Main calling thread polls done.wait(timeout=1.0) every second
# Fires on_tick(remaining) countdown callback each second
# Gives up after timeout_seconds (default 120)
```

- **Daemon:** Yes
- **Timeout:** 120 seconds
- **Countdown callback:** `on_tick(remaining_seconds)` — used by GUI to show countdown

### 4. Excel Close Thread (`src/gui/app.py:_ask_excel_locked()`)

```
When Excel is locked during scan:
    self.after(0, _show)  → shows dialog on main thread
    event.wait()          → blocks worker thread

User clicks "Đóng Excel & Thử lại":
    threading.Thread(target=_kill_and_signal, daemon=True).start()
        └── subprocess.run(["taskkill", "/IM", "EXCEL.EXE"])
            time.sleep(2.0)
            result[0] = True
            event.set()         ← unblocks worker thread
```

---

## Event Listeners

### Playwright Download Events (`src/portal/browser_downloader.py:_run()`)

```python
downloads_received = []
page.on("download", lambda d: downloads_received.append(d))
```

- **Registered on:** Each `page` instance, inside `sync_playwright()` context
- **Duration:** Lives until `browser.close()`
- **Action:** Appends `Download` objects to list
- **Cleanup:** Browser context closed in all paths (success, error, timeout)

---

## Timers / Waits

### Portal Page Load Timeout
- **Location:** `src/portal/browser_downloader.py:_run()`
- **Config:** `portal.page_load_timeout_ms` (default 15000 ms)
- **Code:** `page.goto(url, timeout=self._page_load_timeout, wait_until="networkidle")`
- **On timeout:** `PWTimeout` caught → falls back to `wait_for_load_state("domcontentloaded", timeout=5000)`

### Portal Download Wait
- **Location:** `src/portal/browser_downloader.py:_run()`
- **Config:** `portal.wait_after_click_ms` (default 8000 ms)
- **Code:** `page.wait_for_timeout(self._wait_after_click)`
- **Purpose:** Waits after clicking download button for all downloads to START (save_as blocks for completion)

### Excel Close Wait
- **Location:** `src/gui/app.py:_confirm_close_excel()` and `_ask_excel_locked()`
- **Duration:** 2 seconds after `taskkill EXCEL.EXE`
- **Code:** `dlg.after(2000, _finish)` or `time.sleep(2.0)`
- **Purpose:** Waits for Excel to release file handles before retrying

### Login Countdown
- **Location:** `src/auth/graph_auth.py:get_token_interactive_force()`
- **Duration:** Up to 120 seconds (1-second poll intervals)
- **Code:** `done.wait(timeout=1.0)` in a `range(timeout_seconds, 0, -1)` loop

---

## Subprocess Calls

### `taskkill EXCEL.EXE`
- **Location:** `src/gui/app.py:_do_close_excel()`, `_kill_and_signal()`
- **Command:** `subprocess.run(["taskkill", "/IM", "EXCEL.EXE"], capture_output=True, timeout=8)`
- **When:** User clicks "Đóng Excel & Bắt đầu quét" in the Excel-locked dialog
- **Risk:** Kills ALL Excel processes — user loses unsaved work in any open Excel file

### `explorer <folder>`
- **Location:** `src/gui/app.py:_open_exported_folder()`
- **Command:** `subprocess.Popen(["explorer", os.fspath(folder)])`
- **When:** User clicks "📂 Mở folder export"
- **Note:** Non-blocking (`Popen`, not `run`)

### `setup_scheduler.bat` / `schtasks`
- **Location:** `setup_scheduler.bat`
- **Command:** Calls Windows `schtasks /create` to register daily Task Scheduler job
- **Trigger:** Daily at 08:00
- **Action:** Runs `run_headless.bat`

