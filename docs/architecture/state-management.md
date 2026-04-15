# State Management — Công Văn Processor

> Where all state lives, how it updates, and how it persists.
> Updated: 2026-04-15

---

## State Locations Overview

| State | Location | Type | Lifetime |
|---|---|---|---|
| OAuth token | `~/.tool_mail_cong_van/token_cache.bin` | Disk (MSAL binary) | Persistent across runs |
| Dedup records | `~/.tool_mail_cong_van/<date>/_processed.json` | Disk (JSON) | Per-day, persistent |
| In-memory dedup index | `DedupManager._tech_keys`, `._business_keys` | Python sets | Single run |
| Processing result | `ProcessResult` dataclass | In-memory | Single scan |
| GUI state | `CongVanApp` instance vars | tkinter StringVar / BooleanVar | App lifetime |
| Config | `AppConfig` dataclass | In-memory | App lifetime (loaded once) |
| Last export folder | `CongVanApp._last_export_folder` | str | App lifetime |
| Auto-scan slot | `CongVanApp._last_auto_scan_slot` | tuple(int, int) | App lifetime |
| Scan running flag | `CongVanApp._running` | bool | App lifetime |

---

## Detailed State Analysis

### 1. OAuth Token State (`src/auth/graph_auth.py`)

```
Disk: ~/.tool_mail_cong_van/token_cache.bin
    ↓ loaded at GraphAuth.__init__()
MSAL SerializableTokenCache (in-memory)
    ↓ written back on _save_cache() (only if has_state_changed)
```

- **Read:** `get_token()` → `acquire_token_silent()` → reads from cache
- **Write:** After any successful token acquisition → `_save_cache()`
- **Delete:** `logout()` → removes all accounts + deletes cache file
- **Refresh:** MSAL handles token refresh automatically in `acquire_token_silent()`

### 2. Deduplication State (`src/dedup/manager.py`)

```
Disk: ~/.tool_mail_cong_van/<date>/_processed.json
{
  "records": [
    {
      "message_id": "AAMkAGIw...",
      "internet_message_id": "<uuid@example.com>",
      "date_folder": "26.04.14",
      "so_don": "4-2025-20619",
      "attachment_filenames": ["1-thongbao.pdf"],
      "processed_at": "2026-04-14T09:15:32",
      "run_status": "OK"
    }
  ]
}
```

- **Loaded at:** `DedupManager.__init__(daily_folder)` — one instance per daily folder
- **In-memory index:** `_tech_keys` (set of message_id + internet_message_id), `_business_keys` (set of "date|so_don", "date|filename")
- **Written at:** `register()` — only after successful Excel write
- **Key scoping:** Each `DedupManager` is scoped to ONE daily folder

### 3. Processing Result State (`src/processor/email_processor.py`)

```python
@dataclass
class ProcessResult:
    success_count: int = 0
    duplicate_count: int = 0
    file_error_count: int = 0      # portal download failed
    missing_data_count: int = 0    # red rows in Excel (missing required fields)
    error_count: int = 0
    fallback_count: int = 0
    total_emails: int = 0
    errors: List[str] = field(default_factory=list)
    start_time: datetime
    end_time: Optional[datetime] = None
```

- **Lifetime:** Created at start of `EmailProcessor.run()`, returned when complete
- **Updates:** Mutated in-place by `_process_one()` callbacks
- **Consumed by:** GUI `_on_scan_done()` or headless `main()` for exit code

### 4. GUI State (`src/gui/app.py`)

| Variable | Type | Default | Purpose |
|---|---|---|---|
| `self._config` | `Optional[AppConfig]` | `None` | Loaded config |
| `self._auth` | `Optional[GraphAuth]` | `None` | Auth object |
| `self._running` | `bool` | `False` | Scan in progress flag |
| `self._last_export_folder` | `str` | `~/Desktop/CongVanExport` | For "Open folder" button |
| `self._login_in_progress` | `bool` | `False` | Prevents double-login click |
| `self._last_auto_scan_slot` | `tuple` | `(-1, -1)` | Prevents double-fire of auto-scan |
| `self._from_date_var` | `tk.StringVar` | today 00:00 | Date range start |
| `self._to_date_var` | `tk.StringVar` | today 23:59 | Date range end |
| `self._export_folder_var` | `tk.StringVar` | `~/Desktop/CongVanExport` | Output folder |
| `self._mail_folder_var` | `tk.StringVar` | "Công văn" | Mail folder name |
| `self._auto_scan_var` | `tk.BooleanVar` | `True` | Auto-scan enabled |
| `self._auto_scan_freq_var` | `tk.StringVar` | "1 giờ" | Scan frequency |
| `self._step_var` | `tk.StringVar` | "Sẵn sàng" | Progress step label |
| `self._pct_var` | `tk.StringVar` | `""` | Progress subtitle |

### 5. Config State (`src/config.py`)

- **Loaded once** at startup by `_load_config_and_route()` or at start of headless run
- **Mutable at runtime:** GUI allows changing `mail.target_folder_name` via the folder entry field (applied before scan)
- **Source:** `config.json` → typed `AppConfig` dataclass
- **Not reloaded** during the app lifetime (changes to `config.json` require restart)

---

## State Update Propagation

### GUI → Worker thread
```
User clicks "Quét mail"
    → CongVanApp._do_scan() reads: _from_date_var, _to_date_var, _export_folder_var, _mail_folder_var
    → Creates EmailProcessor with current _config, _auth
    → Spawns threading.Thread(_thread)
    → Sets _running = True
```

### Worker thread → GUI
```
EmailProcessor.run(progress=self._on_progress, ...)
    → Calls progress(current, total, message, stats)
    → CongVanApp._on_progress() dispatches via self.after(0, lambda: self._update_step(...))
    → Main thread updates: _step_var, _pct_var, _progress_bar["value"], stat card vars
```

### Completion
```
_thread() finishes → self.after(0, lambda: self._on_scan_done(result))
    → Updates all stat cards, progress bar to final state
    → Shows "📂 Mở folder export" button
    → _running = False (in finally block)
```

---

## Persistence Strategy

| Data | Persisted? | When | Format |
|---|---|---|---|
| OAuth token | ✅ Yes | After each login | MSAL binary (`token_cache.bin`) |
| Processed emails | ✅ Yes | After each successful write | JSON (`_processed.json`) |
| Scan log | ✅ Yes | After each scan | Plain text (`scan_<range>.log` via standard logging) |
| Excel data | ✅ Yes | After each email | `.xlsx` (openpyxl) |
| User preferences (date range, folder) | ❌ No | — | Only in tkinter StringVars |
| Config | ✅ Manual | config.json on disk | JSON |

**Note:** User preferences (date range, export folder) are NOT persisted between sessions. They always reset to defaults (today's date, `~/Desktop/CongVanExport`) on app launch.
