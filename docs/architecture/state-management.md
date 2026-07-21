# State Management — Công Văn Processor

> Where all state lives, how it updates, and how it persists.
> Updated: 2026-05-05

---

## State Locations Overview

| State | Location | Type | Lifetime |
|---|---|---|---|
| OAuth token | `~/.tool_mail_cong_van/token_cache.bin` | Disk (MSAL cache) | Persistent across runs |
| Dedup records | `~/.tool_mail_cong_van/<date>/_processed.json` | Disk (JSON) | Per-day, persistent |
| GUI scan log | `~/.tool_mail_cong_van/<date>/scan_<range>.log` | Disk (text log) | Persistent per scan |
| In-memory dedup index | `DedupManager._tech_keys`, `._business_keys` | Python sets | Single process |
| Processing result | `ProcessResult` dataclass | In-memory | Single scan |
| GUI runtime state | `CongVanApp` instance vars + tkinter vars | In-memory | App lifetime |
| GUI baseline stats | `CongVanApp._base_stats` | In-memory dict | App lifetime |
| Config | `AppConfig` dataclass | In-memory | Loaded once per process |

---

## Detailed State Analysis

### 1. OAuth Token State (`src/auth/graph_auth.py`)

```
Disk: ~/.tool_mail_cong_van/token_cache.bin
    ↓ loaded at GraphAuth.__init__()
MSAL SerializableTokenCache (in-memory)
    ↓ written back on _save_cache() if has_state_changed
```

- **Read path:** `get_token()` → `acquire_token_silent()`
- **Write path:** `_save_cache()` after successful token acquisition
- **Delete path:** `logout()` removes accounts and deletes the cache file

### 2. Dedup State (`src/dedup/manager.py`)

```
Disk: ~/.tool_mail_cong_van/<date>/_processed.json
{
  "records": [
    {
      "message_id": "AAMkAGIw...",
      "internet_message_id": "<uuid@example.com>",
      "date_folder": "26.04.14",
      "so_don": "4-2025-20619",
      "attachment_filenames": ["3-thongbao.pdf"],
      "processed_at": "2026-04-14T09:15:32",
      "run_status": "OK"
    }
  ]
}
```

- **Loaded at:** `DedupManager.__init__(daily_folder)`
- **In-memory indexes:**
  - `_tech_keys` = `message_id` + `internet_message_id`
  - `_business_keys` = `date_folder|so_don`, `date_folder|filename`
- **Write rule:** only `register()` persists state, and it is called after a successful Excel write

### 3. Processing Result State (`src/processor/email_processor.py`)

```python
@dataclass
class ProcessResult:
    success_count: int = 0
    duplicate_count: int = 0
    review_count: int = 0
    error_count: int = 0
    file_error_count: int = 0
    missing_data_count: int = 0
    fallback_count: int = 0
    total_emails: int = 0
    errors: List[str] = field(default_factory=list)
    start_time: datetime
    end_time: Optional[datetime] = None
```

- **Lifetime:** one call to `EmailProcessor.run()`
- **Mutation style:** shared mutable object updated by worker threads; dedup/write phase is protected by `_write_lock`
- **Consumers:** GUI, headless CLI, and optional web server flow

### 4. GUI State (`src/gui/app.py`)

| Variable | Type | Default | Purpose |
|---|---|---|---|
| `self._config` | `Optional[AppConfig]` | `None` | Loaded config |
| `self._auth` | `Optional[GraphAuth]` | `None` | Auth object |
| `self._running` | `bool` | `False` | Scan in progress flag |
| `self._last_export_folder` | `str` | `~/Desktop/CongVanExport` | For “Open folder export” |
| `self._login_in_progress` | `bool` | `False` | Prevent double login |
| `self._last_auto_scan_slot` | `tuple` | `(-1, -1)` or current slot | Prevent double-fire |
| `self._base_stats` | `dict` | zeros | Baseline counters loaded from `_processed.json` |
| `self._from_date_var` | `tk.StringVar` | today `00:00` | Start of scan window |
| `self._to_date_var` | `tk.StringVar` | today `23:59` | End of scan window |
| `self._export_folder_var` | `tk.StringVar` | `~/Desktop/CongVanExport` | Output root |
| `self._mail_folder_var` | `tk.StringVar` | `Công văn` | Runtime folder override |
| `self._auto_scan_var` | `tk.BooleanVar` | `True` | Auto-scan enabled |
| `self._auto_scan_freq_var` | `tk.StringVar` | `1 giờ` | Scheduler frequency |
| `self._step_var` | `tk.StringVar` | `Sẵn sàng` | Progress title |
| `self._pct_var` | `tk.StringVar` | `""` | Progress subtitle |

### 5. Config State (`src/config.py`)

- `load_config()` returns a typed `AppConfig`
- Search order without explicit path:
  1. next to frozen `.exe`
  2. repo/package root
  3. current working directory
- Output paths are normalized with `.expanduser()` before use
- GUI mutates `self._config.mail.target_folder_name` at runtime before starting a scan

---

## State Update Propagation

### GUI → Worker Thread
```
User clicks "Quét mail"
    → _do_scan() reads tkinter vars
    → creates EmailProcessor(self._config, self._auth)
    → spawns scan thread
    → sets self._running = True
```

### Worker Thread → GUI
```
EmailProcessor.run(progress=self._on_progress, ...)
    → progress(current, total, message, stats)
    → CongVanApp._on_progress()
    → self.after(0, ...) updates labels, cards, progress bar, log panel
```

### GUI Completion Path
```
scan thread finishes
    → self.after(0, lambda: self._on_scan_done(result))
    → updates _base_stats, dashboard, progress bar, open-folder button
    → finally sets self._running = False
```

### Optional Web Server Completion Path
```
background scan worker
    → updates _st.scan_result
    → pushes progress objects into asyncio.Queue
    → /api/scan/stream emits SSE events
```

---

## Persistence Strategy

| Data | Persisted? | When | Format |
|---|---|---|---|
| OAuth token | ✅ Yes | After successful login/refresh | MSAL serialized cache |
| Processed emails | ✅ Yes | After each successful Excel write | JSON |
| GUI scan log | ✅ Yes | During each scan | Plain text |
| Excel workbook | ✅ Yes | After each append | `.xlsx` |
| Scheduler wrapper log | ✅ Yes | During headless wrapper execution | Plain text |
| GUI preferences (date range, output folder) | ❌ No | — | In-memory only |
| Config | ✅ Manual | `config.json` on disk | JSON |

**Key distinction:** business output and dedup state are intentionally split. The export folder can be remote or user-selected; the tool-state folder under `~/.tool_mail_cong_van/` is always local.
