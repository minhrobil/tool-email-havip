"""
Main GUI — Xử lý Mail công văn (v2).

Flow:
  App opens → Check auth
    Not logged in → Login screen
    Logged in     → Main screen (date range, folder, scan, dashboard, stats)

Features:
  - Date range picker  (default: today 00:00–23:59)
  - Output folder selector  (default: ~/Desktop/CongVanExport)
  - Mini dashboard: Tìm thấy / Đang xử lý / Đã xử lý
  - Progress bar reaches 100 % only when error_count == 0
  - "Mở folder export" button appears after any successful export
  - No yellow network-fallback banner
"""
from __future__ import annotations

import json
import logging
import os
import pathlib
import subprocess
import sys
import threading
import time
import tkinter as tk
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
from typing import Optional

from ..auth.graph_auth import AuthRequiredError, GraphAuth
from ..config import AppConfig, load_config
from ..processor.email_processor import EmailProcessor, ProcessResult

logger = logging.getLogger(__name__)


# ── Design Tokens ─────────────────────────────────────────────────────────
_PRIMARY     = "#4F46E5"   # Indigo
_PRIMARY_H   = "#4338CA"   # Indigo hover
_PRIMARY_D   = "#3730A3"   # Indigo dark
_ACCENT      = "#06B6D4"   # Cyan
_SUCCESS     = "#10B981"   # Emerald
_SUCCESS_H   = "#059669"
_WARNING     = "#F59E0B"   # Amber
_ERROR       = "#EF4444"   # Red
_ERROR_H     = "#DC2626"

_BG          = "#F1F5F9"   # Slate-100
_CARD_BG     = "#FFFFFF"
_HEADER_BG   = "#1E293B"   # Slate-800
_HEADER_LIGHT= "#334155"   # Slate-700
_BORDER      = "#E2E8F0"   # Slate-200
_SHADOW      = "#CBD5E1"   # Slate-300
_TEXT         = "#0F172A"   # Slate-900
_TEXT_SEC     = "#475569"   # Slate-600
_TEXT_MUTED   = "#94A3B8"   # Slate-400
_WHITE        = "#FFFFFF"

_FONT        = "Segoe UI"
_VERSION     = "2.0"

_DISABLED_BG = "#CBD5E1"
_DISABLED_FG = "#F1F5F9"

_APP_TITLE   = "Xử lý Mail công văn"

_DEFAULT_EXPORT  = str(pathlib.Path.home() / "Desktop" / "CongVanExport")
_LOGIN_TIMEOUT   = 120

# Auto-scan frequency options (display label → hours)
_FREQ_HOURS: dict = {
    "1 giờ": 1, "2 giờ": 2, "4 giờ": 4, "6 giờ": 6,
    "8 giờ": 8, "12 giờ": 12, "24 giờ": 24,
}
_FREQ_LABELS = list(_FREQ_HOURS.keys())


def _read_range_stats(date_from: datetime, date_to: datetime, date_folder_format: str) -> dict:
    """
    Read _processed.json files for each day in [date_from, date_to] and sum counts.
    Returns a dict with keys: success, file_err, missing_data, dup, error, total.
    """
    stats = {"success": 0, "file_err": 0, "missing_data": 0, "dup": 0, "error": 0, "total": 0}
    tool_base = Path.home() / ".tool_mail_cong_van"
    cur = date_from.date()
    end = date_to.date()
    while cur <= end:
        proc_file = tool_base / cur.strftime(date_folder_format) / "_processed.json"
        if proc_file.exists():
            try:
                data = json.loads(proc_file.read_text(encoding="utf-8"))
                for rec in data.get("records", []):
                    stats["total"] += 1
                    if rec.get("run_status", "OK") == "OK":
                        stats["success"] += 1
                    else:
                        stats["file_err"] += 1
            except Exception:
                pass
        cur += timedelta(days=1)
    return stats


def _open_folder_in_file_manager(folder: pathlib.Path) -> None:
    """Open a folder in the native file manager for the current OS."""
    folder.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        subprocess.Popen(["open", os.fspath(folder)])
    elif os.name == "nt":
        subprocess.Popen(["explorer", os.fspath(folder)])
    else:
        subprocess.Popen(["xdg-open", os.fspath(folder)])


# ── Reusable hover helper ─────────────────────────────────────────────────
def _bind_hover(widget, enter_bg, leave_bg, enter_fg=None, leave_fg=None):
    """Attach hover color transitions to a widget."""
    def on_enter(e):
        if widget.cget("state") != "disabled":
            widget.config(bg=enter_bg)
            if enter_fg:
                widget.config(fg=enter_fg)
    def on_leave(e):
        if widget.cget("state") != "disabled":
            widget.config(bg=leave_bg)
            if leave_fg:
                widget.config(fg=leave_fg)
    widget.bind("<Enter>", on_enter)
    widget.bind("<Leave>", on_leave)


class _ShadowCard(tk.Frame):
    """A card frame with a subtle shadow effect using a border trick."""
    def __init__(self, parent, **kw):
        shadow = tk.Frame(parent, bg=_SHADOW)
        shadow.pack(fill=tk.X, padx=20, pady=(0, 2))
        # The "shadow" is just a 1px bottom/right colored border
        super().__init__(shadow, bg=_CARD_BG,
                         highlightbackground=_BORDER, highlightthickness=1, **kw)
        self.pack(fill=tk.X, padx=(0, 2), pady=(0, 2))
        self._shadow = shadow

    def pack(self, **kw):
        # Only pack the shadow wrapper externally
        if kw:
            self._shadow.pack(**kw)
        else:
            super().pack(fill=tk.X)

    def pack_configure(self, **kw):
        self._shadow.pack_configure(**kw)


class _GradientProgressBar(tk.Canvas):
    """Custom canvas-based progress bar with gradient fill and text overlay."""
    def __init__(self, parent, height=20, **kw):
        super().__init__(parent, height=height, bg=_BORDER,
                         highlightthickness=0, bd=0, **kw)
        self._value = 0
        self._height = height
        self.bind("<Configure>", self._redraw)

    def set_value(self, pct: int):
        self._value = max(0, min(100, pct))
        self._redraw()

    def _redraw(self, event=None):
        self.delete("all")
        w = self.winfo_width() or 300
        h = self._height

        # Background track (rounded rect via rectangle — Tkinter limitation)
        self.create_rectangle(0, 0, w, h, fill=_BORDER, outline="")

        if self._value > 0:
            fill_w = int(w * self._value / 100)
            # Gradient simulation: left portion primary, right portion lighter
            mid = fill_w // 2
            self.create_rectangle(0, 0, mid, h, fill=_PRIMARY, outline="")
            self.create_rectangle(mid, 0, fill_w, h, fill=_ACCENT, outline="")

        # Text overlay
        if self._value > 0:
            txt_color = _WHITE if self._value > 50 else _TEXT
            self.create_text(w // 2, h // 2, text=f"{self._value}%",
                             font=(_FONT, 8, "bold"), fill=txt_color)


class _Toast(tk.Frame):
    """In-app toast notification that auto-dismisses."""
    def __init__(self, parent, message: str, kind: str = "info", duration: int = 3000):
        colors = {
            "info":    (_PRIMARY, _WHITE),
            "success": (_SUCCESS, _WHITE),
            "warning": (_WARNING, _TEXT),
            "error":   (_ERROR, _WHITE),
        }
        bg, fg = colors.get(kind, colors["info"])
        super().__init__(parent, bg=bg, padx=16, pady=8)
        tk.Label(self, text=message, font=(_FONT, 9), bg=bg, fg=fg,
                 wraplength=500).pack(side=tk.LEFT, fill=tk.X, expand=True)
        close_btn = tk.Label(self, text="✕", font=(_FONT, 10, "bold"),
                             bg=bg, fg=fg, cursor="hand2", padx=8)
        close_btn.pack(side=tk.RIGHT)
        close_btn.bind("<Button-1>", lambda e: self.destroy())
        self.pack(fill=tk.X, padx=20, pady=(4, 0))
        self.lift()
        if duration > 0:
            self.after(duration, self._fade_out)

    def _fade_out(self):
        try:
            self.destroy()
        except Exception:
            pass


class CongVanApp(tk.Tk):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.title(_APP_TITLE)
        self.geometry("700x780")
        self.minsize(620, 720)
        self.configure(bg=_BG)
        self.resizable(True, True)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._config: Optional[AppConfig] = None
        self._auth: Optional[GraphAuth] = None
        self._running = False
        self._last_export_folder: str = _DEFAULT_EXPORT
        self._login_in_progress = False
        self._login_secs_left   = 0
        self._last_auto_scan_slot = -1
        self._base_stats: dict = {"success": 0, "file_err": 0, "missing_data": 0, "dup": 0, "error": 0, "total": 0}

        self._setup_file_logging()

        # Build frames
        self._login_frame = self._build_login_frame()
        self._main_frame  = self._build_main_frame()

        self._load_config_and_route()

    # ═══════════════════════════════════════════════════════════════════════
    # LOGGING SETUP
    # ═══════════════════════════════════════════════════════════════════════

    def _setup_file_logging(self) -> None:
        """Configure root logger basic level — scan-specific file handler is added in _do_scan."""
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)

    def _add_scan_log_handler(
        self, from_date: datetime, to_date: datetime
    ) -> Optional[logging.FileHandler]:
        """Create a FileHandler writing to ~/.tool_mail_cong_van/<from_folder>/<log_name>.

        The log file lives beside _processed.json.  Filename includes the full
        date range so runs with different ranges don't overwrite each other.
        Returns the handler so _do_scan can remove it when the scan finishes.
        """
        try:
            from_folder = from_date.strftime("%y.%m.%d")
            log_dir = pathlib.Path.home() / ".tool_mail_cong_van" / from_folder
            log_dir.mkdir(parents=True, exist_ok=True)

            fname = (
                f"scan_{from_date.strftime('%y.%m.%d_%H%M')}"
                f"--{to_date.strftime('%y.%m.%d_%H%M')}.log"
            )
            fh = logging.FileHandler(log_dir / fname, encoding="utf-8", mode="a")
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)-7s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            ))
            logging.getLogger().addHandler(fh)
            logger.info("=== Scan log: %s/%s ===", log_dir, fname)
            return fh
        except Exception as exc:
            logger.warning("Could not create scan log file: %s", exc)
            return None

    # ═══════════════════════════════════════════════════════════════════════
    # LOGIN FRAME
    # ═══════════════════════════════════════════════════════════════════════

    def _build_login_frame(self) -> tk.Frame:
        f = tk.Frame(self, bg=_BG)

        # Center container
        center = tk.Frame(f, bg=_BG)
        center.place(relx=0.5, rely=0.45, anchor="center")

        # Icon
        tk.Label(center, text="📬", font=(_FONT, 56), bg=_BG, fg=_PRIMARY).pack()

        # Title
        tk.Label(
            center, text=_APP_TITLE,
            font=(_FONT, 22, "bold"), bg=_BG, fg=_HEADER_BG,
        ).pack(pady=(10, 4))

        # Subtitle
        tk.Label(
            center, text="Tự động xử lý công văn từ Cục Sở hữu trí tuệ",
            font=(_FONT, 10), bg=_BG, fg=_TEXT_SEC,
        ).pack(pady=(0, 24))

        # Login card
        login_card = tk.Frame(center, bg=_CARD_BG,
                              highlightbackground=_BORDER, highlightthickness=1)
        login_card.pack(padx=40, pady=8)

        inner = tk.Frame(login_card, bg=_CARD_BG, padx=32, pady=24)
        inner.pack()

        tk.Label(inner, text="Đăng nhập để bắt đầu",
                 font=(_FONT, 11), bg=_CARD_BG, fg=_TEXT_SEC).pack(pady=(0, 16))

        self._login_btn = tk.Button(
            inner, text="🔑   Đăng nhập Microsoft",
            command=self._do_login,
            font=(_FONT, 12, "bold"),
            bg=_PRIMARY, fg=_WHITE,
            activebackground=_PRIMARY_D, activeforeground=_WHITE,
            relief=tk.FLAT, padx=30, pady=12, cursor="hand2", bd=0,
        )
        self._login_btn.pack(ipadx=10, fill=tk.X)
        _bind_hover(self._login_btn, _PRIMARY_H, _PRIMARY)

        self._login_status = tk.Label(
            inner, text="",
            font=(_FONT, 9), bg=_CARD_BG, fg=_TEXT_MUTED,
            wraplength=300,
        )
        self._login_status.pack(pady=(12, 0))

        # Footer
        tk.Label(
            f, text=f"v{_VERSION}  •  Powered by Microsoft Graph API",
            font=(_FONT, 8), bg=_BG, fg=_TEXT_MUTED,
        ).pack(side=tk.BOTTOM, pady=12)

        return f

    # ═══════════════════════════════════════════════════════════════════════
    # MAIN FRAME
    # ═══════════════════════════════════════════════════════════════════════

    def _build_main_frame(self) -> tk.Frame:
        f = tk.Frame(self, bg=_BG)

        # ── Header ────────────────────────────────────────────────────────
        header = tk.Frame(f, bg=_HEADER_BG, pady=14)
        header.pack(fill=tk.X)

        tk.Label(
            header, text=f"📬  {_APP_TITLE}",
            font=(_FONT, 14, "bold"), bg=_HEADER_BG, fg=_WHITE,
        ).pack(side=tk.LEFT, padx=20)

        self._logout_btn = tk.Button(
            header, text="Đăng xuất",
            command=self._do_logout,
            font=(_FONT, 8), bg=_HEADER_LIGHT, fg="#94A3B8",
            activebackground=_ERROR, activeforeground=_WHITE,
            relief=tk.FLAT, padx=12, pady=5, cursor="hand2", bd=0,
        )
        self._logout_btn.pack(side=tk.RIGHT, padx=14)
        _bind_hover(self._logout_btn, _ERROR, _HEADER_LIGHT, _WHITE, "#94A3B8")

        # Status dot + user label
        self._status_dot = tk.Label(
            header, text="●", font=(_FONT, 10), bg=_HEADER_BG, fg=_SUCCESS,
        )
        self._status_dot.pack(side=tk.RIGHT, padx=(0, 4))

        self._user_label = tk.Label(
            header, text="",
            font=(_FONT, 9), bg=_HEADER_BG, fg="#94A3B8",
        )
        self._user_label.pack(side=tk.RIGHT, padx=(0, 2))

        # ── Style setup ───────────────────────────────────────────────────
        style = ttk.Style()
        style.theme_use("clam")

        # ── Toast area ────────────────────────────────────────────────────
        self._toast_area = tk.Frame(f, bg=_BG)
        self._toast_area.pack(fill=tk.X)

        # ── Footer (packed first so it anchors to the bottom) ─────────────
        tk.Label(
            f, text=f"v{_VERSION}  •  Powered by Microsoft Graph API",
            font=(_FONT, 8), bg=_BG, fg=_TEXT_MUTED,
        ).pack(side=tk.BOTTOM, pady=8)

        # ── Custom tab bar ─────────────────────────────────────────────────
        tab_bar = tk.Frame(f, bg=_CARD_BG,
                           highlightbackground=_BORDER, highlightthickness=1)
        tab_bar.pack(fill=tk.X)

        # ── Content area (stacked frames, one visible at a time) ───────────
        tab_content = tk.Frame(f, bg=_BG)
        tab_content.pack(fill=tk.BOTH, expand=True)

        page_main = tk.Frame(tab_content, bg=_BG)
        page_log  = tk.Frame(tab_content, bg=_BG)

        self._build_main_tab(page_main)
        self._build_activities_tab(page_log)

        # ── Tab switch logic ───────────────────────────────────────────────
        _TAB_PAGES = {"main": page_main, "activities": page_log}
        self._tab_buttons: dict = {}

        def _switch_tab(name: str) -> None:
            for k, page in _TAB_PAGES.items():
                if k == name:
                    page.pack(fill=tk.BOTH, expand=True)
                else:
                    page.pack_forget()
            for k, (btn, bar) in self._tab_buttons.items():
                if k == name:
                    btn.config(fg=_PRIMARY, font=(_FONT, 9, "bold"), bg="#EEF2FF")
                    bar.config(bg=_PRIMARY)
                else:
                    btn.config(fg=_TEXT_MUTED, font=(_FONT, 9), bg=_CARD_BG)
                    bar.config(bg=_CARD_BG)

        self._switch_tab = _switch_tab

        tab_icons = {"main": "◉  Main", "activities": "◎  Activities"}
        for tab_name, tab_label in tab_icons.items():
            cell = tk.Frame(tab_bar, bg=_CARD_BG)
            cell.pack(side=tk.LEFT)
            btn = tk.Button(
                cell, text=tab_label,
                command=lambda n=tab_name: _switch_tab(n),
                font=(_FONT, 9), bg=_CARD_BG, fg=_TEXT_MUTED,
                relief=tk.FLAT, bd=0, padx=22, pady=10,
                cursor="hand2",
                activebackground="#EEF2FF", activeforeground=_PRIMARY,
            )
            btn.pack()
            indicator = tk.Frame(cell, bg=_CARD_BG, height=3)
            indicator.pack(fill=tk.X)
            self._tab_buttons[tab_name] = (btn, indicator)

        _switch_tab("main")

        return f

    def _build_main_tab(self, f: tk.Frame) -> None:
        """Build all widgets for Tab 1 — Main."""

        # ── Scrollable container ──────────────────────────────────────────
        # Wrap everything in a canvas for scrollability on small screens
        container = tk.Frame(f, bg=_BG)
        container.pack(fill=tk.BOTH, expand=True)

        # ── Config card ───────────────────────────────────────────────────
        cfg_shadow = tk.Frame(container, bg=_SHADOW)
        cfg_shadow.pack(fill=tk.X, padx=20, pady=(14, 2))
        cfg_card = tk.Frame(
            cfg_shadow, bg=_CARD_BG,
            highlightbackground=_BORDER, highlightthickness=1,
        )
        cfg_card.pack(fill=tk.X, padx=(0, 2), pady=(0, 2))

        # Section header
        cfg_header = tk.Frame(cfg_card, bg=_CARD_BG, padx=18, pady=(12, 0))
        cfg_header.pack(fill=tk.X)
        tk.Label(cfg_header, text="⚙  Cấu hình quét",
                 font=(_FONT, 11, "bold"), bg=_CARD_BG, fg=_TEXT).pack(anchor="w")

        g = tk.Frame(cfg_card, bg=_CARD_BG, padx=18, pady=(8, 14))
        g.pack(fill=tk.X)
        g.columnconfigure(1, weight=1)

        def _lbl(text, row, col=0, **kw):
            tk.Label(
                g, text=text,
                font=(_FONT, 9), bg=_CARD_BG, fg=_TEXT_SEC,
                anchor="e",
            ).grid(row=row, column=col, sticky="e", padx=(0, 10), pady=5, **kw)

        today = datetime.now()

        # Row 0 — date range
        _lbl("Từ:", 0)
        date_cells = tk.Frame(g, bg=_CARD_BG)
        date_cells.grid(row=0, column=1, sticky="w", pady=5)

        self._from_date_var = tk.StringVar(value=today.strftime("%d/%m/%Y 00:00"))
        self._from_date_entry = ttk.Entry(
            date_cells, textvariable=self._from_date_var, width=16, font=(_FONT, 9),
        )
        self._from_date_entry.pack(side=tk.LEFT)
        self._from_date_entry.bind("<FocusOut>", lambda _e: self._load_and_show_stats())
        self._from_date_entry.bind("<Return>",   lambda _e: self._load_and_show_stats())

        tk.Label(
            date_cells, text="  →  Đến:",
            font=(_FONT, 9), bg=_CARD_BG, fg=_TEXT_SEC,
        ).pack(side=tk.LEFT)

        self._to_date_var = tk.StringVar(value=today.strftime("%d/%m/%Y 23:59"))
        self._to_date_entry = ttk.Entry(
            date_cells, textvariable=self._to_date_var, width=16, font=(_FONT, 9),
        )
        self._to_date_entry.pack(side=tk.LEFT, padx=(4, 8))
        self._to_date_entry.bind("<FocusOut>", lambda _e: self._load_and_show_stats())
        self._to_date_entry.bind("<Return>",   lambda _e: self._load_and_show_stats())

        tk.Label(
            date_cells, text="DD/MM/YYYY HH:MM",
            font=(_FONT, 8), bg=_CARD_BG, fg=_TEXT_MUTED,
        ).pack(side=tk.LEFT)

        # Row 1 — mail folder
        _lbl("Thư mục mail:", 1)
        self._mail_folder_var = tk.StringVar(value="Công văn")
        self._mail_folder_entry = ttk.Entry(
            g, textvariable=self._mail_folder_var, font=(_FONT, 9), width=24,
        )
        self._mail_folder_entry.grid(row=1, column=1, sticky="w", pady=5)

        # Row 2 — export folder
        _lbl("Export vào:", 2)
        export_row = tk.Frame(g, bg=_CARD_BG)
        export_row.grid(row=2, column=1, sticky="ew", pady=5)
        export_row.columnconfigure(0, weight=1)

        self._export_folder_var = tk.StringVar(value=_DEFAULT_EXPORT)
        ttk.Entry(
            export_row, textvariable=self._export_folder_var, font=(_FONT, 9),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self._choose_folder_btn = tk.Button(
            export_row, text="📁  Chọn…",
            command=self._do_choose_folder,
            font=(_FONT, 9), bg=_BORDER, fg=_TEXT,
            activebackground=_HEADER_LIGHT, activeforeground=_WHITE,
            relief=tk.FLAT, padx=10, pady=5, cursor="hand2", bd=0,
        )
        self._choose_folder_btn.grid(row=0, column=1)
        _bind_hover(self._choose_folder_btn, _SHADOW, _BORDER)

        # Row 3 — auto-scan
        _lbl("Tự động quét:", 3)
        auto_cells = tk.Frame(g, bg=_CARD_BG)
        auto_cells.grid(row=3, column=1, sticky="w", pady=5)

        self._auto_scan_var = tk.BooleanVar(value=True)
        self._auto_scan_cb = tk.Checkbutton(
            auto_cells, text="Bật",
            variable=self._auto_scan_var,
            font=(_FONT, 9), bg=_CARD_BG, fg=_TEXT,
            activebackground=_CARD_BG, selectcolor=_CARD_BG,
            cursor="hand2",
        )
        self._auto_scan_cb.pack(side=tk.LEFT)

        tk.Label(
            auto_cells, text="  Mỗi",
            font=(_FONT, 9), bg=_CARD_BG, fg=_TEXT_SEC,
        ).pack(side=tk.LEFT)

        self._auto_scan_freq_var = tk.StringVar(value="1 giờ")
        self._auto_scan_freq_cb = ttk.Combobox(
            auto_cells, textvariable=self._auto_scan_freq_var,
            values=_FREQ_LABELS, state="readonly", width=7,
            font=(_FONT, 9),
        )
        self._auto_scan_freq_cb.pack(side=tk.LEFT, padx=(4, 0))

        # ── Action buttons ─────────────────────────────────────────────────
        self._btn_row = tk.Frame(container, bg=_BG, pady=10)
        self._btn_row.pack(fill=tk.X, padx=20)

        self._scan_btn = self._big_btn(
            self._btn_row, "📥   Quét mail", self._do_scan, _PRIMARY,
        )
        self._scan_btn.pack(side=tk.LEFT)
        _bind_hover(self._scan_btn, _PRIMARY_H, _PRIMARY)

        # "Mở folder" — hidden until first successful export
        self._open_export_btn = self._big_btn(
            self._btn_row, "📂   Mở folder export",
            self._open_exported_folder, _SUCCESS,
        )
        _bind_hover(self._open_export_btn, _SUCCESS_H, _SUCCESS)
        # Not packed yet — shown in _on_scan_done

        # ── Progress card ──────────────────────────────────────────────────
        prog_shadow = tk.Frame(container, bg=_SHADOW)
        prog_shadow.pack(fill=tk.X, padx=20, pady=(0, 2))
        card = tk.Frame(
            prog_shadow, bg=_CARD_BG, relief=tk.FLAT, bd=0,
            highlightbackground=_BORDER, highlightthickness=1,
        )
        card.pack(fill=tk.X, padx=(0, 2), pady=(0, 2))

        inner = tk.Frame(card, bg=_CARD_BG, padx=18, pady=14)
        inner.pack(fill=tk.X)

        self._step_var = tk.StringVar(value="Sẵn sàng")
        tk.Label(
            inner, textvariable=self._step_var,
            font=(_FONT, 10, "bold"), bg=_CARD_BG, fg=_TEXT,
            anchor="w", justify=tk.LEFT, wraplength=560,
        ).pack(fill=tk.X)

        self._pct_var = tk.StringVar(value="")
        tk.Label(
            inner, textvariable=self._pct_var,
            font=(_FONT, 9), bg=_CARD_BG, fg=_TEXT_SEC, anchor="w",
        ).pack(fill=tk.X, pady=(2, 0))

        pb_frame = tk.Frame(inner, bg=_CARD_BG, pady=8)
        pb_frame.pack(fill=tk.X)

        self._progress_bar = _GradientProgressBar(pb_frame, height=18)
        self._progress_bar.pack(fill=tk.X)

        # ── Dashboard row (3 cards) ─────────────────────────────────────────
        dash_row = tk.Frame(container, bg=_BG, pady=8)
        dash_row.pack(fill=tk.X, padx=20)

        self._dash_found      = self._stat_card(dash_row, "📬  Tìm thấy",    "0", _PRIMARY)
        self._dash_processing = self._stat_card(dash_row, "⏳  Đang xử lý",  "0", _WARNING)
        self._dash_done       = self._stat_card(dash_row, "✅  Đã xử lý",    "0", _SUCCESS)

        for w in (self._dash_found[0], self._dash_processing[0], self._dash_done[0]):
            w.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=4)

        # ── Stats row (5 cards) ────────────────────────────────────────────
        stats_row = tk.Frame(container, bg=_BG, pady=2)
        stats_row.pack(fill=tk.X, padx=20)

        self._stat_ok          = self._stat_card(stats_row, "✓ Thành công",    "0", _SUCCESS)
        self._stat_file_err    = self._stat_card(stats_row, "⚠ Lỗi tải file", "0", _WARNING)
        self._stat_missing     = self._stat_card(stats_row, "📋 Thiếu data",   "0", _WARNING)
        self._stat_dup         = self._stat_card(stats_row, "⟳ Đã có",        "0", _TEXT_MUTED)
        self._stat_err         = self._stat_card(stats_row, "✗ Lỗi",           "0", _ERROR)

        for w in (self._stat_ok[0], self._stat_file_err[0], self._stat_missing[0],
                  self._stat_dup[0], self._stat_err[0]):
            w.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=4)

    def _build_activities_tab(self, f: tk.Frame) -> None:
        """Build all widgets for Tab 2 — Activities."""
        outer = tk.Frame(f, bg=_BG)
        outer.pack(fill=tk.BOTH, expand=True, padx=20, pady=14)

        hdr = tk.Frame(outer, bg=_BG)
        hdr.pack(fill=tk.X, pady=(0, 8))

        tk.Label(
            hdr, text="📋  Nhật ký hoạt động",
            font=(_FONT, 11, "bold"), bg=_BG, fg=_TEXT,
        ).pack(side=tk.LEFT)

        clear_btn = tk.Button(
            hdr, text="Xoá",
            command=self._clear_log,
            font=(_FONT, 8), bg=_BORDER, fg=_TEXT_SEC,
            activebackground=_ERROR, activeforeground=_WHITE,
            relief=tk.FLAT, padx=10, pady=4, cursor="hand2", bd=0,
        )
        clear_btn.pack(side=tk.RIGHT)
        _bind_hover(clear_btn, _ERROR, _BORDER, _WHITE, _TEXT_SEC)

        # Log text with colored tags
        log_frame = tk.Frame(outer, bg=_BORDER,
                             highlightbackground=_BORDER, highlightthickness=1)
        log_frame.pack(fill=tk.BOTH, expand=True)

        self._log_text = scrolledtext.ScrolledText(
            log_frame, state=tk.DISABLED,
            font=("Consolas", 9), bg="#FAFBFC", fg=_TEXT,
            relief=tk.FLAT, padx=12, pady=10,
            wrap=tk.WORD,
        )
        self._log_text.pack(fill=tk.BOTH, expand=True)

        # Configure color tags for log entries
        self._log_text.tag_configure("success", foreground=_SUCCESS)
        self._log_text.tag_configure("error", foreground=_ERROR)
        self._log_text.tag_configure("warning", foreground=_WARNING)
        self._log_text.tag_configure("info", foreground=_PRIMARY)
        self._log_text.tag_configure("timestamp", foreground=_TEXT_MUTED)

    # ═══════════════════════════════════════════════════════════════════════
    # WIDGET HELPERS
    # ═══════════════════════════════════════════════════════════════════════

    def _big_btn(self, parent, text, cmd, color) -> tk.Button:
        return tk.Button(
            parent, text=text, command=cmd,
            font=(_FONT, 11, "bold"), bg=color, fg=_WHITE,
            activebackground=_PRIMARY_D, activeforeground=_WHITE,
            disabledforeground=_DISABLED_FG,
            relief=tk.FLAT, padx=20, pady=10, cursor="hand2", bd=0,
        )

    def _stat_card(self, parent, label: str, value: str, color: str):
        """Returns (frame, value_var)."""
        # Shadow wrapper
        shadow = tk.Frame(parent, bg=_SHADOW)

        card = tk.Frame(
            shadow, bg=_CARD_BG,
            highlightbackground=_BORDER, highlightthickness=1,
        )
        card.pack(fill=tk.BOTH, expand=True, padx=(0, 2), pady=(0, 2))

        inner = tk.Frame(card, bg=_CARD_BG, padx=6, pady=10)
        inner.pack(fill=tk.BOTH, expand=True)

        val_var = tk.StringVar(value=value)
        tk.Label(
            inner, textvariable=val_var,
            font=(_FONT, 22, "bold"), bg=_CARD_BG, fg=color,
        ).pack()
        tk.Label(
            inner, text=label,
            font=(_FONT, 8), bg=_CARD_BG, fg=_TEXT_SEC,
        ).pack(pady=(2, 0))
        return shadow, val_var

    # ═══════════════════════════════════════════════════════════════════════
    # TOAST HELPER
    # ═══════════════════════════════════════════════════════════════════════

    def _show_toast(self, message: str, kind: str = "info", duration: int = 3000) -> None:
        """Show an in-app toast notification."""
        _Toast(self._toast_area, message, kind, duration)

    # ═══════════════════════════════════════════════════════════════════════
    # LOG PANEL HELPERS
    # ═══════════════════════════════════════════════════════════════════════

    def _append_log(self, message: str) -> None:
        """Append a timestamped line to the log panel (must be called on main thread)."""
        try:
            ts = datetime.now().strftime("%H:%M:%S")
            self._log_text.config(state=tk.NORMAL)

            # Insert timestamp with tag
            self._log_text.insert(tk.END, f"[{ts}] ", "timestamp")

            # Determine message tag based on content
            msg = message.strip()
            tag = ""
            if any(k in msg for k in ("✅", "Hoàn thành", "thành công", "✓")):
                tag = "success"
            elif any(k in msg for k in ("❌", "Lỗi", "✗", "lỗi")):
                tag = "error"
            elif any(k in msg for k in ("⚠", "cảnh báo", "thiếu")):
                tag = "warning"
            elif any(k in msg for k in ("⏰", "▶", "Auto-scan", "📥")):
                tag = "info"

            self._log_text.insert(tk.END, msg + "\n", tag if tag else None)
            self._log_text.see(tk.END)
            self._log_text.config(state=tk.DISABLED)
        except Exception:
            pass

    def _clear_log(self) -> None:
        try:
            self._log_text.config(state=tk.NORMAL)
            self._log_text.delete("1.0", tk.END)
            self._log_text.config(state=tk.DISABLED)
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════════════════
    # INIT / ROUTING
    # ═══════════════════════════════════════════════════════════════════════

    def _load_config_and_route(self) -> None:
        try:
            self._config = load_config()
            self._auth = GraphAuth(
                client_id=self._config.azure.client_id,
                authority=self._config.azure.authority,
                scopes=self._config.azure.scopes,
            )
            # Sync mail folder field with loaded config
            self._mail_folder_var.set(self._config.mail.target_folder_name)
        except (FileNotFoundError, ValueError) as exc:
            self._show_login()
            self._login_status.config(
                text=f"⚠ Lỗi config: {exc}", fg=_ERROR,
            )
            return

        if self._auth.is_authenticated():
            self._show_main()
        else:
            self._show_login()

    def _show_login(self) -> None:
        self._main_frame.pack_forget()
        self._login_frame.pack(fill=tk.BOTH, expand=True)
        self.geometry("520x460")

    def _show_main(self) -> None:
        self._login_in_progress = False
        self._login_frame.pack_forget()
        self._main_frame.pack(fill=tk.BOTH, expand=True)
        self.geometry("700x780")
        user = self._auth.get_username() or ""
        self._user_label.config(text=user)
        self._status_dot.config(fg=_SUCCESS)
        self._start_scheduler()
        self._load_and_show_stats()

    # ═══════════════════════════════════════════════════════════════════════
    # DATE / FOLDER HELPERS
    # ═══════════════════════════════════════════════════════════════════════

    def _load_and_show_stats(self) -> None:
        """Read _processed.json files for the current date range and populate stat cards."""
        if self._config is None or self._running:
            return
        date_from, date_to = self._parse_date_range()
        if date_from is None:
            return
        fmt = self._config.output.date_folder_format

        def _bg():
            stats = _read_range_stats(date_from, date_to, fmt)
            self.after(0, lambda: self._apply_base_stats(stats))

        threading.Thread(target=_bg, daemon=True).start()

    def _apply_base_stats(self, stats: dict) -> None:
        """Store and display the pre-loaded stats as the baseline."""
        self._base_stats = dict(stats)
        self._stat_ok[1].set(str(stats.get("success", 0)))
        self._stat_file_err[1].set(str(stats.get("file_err", 0)))
        self._stat_missing[1].set(str(stats.get("missing_data", 0)))
        self._stat_dup[1].set(str(stats.get("dup", 0)))
        self._stat_err[1].set(str(stats.get("error", 0)))
        total = stats.get("total", 0)
        self._dash_found[1].set(str(total))
        self._dash_processing[1].set("0")
        self._dash_done[1].set(str(total))
        if total > 0:
            self._open_export_btn.pack(side=tk.LEFT, padx=(12, 0))


    def _parse_date_range(self):
        """
        Parse from / to datetime entries (DD/MM/YYYY HH:MM).
        Returns (datetime_from, datetime_to) or (None, None) on error.
        """
        fmt = "%d/%m/%Y %H:%M"
        raw_from = self._from_date_var.get().strip()
        raw_to   = self._to_date_var.get().strip()

        # Accept date-only input and append defaults
        if len(raw_from) == 10:   # "DD/MM/YYYY"
            raw_from += " 00:00"
        if len(raw_to) == 10:
            raw_to += " 23:59"

        try:
            d_from = datetime.strptime(raw_from, fmt)
        except ValueError:
            messagebox.showerror(
                "Ngày giờ không hợp lệ",
                f"Định dạng: DD/MM/YYYY HH:MM\nGiá trị bắt đầu: '{raw_from}'",
            )
            return None, None
        try:
            d_to = datetime.strptime(raw_to, fmt)
        except ValueError:
            messagebox.showerror(
                "Ngày giờ không hợp lệ",
                f"Định dạng: DD/MM/YYYY HH:MM\nGiá trị kết thúc: '{raw_to}'",
            )
            return None, None

        if d_from > d_to:
            messagebox.showerror(
                "Khoảng thời gian không hợp lệ",
                "Thời điểm bắt đầu phải ≤ thời điểm kết thúc.",
            )
            return None, None
        return d_from, d_to

    def _do_choose_folder(self) -> None:
        folder = filedialog.askdirectory(
            title="Chọn thư mục export",
            initialdir=self._export_folder_var.get() or str(pathlib.Path.home() / "Desktop"),
        )
        if folder:
            self._export_folder_var.set(folder)

    # ═══════════════════════════════════════════════════════════════════════
    # BUTTON HANDLERS
    # ═══════════════════════════════════════════════════════════════════════

    def _do_login(self) -> None:
        if not self._auth:
            messagebox.showerror("Lỗi", "Chưa tải được config.json.")
            return
        if self._login_in_progress:
            return

        self._login_in_progress = True
        self._login_btn.config(state=tk.DISABLED)
        self._login_status.config(text="Đang mở trình duyệt…", fg=_TEXT_SEC)

        def _tick(remaining: int) -> None:
            """Called every second by get_token_interactive_force (worker thread)."""
            mins = remaining // 60
            sec  = remaining % 60
            self.after(0, lambda r=remaining: self._login_status.config(
                text=f"Đang chờ trong trình duyệt…  {mins}:{sec:02d}",
                fg=_TEXT_SEC,
            ))

        def _thread() -> None:
            token = self._auth.get_token_interactive_force(
                timeout_seconds=_LOGIN_TIMEOUT,
                on_tick=_tick,
            )
            self._login_in_progress = False
            if token:
                self.after(0, self._show_main)
            else:
                self.after(0, lambda: self._login_reset(
                    "❌ Hết 2 phút — đăng nhập bị huỷ. Thử lại."
                ))

        threading.Thread(target=_thread, daemon=True).start()


    def _login_reset(self, msg: str) -> None:
        """Re-enable login button and show a small red error below it."""
        self._login_btn.config(state=tk.NORMAL)
        self._login_status.config(text=msg, fg=_ERROR)

    def _do_logout(self) -> None:
        if self._running:
            self._show_toast("Không thể đăng xuất khi đang quét mail.", "warning")
            return
        if not messagebox.askyesno(
            "Xác nhận đăng xuất",
            "Bạn có chắc muốn đăng xuất?\nLần sau cần đăng nhập lại.",
        ):
            return
        self._auth.logout()
        self._reset_progress()
        self._show_login()
        self._login_status.config(text="Đã đăng xuất.", fg=_TEXT_SEC)

    def _confirm_close_excel(self, locked_files: list) -> bool:
        """
        Synchronous pre-scan dialog shown on the main thread when the Excel
        export file is already open.

        Returns True  → user closed Excel (or it was closed automatically) → OK to proceed.
        Returns False → user cancelled → abort scan.
        """
        result = [False]

        dlg = tk.Toplevel(self)
        dlg.title("File Excel đang mở")
        dlg.resizable(False, False)
        dlg.grab_set()
        dlg.transient(self)
        dlg.configure(bg=_CARD_BG)

        tk.Label(
            dlg, text="⚠  File Excel đang được mở",
            font=(_FONT, 12, "bold"), fg=_WARNING, bg=_CARD_BG,
            padx=20, pady=14,
        ).pack(fill=tk.X)

        names = "\n".join(f"  • {p.name}  ({p.parent.name})" for p in locked_files)
        tk.Label(
            dlg,
            text=(
                f"Các file sau đang mở, không thể ghi dữ liệu:\n{names}\n\n"
                "Nhấn  Đóng Excel  để tự động đóng Excel và bắt đầu quét,\n"
                "hoặc  Hủy  để không quét."
            ),
            font=(_FONT, 9), fg=_TEXT, bg=_CARD_BG,
            justify=tk.LEFT, wraplength=400, padx=20, pady=6,
        ).pack(fill=tk.X)

        btn_row = tk.Frame(dlg, bg=_CARD_BG, padx=20, pady=14)
        btn_row.pack(fill=tk.X)

        close_btn = tk.Button(
            btn_row, text="Đóng Excel & Bắt đầu quét",
            font=(_FONT, 10, "bold"), bg=_PRIMARY, fg=_WHITE,
            activebackground=_PRIMARY_D, activeforeground=_WHITE,
            relief=tk.FLAT, padx=14, pady=8, cursor="hand2", bd=0,
        )
        close_btn.pack(side=tk.LEFT, padx=(0, 8))

        cancel_btn = tk.Button(
            btn_row, text="Hủy",
            font=(_FONT, 10), bg=_BORDER, fg=_TEXT,
            activebackground=_ERROR, activeforeground=_WHITE,
            relief=tk.FLAT, padx=14, pady=8, cursor="hand2", bd=0,
        )
        cancel_btn.pack(side=tk.LEFT)

        def _do_close_excel() -> None:
            close_btn.config(state=tk.DISABLED, text="Đang đóng…", cursor="arrow")
            cancel_btn.config(state=tk.DISABLED)
            try:
                subprocess.run(
                    ["taskkill", "/IM", "EXCEL.EXE"],
                    capture_output=True, timeout=8,
                )
            except Exception:
                pass

            def _finish() -> None:
                result[0] = True
                dlg.destroy()

            dlg.after(2000, _finish)   # wait 2 s for Excel to release files

        def _do_cancel() -> None:
            result[0] = False
            dlg.destroy()

        close_btn.config(command=_do_close_excel)
        cancel_btn.config(command=_do_cancel)

        # Centre on parent
        dlg.update_idletasks()
        px = self.winfo_x() + (self.winfo_width()  - dlg.winfo_width())  // 2
        py = self.winfo_y() + (self.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{px}+{py}")

        self.wait_window(dlg)   # blocks this method; main loop still runs
        return result[0]

    def _do_scan(self) -> None:
        if not self._config or not self._auth:
            return
        if self._running:
            return

        date_from, date_to = self._parse_date_range()
        if date_from is None:
            return   # error already shown

        output_folder = self._export_folder_var.get().strip() or _DEFAULT_EXPORT
        self._last_export_folder = output_folder

        # Apply runtime mail folder override
        if self._config:
            folder_name = self._mail_folder_var.get().strip()
            if folder_name:
                self._config.mail.target_folder_name = folder_name

        # ── Pre-scan: close any open Excel export files first ─────────────────
        excel_filename = self._config.output.excel_filename
        locked = _find_locked_excel_files(pathlib.Path(output_folder), excel_filename)
        if locked:
            if not self._confirm_close_excel(locked):
                return   # user cancelled

        # ── Start scan thread ─────────────────────────────────────────────────
        self._running = True
        self._status_dot.config(fg=_WARNING)
        # Reset only the progress bar/label — stat cards keep pre-loaded values
        self._step_var.set("Đang kết nối…")
        self._pct_var.set("")
        self._progress_bar.set_value(0)
        self._set_scan_state(False)
        start_msg = f"▶ Bắt đầu quét  {date_from.strftime('%d/%m/%Y %H:%M')} → {date_to.strftime('%d/%m/%Y %H:%M')}"
        logger.info(start_msg)
        self._append_log(start_msg)
        self._update_step("Đang kết nối…", 0, 0)

        scan_log_fh = self._add_scan_log_handler(date_from, date_to)

        def _thread() -> None:
            try:
                processor = EmailProcessor(self._config, self._auth)
                result = processor.run(
                    progress=self._on_progress,
                    date_from=date_from,
                    date_to=date_to,
                    output_folder_override=output_folder,
                    on_excel_locked=self._ask_excel_locked,
                )
                self.after(0, lambda: self._on_scan_done(result))
            except AuthRequiredError as exc:
                logger.warning("Auth required — redirecting to login: %s", exc)
                self.after(0, lambda: self._on_auth_required(str(exc)))
            except Exception as exc:
                self.after(0, lambda: self._on_scan_error(str(exc)))
                logger.exception("Scan error")
            finally:
                if scan_log_fh:
                    logging.getLogger().removeHandler(scan_log_fh)
                    scan_log_fh.close()
                self._running = False
                self.after(0, lambda: self._set_scan_state(True))
                self.after(0, lambda: self._status_dot.config(fg=_SUCCESS))

        threading.Thread(target=_thread, daemon=True).start()

    def open_exported_folder(self) -> None:
        self._open_exported_folder()

    def _open_exported_folder(self) -> None:
        folder = pathlib.Path(self._last_export_folder)
        try:
            _open_folder_in_file_manager(folder)
        except Exception as exc:
            logger.warning("Could not open export folder %s: %s", folder, exc)
            messagebox.showerror(
                "Không mở được folder",
                f"Không mở được thư mục export:\n{folder}\n\n{exc}",
            )

    def _ask_excel_locked(self, excel_path) -> bool:
        """
        Called from the scan worker thread when the Excel file is locked.
        Shows a dialog on the main thread and blocks the worker until the
        user responds.

        Returns True  → close Excel automatically and retry the write.
        Returns False → cancel the current scan entirely.
        """
        event  = threading.Event()
        result = [False]   # mutable container so nested closures can write

        def _show() -> None:
            dlg = tk.Toplevel(self)
            dlg.title("File Excel đang mở")
            dlg.resizable(False, False)
            dlg.grab_set()
            dlg.transient(self)
            dlg.configure(bg=_CARD_BG)

            tk.Label(
                dlg, text="⚠  File Excel đang được mở",
                font=(_FONT, 12, "bold"), fg=_WARNING, bg=_CARD_BG,
                padx=20, pady=14,
            ).pack(fill=tk.X)

            name = getattr(excel_path, "name", str(excel_path))
            tk.Label(
                dlg,
                text=(
                    f"Không thể ghi dữ liệu vào:\n{name}\n\n"
                    "Nhấn  Đóng Excel  để tự động đóng Excel và thử lại,\n"
                    "hoặc  Hủy  để dừng quét mail."
                ),
                font=(_FONT, 9), fg=_TEXT, bg=_CARD_BG,
                justify=tk.LEFT, wraplength=380, padx=20, pady=6,
            ).pack(fill=tk.X)

            btn_row = tk.Frame(dlg, bg=_CARD_BG, padx=20, pady=14)
            btn_row.pack(fill=tk.X)

            def _do_close_excel() -> None:
                dlg.destroy()

                def _kill_and_signal() -> None:
                    try:
                        subprocess.run(
                            ["taskkill", "/IM", "EXCEL.EXE"],
                            capture_output=True, timeout=8,
                        )
                    except Exception:
                        pass
                    time.sleep(2.0)   # wait for Excel to fully release the file
                    result[0] = True
                    event.set()

                threading.Thread(target=_kill_and_signal, daemon=True).start()

            def _do_cancel() -> None:
                result[0] = False
                dlg.destroy()
                event.set()

            tk.Button(
                btn_row, text="Đóng Excel & Thử lại",
                command=_do_close_excel,
                font=(_FONT, 10, "bold"), bg=_PRIMARY, fg=_WHITE,
                activebackground=_PRIMARY_D, activeforeground=_WHITE,
                relief=tk.FLAT, padx=14, pady=8, cursor="hand2", bd=0,
            ).pack(side=tk.LEFT, padx=(0, 8))

            tk.Button(
                btn_row, text="Hủy",
                command=_do_cancel,
                font=(_FONT, 10), bg=_BORDER, fg=_TEXT,
                activebackground=_ERROR, activeforeground=_WHITE,
                relief=tk.FLAT, padx=14, pady=8, cursor="hand2", bd=0,
            ).pack(side=tk.LEFT)

            # Centre on parent
            dlg.update_idletasks()
            px = self.winfo_x() + (self.winfo_width()  - dlg.winfo_width())  // 2
            py = self.winfo_y() + (self.winfo_height() - dlg.winfo_height()) // 2
            dlg.geometry(f"+{px}+{py}")

        self.after(0, _show)
        event.wait()          # block worker thread until user responds
        return result[0]

    def _on_close(self) -> None:
        if self._running and not messagebox.askyesno(
            "Đang xử lý", "Đang quét mail. Bạn có chắc muốn đóng không?"
        ):
            return
        self.destroy()

    # ═══════════════════════════════════════════════════════════════════════
    # PROGRESS UPDATES  (called from worker thread via .after())
    # ═══════════════════════════════════════════════════════════════════════

    def _on_progress(
        self, current: int, total: int, message: str, stats: Optional[dict] = None
    ) -> None:
        """Callback from EmailProcessor — dispatched to main thread."""
        self.after(0, lambda: self._update_step(message, current, total, stats))
        self.after(0, lambda: self._append_log(message))

    def _update_step(
        self, message: str, current: int, total: int, stats: Optional[dict] = None
    ) -> None:
        # Update title only for:
        #   • per-email messages   (current > 0)  → "Đang xử lý 1/4: subject"
        #   • top-level setup msgs (total == 0, no leading whitespace)
        #     → "Đang xác thực…", "Tìm thấy X email…", …
        # Sub-messages inside _process_one all start with spaces ("  ↳ …")
        # and must NOT clobber the title or reset the progress bar.
        is_sub_message = total == 0 and message.startswith(" ")
        if not is_sub_message:
            self._step_var.set(message.strip())

        if total > 0 and current > 0:
            # Progress = emails *completed* before the current one:
            #   1/4 → 0 %,  2/4 → 25 %,  3/4 → 50 %,  4/4 → 75 %
            pct = int((current - 1) / total * 100)
            self._progress_bar.set_value(pct)

            success = stats.get("success", 0) if stats else 0
            error   = stats.get("error",   0) if stats else 0
            self._pct_var.set(
                f"{total} email tìm thấy  •  {success} thành công  •  {error} lỗi"
            )

            # Dashboard: show pre-loaded + current scan counts
            base_total = self._base_stats.get("total", 0)
            base_done  = self._base_stats.get("success", 0) + self._base_stats.get("file_err", 0) + self._base_stats.get("missing_data", 0)
            self._dash_found[1].set(str(base_total + total))
            self._dash_processing[1].set(str(total - current + 1))
            self._dash_done[1].set(str(base_done + current - 1))
        elif not is_sub_message:
            # Setup phase — reset bar but keep any subtitle already set
            self._progress_bar.set_value(0)
            self._pct_var.set("")

        if stats:
            b = self._base_stats
            self._stat_ok[1].set(str(b.get("success", 0) + stats.get("success", 0)))
            self._stat_file_err[1].set(str(b.get("file_err", 0) + stats.get("file_err", 0)))
            self._stat_missing[1].set(str(b.get("missing_data", 0) + stats.get("missing_data", 0)))
            self._stat_dup[1].set(str(b.get("dup", 0) + stats.get("dup", 0)))
            self._stat_err[1].set(str(b.get("error", 0) + stats.get("error", 0)))

    def _on_scan_done(self, result: ProcessResult) -> None:
        total = result.total_emails
        extracted = result.success_count + result.review_count
        # Progress bar: 100% only if no errors; otherwise proportional to successes
        if total == 0:
            self._progress_bar.set_value(0)
            msg = "⚠  Không tìm thấy email nào trong khoảng thời gian này"
            self._step_var.set(msg)
            self._append_log(msg)
        elif result.error_count == 0:
            self._progress_bar.set_value(100)
            msg = "✅  Hoàn thành"
            self._step_var.set(msg)
            self._append_log(msg)
            self._show_toast("Quét mail hoàn thành!", "success")
        else:
            ok_pct = int(extracted / total * 100)
            self._progress_bar.set_value(ok_pct)
            msg = f"⚠  Xong: {result.success_count} thành công, {result.error_count} lỗi"
            self._step_var.set(msg)
            self._append_log(msg)
            self._show_toast(f"{result.error_count} email bị lỗi", "warning")

        self._pct_var.set(
            f"{total} email tìm thấy  •  "
            f"{result.success_count} thành công  •  "
            f"{result.error_count} lỗi"
        )

        # Stat cards: accumulate scan result on top of pre-loaded baseline
        b = self._base_stats
        self._stat_ok[1].set(str(b.get("success", 0) + result.success_count))
        self._stat_file_err[1].set(str(b.get("file_err", 0) + result.file_error_count))
        self._stat_missing[1].set(str(b.get("missing_data", 0) + result.missing_data_count))
        self._stat_dup[1].set(str(b.get("dup", 0) + result.duplicate_count))
        self._stat_err[1].set(str(b.get("error", 0) + result.error_count))

        # Dashboard final values
        base_total = b.get("total", 0)
        base_done  = b.get("success", 0) + b.get("file_err", 0) + b.get("missing_data", 0)
        self._dash_found[1].set(str(base_total + total))
        self._dash_processing[1].set("0")
        self._dash_done[1].set(str(base_done + extracted))

        # Update baseline so subsequent scans also accumulate correctly
        self._base_stats = {
            "success":      b.get("success", 0) + result.success_count,
            "file_err":     b.get("file_err", 0) + result.file_error_count,
            "missing_data": b.get("missing_data", 0) + result.missing_data_count,
            "dup":          b.get("dup", 0) + result.duplicate_count,
            "error":        b.get("error", 0) + result.error_count,
            "total":        base_total + total,
        }

        # Show "open folder" button whenever scan finishes
        if total >= 0:
            self._open_export_btn.pack(side=tk.LEFT, padx=(12, 0))

    def _on_scan_error(self, msg: str) -> None:
        self._step_var.set(f"❌  Lỗi: {msg[:80]}")
        self._pct_var.set("Kiểm tra kết nối và thử lại.")
        self._progress_bar.set_value(0)
        self._append_log(f"❌ Lỗi: {msg}")
        self._show_toast(f"Lỗi: {msg[:60]}", "error", 5000)

    def _on_auth_required(self, reason: str) -> None:
        """Called when authentication completely fails — clear cache and go to login screen."""
        self._append_log(f"🔐 Cần đăng nhập lại: {reason}")
        logger.warning("Returning to login screen: %s", reason)
        if self._auth:
            try:
                self._auth.logout()
            except Exception:
                pass
        self._show_login()
        self._login_status.config(
            text=f"⚠ Phiên đăng nhập hết hạn hoặc tài khoản bị khóa.\n{reason}",
            fg=_ERROR,
        )

    def _reset_progress(self) -> None:
        self._step_var.set("Sẵn sàng")
        self._pct_var.set("")
        self._progress_bar.set_value(0)
        self._stat_ok[1].set("0")
        self._stat_file_err[1].set("0")
        self._stat_missing[1].set("0")
        self._stat_dup[1].set("0")
        self._stat_err[1].set("0")
        self._dash_found[1].set("0")
        self._dash_processing[1].set("0")
        self._dash_done[1].set("0")
        self._open_export_btn.pack_forget()

    def _set_scan_state(self, enabled: bool) -> None:
        """Enable/disable controls during a scan."""
        state_btn    = tk.NORMAL   if enabled else tk.DISABLED
        state_entry  = "normal"    if enabled else "disabled"
        state_combo  = "readonly"  if enabled else "disabled"
        cursor_btn   = "hand2"     if enabled else "arrow"

        if enabled:
            self._scan_btn.config(state=state_btn, bg=_PRIMARY, fg=_WHITE, cursor=cursor_btn)
            self._logout_btn.config(state=state_btn, bg=_HEADER_LIGHT, fg="#94A3B8", cursor=cursor_btn)
            self._choose_folder_btn.config(state=state_btn, bg=_BORDER, fg=_TEXT, cursor=cursor_btn)
        else:
            self._scan_btn.config(state=state_btn, bg=_DISABLED_BG, fg=_DISABLED_FG, cursor=cursor_btn)
            self._logout_btn.config(state=state_btn, bg=_DISABLED_BG, fg=_DISABLED_FG, cursor=cursor_btn)
            self._choose_folder_btn.config(state=state_btn, bg=_DISABLED_BG, fg=_DISABLED_FG, cursor=cursor_btn)

        self._from_date_entry.config(state=state_entry)
        self._to_date_entry.config(state=state_entry)
        self._mail_folder_entry.config(state=state_entry)
        self._auto_scan_freq_cb.config(state=state_combo)
        self._auto_scan_cb.config(state=state_btn)

    # ═══════════════════════════════════════════════════════════════════════
    # AUTO-SCAN SCHEDULER
    # ═══════════════════════════════════════════════════════════════════════

    def _start_scheduler(self) -> None:
        """
        Initialise the last-fired key and start the background scheduler thread.
        The key is (day_of_year, hour) so the same hour on different days both fire.
        If started exactly inside a scheduled window, mark it as already fired
        so the user doesn't get an unexpected immediate scan on app launch.
        """
        now    = datetime.now()
        freq_h = _FREQ_HOURS.get(self._auto_scan_freq_var.get(), 1)
        if now.hour % freq_h == 0 and now.minute < 2:
            # App started right at a scheduled moment — skip this one
            self._last_auto_scan_slot = (now.timetuple().tm_yday, now.hour)
        else:
            self._last_auto_scan_slot = (-1, -1)   # fire at next scheduled hour
        threading.Thread(target=self._scheduler_loop, daemon=True).start()

    def _scheduler_loop(self) -> None:
        """
        Runs every 30 s in a daemon thread.  Fires an auto-scan **only** when:
          • auto-scan is enabled
          • no scan is currently running
          • current hour is a multiple of the configured frequency  ← key fix
          • we are in the first 2 minutes of that hour              ← key fix
          • this (day, hour) slot has not been fired yet

        Example — freq = 4 h:
          Fires at 00:00–00:01, 04:00–04:01, 08:00–08:01, 12:00–12:01, …
          Will NEVER fire at 09:41 because 9 % 4 ≠ 0.

        Example — freq = 1 h:
          Fires at 00:00–00:01, 01:00–01:01, 02:00–02:01, … every whole hour.
        """
        while True:
            time.sleep(30)
            try:
                if not self._auto_scan_var.get():
                    continue
                if self._running:
                    continue
                freq_h = _FREQ_HOURS.get(self._auto_scan_freq_var.get(), 1)
                now    = datetime.now()
                # Only fire at scheduled hours and within the first 2 minutes
                if now.hour % freq_h != 0 or now.minute >= 2:
                    continue
                key = (now.timetuple().tm_yday, now.hour)
                if key != self._last_auto_scan_slot:
                    self._last_auto_scan_slot = key
                    self.after(0, self._do_auto_scan)
            except Exception:
                pass

    def _do_auto_scan(self) -> None:
        """Trigger a scan using the currently configured date range (called by the scheduler)."""
        now = datetime.now()
        msg = f"⏰ Auto-scan triggered at {now.strftime('%H:%M')}"
        logger.info(msg)
        self._append_log(msg)
        self._show_toast(f"Auto-scan bắt đầu lúc {now.strftime('%H:%M')}", "info", 2000)
        self._do_scan()


# ── Run ────────────────────────────────────────────────────────────────────

def _find_locked_excel_files(root: pathlib.Path, excel_filename: str) -> list:
    """
    Return a list of Excel files inside *root* that are currently open.
    Excel on Windows always creates a  ~$<filename>  lock file next to any
    open workbook — we use that as a reliable open-file indicator.
    """
    locked = []
    try:
        for path in root.rglob(excel_filename):
            if (path.parent / f"~${excel_filename}").exists():
                locked.append(path)
    except OSError:
        pass
    return locked


def run_gui() -> None:
    app = CongVanApp()
    app.mainloop()
