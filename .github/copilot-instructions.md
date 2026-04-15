# GitHub Copilot Instructions — Công Văn Processor

## 🎯 Coding Philosophy (Non-negotiable)

> These rules apply to EVERY change, regardless of size.

1. **Minimal diff** — Change the least amount of code necessary to solve the problem.
   Do NOT refactor surrounding code, rename variables, or reformat lines not directly related to the task.
   A reviewer should be able to see exactly what changed and why.

2. **Follow existing conventions first** — Before writing any code, observe:
   - How existing files in the same folder are structured
   - What naming pattern is already used (snake_case throughout)
   - What import style is used (relative imports inside `src/`, e.g. `from ..config import load_config`)
   - What component/class pattern is used (dataclass + class with `_private` methods)
   Match the existing pattern even if you personally prefer a different style.

3. **Language best practices** — Code must follow idiomatic Python:
   - Type hints on all function signatures (`def foo(x: str) -> Optional[int]:`)
   - No dead code, no commented-out blocks, no debug `print()` left in
   - No direct state mutation on shared objects
   - Use `from __future__ import annotations` at top of every new file
   - Cleanup side effects (Playwright browser must always be closed — `browser.close()`)

4. **Design patterns** — Use the pattern already established:
   - Dataclasses for data transfer objects (`ParsedDocument`, `PortalDownloadResult`, etc.)
   - Class with `__init__` + private `_method()` naming for services
   - Module-level helper functions (not nested inside methods unless closure needed)
   - `logger = logging.getLogger(__name__)` at module level

5. **No sloppy shortcuts** — Forbidden regardless of urgency:
   - Hardcoded paths (use `config.json` / `AppConfig`)
   - `datetime.now()` for folder routing (use email's `received_datetime`)
   - Direct tkinter calls from worker threads (use `self.after(0, callback)`)
   - Suppressing type errors without comment

---

## 🧱 Code Style Patterns

### New service/module
```python
"""
Short module docstring explaining purpose.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from ..config import AppConfig   # relative import

logger = logging.getLogger(__name__)


class MyService:
    def __init__(self, config: AppConfig) -> None:
        self._config = config

    def do_thing(self, input: str) -> Optional[str]:
        """Public method — doc with return contract."""
        try:
            return self._internal(input)
        except Exception as exc:
            logger.warning("Failed to do_thing for %s: %s", input, exc)
            return None

    def _internal(self, input: str) -> str:
        """Private helper."""
        ...
```

### New dataclass result object
```python
from dataclasses import dataclass, field
from typing import List

@dataclass
class MyResult:
    success: bool = False
    items: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
```

### Adding a new classification rule (document type)
```python
# In src/parser/rules.py — append to CLASSIFICATION_RULES list:
# Tuple: (label, [required_phrase1, required_phrase2, ...])
# ORDER MATTERS — first match wins.
CLASSIFICATION_RULES: List[tuple] = [
    ("Dự định từ chối",            ["dự định từ chối"]),
    # ... existing rules ...
    ("Thông báo mới",              ["phrase that identifies this type"]),  # ← add here
]
```

### Adding a new Excel column
```python
# 1. Add to DATA_COLUMNS in src/excel/writer.py:
DATA_COLUMNS: List[str] = [
    # ... existing columns ...
    "Tên cột mới",   # ← append here
]

# 2. Add to row dict in src/processor/email_processor.py _write_results():
row = {
    # ... existing fields ...
    "Tên cột mới": parsed.new_field or "",
}
```

---

## 🏷️ Naming Conventions

| Type | Convention | Example |
|---|---|---|
| Variables | `snake_case` | `portal_url`, `daily_folder` |
| Private methods | `_snake_case` | `_run()`, `_click_download_button()` |
| Classes | `PascalCase` | `GraphAuth`, `BrowserDownloader` |
| Constants | `UPPER_SNAKE_CASE` | `CLASSIFICATION_RULES`, `DATA_COLUMNS` |
| Dataclasses | `PascalCase` | `ParsedDocument`, `PortalDownloadResult` |
| Vietnamese UI strings | Use full diacritics | `"Không tìm thấy"`, NOT `"Khong tim thay"` |
| Log messages (Vietnamese) | Use full diacritics | `logger.info("Đang xử lý...")` |

---

## 📊 Data Access Patterns

### Check if email already processed
```python
dedup = DedupManager(daily_folder)
is_dup, reason = dedup.is_duplicate(
    message_id=msg.id,
    internet_message_id=msg.internet_message_id,
    date_folder=folder_name,
    so_don=parsed.so_don,                          # None if not yet parsed
    attachment_filenames=att_filenames,            # None if not yet downloaded
)
if is_dup:
    result.duplicate_count += 1
    return
```

### Parse Vietnamese document fields from text
```python
from src.parser.rules import parse_document, ParsedDocument
parsed: ParsedDocument = parse_document(
    text=email_body_preview,
    pdf_path=Path("downloaded.pdf"),   # optional; merged with text
)
# Fields: so_cong_van, so_don, so_gcn, so_yeu_cau,
#         issue_date, deadline_months, deadline_date,
#         loai_cong_van, loai_hinh_don, noi_dung_cong_van
```

### Handle Excel locked error
```python
from src.excel.writer import ExcelWriter, ExcelLockedError
writer = ExcelWriter(daily_folder, "SO CONG VAN DEN-LIENDO.xlsx")
try:
    writer.append_data_row(row)
except ExcelLockedError as exc:
    # exc.excel_path = Path to the locked file
    logger.error("Excel đang mở: %s", exc.excel_path)
    # In GUI: show dialog via self._ask_excel_locked(exc.excel_path)
```

---

## ✅ Validation Checklist Before Proposing Changes

1. [ ] Imports use relative paths inside `src/` (e.g. `from ..config import ...`)
2. [ ] No `datetime.now()` used for folder name computation
3. [ ] GUI updates use `self.after(0, lambda: ...)` from worker threads
4. [ ] Vietnamese strings have correct diacritics
5. [ ] New service classes have `logger = logging.getLogger(__name__)`
6. [ ] Playwright browser context is always closed (`browser.close()`)
7. [ ] `DedupManager.register()` called AFTER `ExcelWriter.append_data_row()`
8. [ ] Tests updated if parser rules or dedup logic changed

---

## 🚨 Critical Files — Do NOT Modify Without Full Read

| File | Risk if modified carelessly |
|---|---|
| `src/processor/email_processor.py` | Step order change → dedup/Excel inconsistency |
| `src/dedup/manager.py` | Key strategy change → duplicate rows in Excel |
| `src/folder/routing.py` | Wrong UTC→local conversion → emails in wrong date folder |
| `src/excel/writer.py` | Column order change → existing Excel files corrupted |
| `src/parser/rules.py` | CLASSIFICATION_RULES reorder → wrong document type labels |
| `src/gui/app.py` | Thread safety violation → app crash during scan |
| `config.json` | Contains production Azure credentials and network paths |

---

## 📋 Mandatory Workflow Rules

1. **Before starting any ticket/task** — check `docs/tickets/` for previous fixes in the same area.
   If no ticket file exists yet, create one from `docs/tickets/_TEMPLATE.md` before writing code.

2. **After completing any ticket/task** — create or update `docs/tickets/ticket-{ID}-{slug}.md`.
   File must be bilingual (English + Vietnamese) and include root cause, solution, files changed, testing, risks.

3. **Non-ticket conversations** — log to `docs/conversations/conversation-{N}.md`.
   Max 5000 lines per file. When full, create the next numbered file.

4. **Ticket files MUST have Section 0** with two checklists:
   - `### 📋 Tiến độ xử lý` — 5-step progress tracking
   - `### 🎯 Các vấn đề cần giải quyết` — ticket-specific bugs/features

5. **Language rule** — all Vietnamese notes MUST use correct diacritics.
   Example: "người dùng" NOT "nguoi dung"; "không tìm thấy" NOT "khong tim thay"

6. **Never modify these critical files without reading them fully first**:
   `src/processor/email_processor.py`, `src/dedup/manager.py`,
   `src/folder/routing.py`, `src/excel/writer.py`, `src/parser/rules.py`

