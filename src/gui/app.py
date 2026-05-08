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
from ..version import __version__

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────
_NAVY       = "#1A2E4A"
_NAVY_LIGHT = "#243D5E"
_BLUE       = "#2E75B6"
_WHITE      = "#FFFFFF"
_BG         = "#F4F6F9"
_CARD_BG    = "#FFFFFF"
_BORDER     = "#DDE3EC"
_TEXT       = "#1C1C1E"
_TEXT_MUTED = "#6B7280"
_GREEN      = "#27AE60"
_ORANGE     = "#E67E22"
_RED        = "#E74C3C"
_FONT       = "Segoe UI"
_VERSION    = __version__

# Disabled button appearance — neutral gray so text is still legible
_DISABLED_BG = "#9CA3AF"
_DISABLED_FG = "#F3F4F6"

_APP_TITLE  = "Xử lý Mail công văn"

_DEFAULT_EXPORT  = str(pathlib.Path.home() / "Desktop" / "CongVanExport")
_LOGIN_TIMEOUT   = 120   # seconds — countdown before auto-reset

# Auto-scan frequency options (display label → hours)
_FREQ_HOURS: dict = {
    "1 giờ": 1, "2 giờ": 2, "4 giờ": 4, "6 giờ": 6,
    "8 giờ": 8, "12 giờ": 12, "24 giờ": 24,
}
_FREQ_LABELS = list(_FREQ_HOURS.keys())


def _read_range_stats(date_from: datetime, date_to: datetime, date_folder_format: str) -> dict:
    """
    Read _processed.json files for each day in [date_from, date_to] and sum counts.
    Returns a dict with keys: success, file_err, scan, missing_data, dup, error, total.
    """
    stats = {"success": 0, "file_err": 0, "scan": 0, "missing_data": 0, "dup": 0, "error": 0, "total": 0}
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


class CongVanApp(tk.Tk):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.title(_APP_TITLE)
        self.geometry("640x730")
        self.minsize(580, 680)
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
        self._base_stats: dict = {"success": 0, "file_err": 0, "scan": 0, "missing_data": 0, "dup": 0, "error": 0, "total": 0}

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

        tk.Label(f, text="", bg=_BG, height=3).pack()
        tk.Label(f, text="📬", font=(_FONT, 48), bg=_BG, fg=_NAVY).pack()

        tk.Label(
            f, text=_APP_TITLE,
            font=(_FONT, 20, "bold"), bg=_BG, fg=_NAVY,
        ).pack(pady=(6, 2))

        tk.Label(
            f, text="Tự động xử lý công văn từ Cục Sở hữu trí tuệ",
            font=(_FONT, 10), bg=_BG, fg=_TEXT_MUTED,
        ).pack()

        tk.Label(f, text="", bg=_BG, height=2).pack()

        self._login_btn = tk.Button(
            f, text="🔑   Đăng nhập Microsoft",
            command=self._do_login,
            font=(_FONT, 12, "bold"),
            bg=_BLUE, fg=_WHITE,
            activebackground=_NAVY, activeforeground=_WHITE,
            relief=tk.FLAT, padx=30, pady=12, cursor="hand2", bd=0,
        )
        self._login_btn.pack(ipadx=10)

        self._login_status = tk.Label(
            f, text="",
            font=(_FONT, 9), bg=_BG, fg=_TEXT_MUTED,
        )
        self._login_status.pack(pady=10)

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
        header = tk.Frame(f, bg=_NAVY, pady=12)
        header.pack(fill=tk.X)

        tk.Label(
            header, text=f"📬  {_APP_TITLE}",
            font=(_FONT, 13, "bold"), bg=_NAVY, fg=_WHITE,
        ).pack(side=tk.LEFT, padx=18)

        self._logout_btn = tk.Button(
            header, text="Đăng xuất",
            command=self._do_logout,
            font=(_FONT, 8), bg=_NAVY_LIGHT, fg="#AAC4E0",
            activebackground=_RED, activeforeground=_WHITE,
            relief=tk.FLAT, padx=10, pady=4, cursor="hand2", bd=0,
        )
        self._logout_btn.pack(side=tk.RIGHT, padx=12)

        tk.Label(
            header, text=f"v{__version__}",
            font=(_FONT, 8), bg=_NAVY, fg="#6B8CAE",
        ).pack(side=tk.RIGHT, padx=(0, 8))

        self._user_label = tk.Label(
            header, text="",
            font=(_FONT, 9), bg=_NAVY, fg="#AAC4E0",
        )
        self._user_label.pack(side=tk.RIGHT, padx=4)

        # ── Notebook (2 tabs) ──────────────────────────────────────────────
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "CongVan.Horizontal.TProgressbar",
            troughcolor=_BORDER, background=_BLUE,
            thickness=14, borderwidth=0,
        )

        # ── Footer (packed first so it anchors to the bottom) ──────────────
        tk.Label(
            f, text=f"v{_VERSION}  •  Powered by Microsoft Graph API",
            font=(_FONT, 8), bg=_BG, fg=_TEXT_MUTED,
        ).pack(side=tk.BOTTOM, pady=6)

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
                    btn.config(fg=_NAVY,      font=(_FONT, 9, "bold"))
                    bar.config(bg=_BLUE)
                else:
                    btn.config(fg=_TEXT_MUTED, font=(_FONT, 9))
                    bar.config(bg=_CARD_BG)

        self._switch_tab = _switch_tab

        for tab_name, tab_label in [("main", "Main"), ("activities", "Activities")]:
            cell = tk.Frame(tab_bar, bg=_CARD_BG)
            cell.pack(side=tk.LEFT)
            btn = tk.Button(
                cell, text=tab_label,
                command=lambda n=tab_name: _switch_tab(n),
                font=(_FONT, 9), bg=_CARD_BG, fg=_TEXT_MUTED,
                relief=tk.FLAT, bd=0, padx=18, pady=9,
                cursor="hand2",
                activebackground=_CARD_BG, activeforeground=_NAVY,
            )
            btn.pack()
            indicator = tk.Frame(cell, bg=_CARD_BG, height=3)
            indicator.pack(fill=tk.X)
            self._tab_buttons[tab_name] = (btn, indicator)

        _switch_tab("main")

        return f

    def _build_main_tab(self, f: tk.Frame) -> None:
        """Build all widgets for Tab 1 — Main."""

        # ── Config card — grid layout for clean alignment ──────────────────
        cfg_card = tk.Frame(
            f, bg=_CARD_BG,
            highlightbackground=_BORDER, highlightthickness=1,
        )
        cfg_card.pack(fill=tk.X, padx=20, pady=(12, 4))

        g = tk.Frame(cfg_card, bg=_CARD_BG, padx=16, pady=12)
        g.pack(fill=tk.X)
        g.columnconfigure(1, weight=1)   # input column stretches

        def _lbl(text, row, col=0, **kw):
            tk.Label(
                g, text=text,
                font=(_FONT, 9), bg=_CARD_BG, fg=_TEXT_MUTED,
                anchor="e",
            ).grid(row=row, column=col, sticky="e", padx=(0, 8), pady=4, **kw)

        today = datetime.now()

        # Row 0 — date range
        _lbl("Từ:", 0)
        date_cells = tk.Frame(g, bg=_CARD_BG)
        date_cells.grid(row=0, column=1, sticky="w", pady=4)

        self._from_date_var = tk.StringVar(value=today.strftime("%d/%m/%Y 00:00"))
        self._from_date_entry = ttk.Entry(
            date_cells, textvariable=self._from_date_var, width=16, font=(_FONT, 9),
        )
        self._from_date_entry.pack(side=tk.LEFT)
        self._from_date_entry.bind("<FocusOut>", lambda _e: self._load_and_show_stats())
        self._from_date_entry.bind("<Return>",   lambda _e: self._load_and_show_stats())

        tk.Label(
            date_cells, text="  —  Đến:",
            font=(_FONT, 9), bg=_CARD_BG, fg=_TEXT_MUTED,
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

        # Row 1 — sender email
        _lbl("Email người gửi:", 1)
        self._sender_email_var = tk.StringVar(value="cucsohuutritue@ipvietnam.gov.vn")
        self._sender_email_entry = ttk.Entry(
            g, textvariable=self._sender_email_var, font=(_FONT, 9), width=34,
        )
        self._sender_email_entry.grid(row=1, column=1, sticky="w", pady=4)

        # Row 2 — export folder
        _lbl("Export vào:", 2)
        export_row = tk.Frame(g, bg=_CARD_BG)
        export_row.grid(row=2, column=1, sticky="ew", pady=4)
        export_row.columnconfigure(0, weight=1)

        self._export_folder_var = tk.StringVar(value=_DEFAULT_EXPORT)
        ttk.Entry(
            export_row, textvariable=self._export_folder_var, font=(_FONT, 9),
        ).grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self._choose_folder_btn = tk.Button(
            export_row, text="📁  Chọn…",
            command=self._do_choose_folder,
            font=(_FONT, 9), bg=_BORDER, fg=_TEXT,
            activebackground=_NAVY_LIGHT, activeforeground=_WHITE,
            relief=tk.FLAT, padx=8, pady=4, cursor="hand2", bd=0,
        )
        self._choose_folder_btn.grid(row=0, column=1)

        # Row 3 — auto-scan
        _lbl("Tự động quét:", 3)
        auto_cells = tk.Frame(g, bg=_CARD_BG)
        auto_cells.grid(row=3, column=1, sticky="w", pady=4)

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
            font=(_FONT, 9), bg=_CARD_BG, fg=_TEXT_MUTED,
        ).pack(side=tk.LEFT)

        self._auto_scan_freq_var = tk.StringVar(value="1 giờ")
        self._auto_scan_freq_cb = ttk.Combobox(
            auto_cells, textvariable=self._auto_scan_freq_var,
            values=_FREQ_LABELS, state="readonly", width=7,
            font=(_FONT, 9),
        )
        self._auto_scan_freq_cb.pack(side=tk.LEFT, padx=(4, 0))

        # ── Action buttons ─────────────────────────────────────────────────
        self._btn_row = tk.Frame(f, bg=_BG, pady=12)
        self._btn_row.pack(fill=tk.X, padx=20)

        self._scan_btn = self._big_btn(
            self._btn_row, "📥   Quét mail", self._do_scan, _BLUE,
        )
        self._scan_btn.pack(side=tk.LEFT, padx=(0, 0))

        # "Mở folder" — hidden until first successful export
        self._open_export_btn = self._big_btn(
            self._btn_row, "📂   Mở folder export",
            self._open_exported_folder, _GREEN,
        )
        # Not packed yet — shown in _on_scan_done

        # ── Progress card ──────────────────────────────────────────────────
        card = tk.Frame(
            f, bg=_CARD_BG, relief=tk.FLAT, bd=1,
            highlightbackground=_BORDER, highlightthickness=1,
        )
        card.pack(fill=tk.X, padx=20)

        inner = tk.Frame(card, bg=_CARD_BG, padx=16, pady=12)
        inner.pack(fill=tk.X)

        self._step_var = tk.StringVar(value="Sẵn sàng")
        tk.Label(
            inner, textvariable=self._step_var,
            font=(_FONT, 10, "bold"), bg=_CARD_BG, fg=_TEXT,
            anchor="w", justify=tk.LEFT, wraplength=500,
        ).pack(fill=tk.X)

        self._pct_var = tk.StringVar(value="")
        tk.Label(
            inner, textvariable=self._pct_var,
            font=(_FONT, 9), bg=_CARD_BG, fg=_TEXT_MUTED, anchor="w",
        ).pack(fill=tk.X)

        pb_frame = tk.Frame(inner, bg=_CARD_BG, pady=8)
        pb_frame.pack(fill=tk.X)

        self._progress_bar = ttk.Progressbar(
            pb_frame, style="CongVan.Horizontal.TProgressbar",
            orient="horizontal", length=300, mode="determinate",
        )
        self._progress_bar.pack(fill=tk.X)
        self._progress_bar["value"] = 0

        # ── Dashboard row (3 cards) ─────────────────────────────────────────
        dash_row = tk.Frame(f, bg=_BG, pady=10)
        dash_row.pack(fill=tk.X, padx=20)

        self._dash_found      = self._stat_card(dash_row, "📬 Đã tìm thấy",  "0", _NAVY)
        self._dash_processing = self._stat_card(dash_row, "⏳ Đang tải về",   "0", _ORANGE)
        self._dash_done       = self._stat_card(dash_row, "✅ Đã tải về",     "0", _GREEN)

        for w in (self._dash_found[0], self._dash_processing[0], self._dash_done[0]):
            w.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=4)

        # ── Stats row (4 cards) ────────────────────────────────────────────
        stats_row = tk.Frame(f, bg=_BG, pady=2)
        stats_row.pack(fill=tk.X, padx=20)

        self._stat_ok          = self._stat_card(stats_row, "✓ File pdf chuẩn",      "0", _GREEN)
        self._stat_file_err    = self._stat_card(stats_row, "⚠ Lỗi tải về",          "0", _ORANGE)
        self._stat_scan        = self._stat_card(stats_row, "🔍 File scan",           "0", _ORANGE)
        self._stat_read_err    = self._stat_card(stats_row, "✗ File đọc lỗi",        "0", _RED)
        self._stat_dup         = self._stat_card(stats_row, "⟳ File đã xử lý",      "0", _TEXT_MUTED)

        for w in (self._stat_ok[0], self._stat_file_err[0], self._stat_scan[0],
                  self._stat_read_err[0], self._stat_dup[0]):
            w.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=4)

    def _build_activities_tab(self, f: tk.Frame) -> None:
        """Build all widgets for Tab 2 — Activities."""
        outer = tk.Frame(f, bg=_BG)
        outer.pack(fill=tk.BOTH, expand=True, padx=20, pady=12)

        hdr = tk.Frame(outer, bg=_BG)
        hdr.pack(fill=tk.X, pady=(0, 6))

        tk.Label(
            hdr, text="📋  Nhật ký hoạt động",
            font=(_FONT, 10, "bold"), bg=_BG, fg=_TEXT,
        ).pack(side=tk.LEFT)

        tk.Button(
            hdr, text="Xoá",
            command=self._clear_log,
            font=(_FONT, 8), bg=_BORDER, fg=_TEXT_MUTED,
            activebackground=_RED, activeforeground=_WHITE,
            relief=tk.FLAT, padx=8, pady=3, cursor="hand2", bd=0,
        ).pack(side=tk.RIGHT)

        tk.Button(
            hdr, text="🗑 Clear processed",
            command=self._clear_processed,
            font=(_FONT, 8), bg=_BORDER, fg=_TEXT_MUTED,
            activebackground=_RED, activeforeground=_WHITE,
            relief=tk.FLAT, padx=8, pady=3, cursor="hand2", bd=0,
        ).pack(side=tk.RIGHT, padx=(0, 6))

        self._log_text = scrolledtext.ScrolledText(
            outer, state=tk.DISABLED,
            font=("Consolas", 8), bg="#F8F9FA", fg=_TEXT,
            relief=tk.FLAT, padx=10, pady=8,
            wrap=tk.WORD,
        )
        self._log_text.pack(fill=tk.BOTH, expand=True)



    # ═══════════════════════════════════════════════════════════════════════
    # WIDGET HELPERS
    # ═══════════════════════════════════════════════════════════════════════

    def _big_btn(self, parent, text, cmd, color) -> tk.Button:
        return tk.Button(
            parent, text=text, command=cmd,
            font=(_FONT, 11, "bold"), bg=color, fg=_WHITE,
            activebackground=_NAVY, activeforeground=_WHITE,
            disabledforeground=_DISABLED_FG,
            relief=tk.FLAT, padx=18, pady=10, cursor="hand2", bd=0,
        )

    def _stat_card(self, parent, label: str, value: str, color: str):
        """Returns (frame, value_var)."""
        card = tk.Frame(
            parent, bg=_CARD_BG,
            highlightbackground=_BORDER, highlightthickness=1,
        )
        inner = tk.Frame(card, bg=_CARD_BG, padx=8, pady=8)
        inner.pack(fill=tk.BOTH, expand=True)

        val_var = tk.StringVar(value=value)
        tk.Label(
            inner, textvariable=val_var,
            font=(_FONT, 20, "bold"), bg=_CARD_BG, fg=color,
        ).pack()
        tk.Label(
            inner, text=label,
            font=(_FONT, 8), bg=_CARD_BG, fg=_TEXT_MUTED,
        ).pack()
        return card, val_var

    # ═══════════════════════════════════════════════════════════════════════
    # LOG PANEL HELPERS
    # ═══════════════════════════════════════════════════════════════════════

    def _append_log(self, message: str) -> None:
        """Append a timestamped line to the log panel (must be called on main thread)."""
        try:
            ts = datetime.now().strftime("%H:%M:%S")
            line = f"[{ts}] {message.strip()}\n"
            self._log_text.config(state=tk.NORMAL)
            self._log_text.insert(tk.END, line)
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

    def _clear_processed(self) -> None:
        tool_root = Path.home() / ".tool_mail_cong_van"
        files = list(tool_root.rglob("_processed.json")) if tool_root.exists() else []
        if not files:
            messagebox.showinfo("Clear processed", "Không có file _processed.json nào.")
            return
        msg = f"Xóa {len(files)} file _processed.json?\n\n" + "\n".join(str(f) for f in files)
        if not messagebox.askyesno("Xác nhận", msg):
            return
        deleted, errors = 0, []
        for f in files:
            try:
                f.unlink()
                deleted += 1
            except OSError as e:
                errors.append(f"{f.name}: {e}")
        summary = f"Đã xóa {deleted}/{len(files)} file."
        if errors:
            summary += "\nLỗi:\n" + "\n".join(errors)
        messagebox.showinfo("Clear processed", summary)
        self._append_log(f"[Clear processed] {summary}")

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
            self._sender_email_var.set(self._config.mail.sender_email)
        except (FileNotFoundError, ValueError) as exc:
            self._show_login()
            self._login_status.config(
                text=f"⚠ Lỗi config: {exc}", fg=_RED,
            )
            return

        if self._auth.is_authenticated():
            self._show_main()
        else:
            self._show_login()

    def _show_login(self) -> None:
        self._main_frame.pack_forget()
        self._login_frame.pack(fill=tk.BOTH, expand=True)
        self.geometry("480x400")

    def _show_main(self) -> None:
        self._login_in_progress = False
        self._login_frame.pack_forget()
        self._main_frame.pack(fill=tk.BOTH, expand=True)
        self.geometry("640x730")
        user = self._auth.get_username() or ""
        self._user_label.config(text=user)
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
        self._stat_scan[1].set(str(stats.get("scan", 0)))
        scan    = stats.get("scan", 0)
        f_err   = stats.get("file_err", 0)
        self._stat_read_err[1].set(str(scan + f_err))
        self._stat_dup[1].set(str(stats.get("dup", 0)))
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
        self._login_status.config(text="Đang mở trình duyệt…", fg=_TEXT_MUTED)

        def _tick(remaining: int) -> None:
            """Called every second by get_token_interactive_force (worker thread)."""
            mins = remaining // 60
            sec  = remaining % 60
            self.after(0, lambda r=remaining: self._login_status.config(
                text=f"Đang chờ trong trình duyệt…  {mins}:{sec:02d}",
                fg=_TEXT_MUTED,
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
        self._login_status.config(text=msg, fg=_RED)

    def _do_logout(self) -> None:
        if self._running:
            messagebox.showwarning("Đang xử lý", "Không thể đăng xuất khi đang quét mail.")
            return
        if not messagebox.askyesno(
            "Xác nhận đăng xuất",
            "Bạn có chắc muốn đăng xuất?\nLần sau cần đăng nhập lại.",
        ):
            return
        self._auth.logout()
        self._reset_progress()
        self._show_login()
        self._login_status.config(text="Đã đăng xuất.", fg=_TEXT_MUTED)

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
            font=(_FONT, 12, "bold"), fg=_ORANGE, bg=_CARD_BG,
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
            font=(_FONT, 10, "bold"), bg=_BLUE, fg=_WHITE,
            activebackground=_NAVY, activeforeground=_WHITE,
            relief=tk.FLAT, padx=14, pady=8, cursor="hand2", bd=0,
        )
        close_btn.pack(side=tk.LEFT, padx=(0, 8))

        cancel_btn = tk.Button(
            btn_row, text="Hủy",
            font=(_FONT, 10), bg=_BORDER, fg=_TEXT,
            activebackground=_RED, activeforeground=_WHITE,
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

        # Apply sender email override
        if self._config:
            sender = self._sender_email_var.get().strip()
            if sender:
                self._config.mail.sender_email = sender

        # ── Pre-scan: close any open Excel export files first ─────────────────
        excel_filename = self._config.output.excel_filename
        locked = _find_locked_excel_files(pathlib.Path(output_folder), excel_filename)
        if locked:
            if not self._confirm_close_excel(locked):
                return   # user cancelled

        # ── Start scan thread ─────────────────────────────────────────────────
        self._running = True
        # Reset all stats and progress before each scan
        self._reset_progress()
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
                font=(_FONT, 12, "bold"), fg=_ORANGE, bg=_CARD_BG,
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
                font=(_FONT, 10, "bold"), bg=_BLUE, fg=_WHITE,
                activebackground=_NAVY, activeforeground=_WHITE,
                relief=tk.FLAT, padx=14, pady=8, cursor="hand2", bd=0,
            ).pack(side=tk.LEFT, padx=(0, 8))

            tk.Button(
                btn_row, text="Hủy",
                command=_do_cancel,
                font=(_FONT, 10), bg=_BORDER, fg=_TEXT,
                activebackground=_RED, activeforeground=_WHITE,
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
            self._progress_bar["value"] = pct

            success = stats.get("success", 0) if stats else 0
            error   = stats.get("error",   0) if stats else 0
            self._pct_var.set(f"{pct}%")

            # Dashboard: live counts during scan (no base accumulation)
            self._dash_found[1].set(str(total))
            self._dash_processing[1].set(str(total - current + 1))
            self._dash_done[1].set(str(stats.get("downloaded", 0)) if stats else "0")

        if stats:
            self._stat_ok[1].set(str(stats.get("success", 0)))
            self._stat_file_err[1].set(str(stats.get("file_err", 0)))
            scan  = stats.get("scan", 0)
            f_err = stats.get("file_err", 0)
            self._stat_scan[1].set(str(scan))
            self._stat_read_err[1].set(str(scan + f_err))
            self._stat_dup[1].set(str(stats.get("dup", 0)))

    def _on_scan_done(self, result: ProcessResult) -> None:
        total = result.total_emails
        extracted = result.success_count + result.review_count
        # Progress bar: 100% only if no errors; otherwise proportional to successes
        if total == 0:
            self._progress_bar["value"] = 0
            msg = "⚠  Không tìm thấy email nào trong khoảng thời gian này"
            self._step_var.set(msg)
            self._append_log(msg)
        elif result.error_count == 0:
            self._progress_bar["value"] = 100
            msg = "✅  Hoàn thành"
            self._step_var.set(msg)
            self._append_log(msg)
        else:
            ok_pct = int(extracted / total * 100)
            self._progress_bar["value"] = ok_pct
            msg = f"⚠  Xong: {result.success_count} thành công, {result.error_count} lỗi"
            self._step_var.set(msg)
            self._append_log(msg)

        self._pct_var.set("")

        # Stat cards: set directly from this scan's result (no base accumulation)
        self._stat_ok[1].set(str(result.success_count))
        self._stat_file_err[1].set(str(result.file_error_count))
        self._stat_scan[1].set(str(result.scan_count))
        self._stat_read_err[1].set(str(result.scan_count + result.file_error_count))
        self._stat_dup[1].set(str(result.duplicate_count))

        # Dashboard final values
        self._dash_found[1].set(str(total))
        self._dash_processing[1].set("0")
        self._dash_done[1].set(str(result.downloaded_file_count))

        # Update baseline so subsequent scans also accumulate correctly
        self._base_stats = {
            "success":      b.get("success", 0) + result.success_count,
            "file_err":     f_err,
            "scan":         scan,
            "missing_data": b.get("missing_data", 0) + result.missing_data_count,
            "dup":          0,  # reset each scan; next scan will count fresh duplicates
            "error":        b.get("error", 0) + result.error_count,
            "total":        base_total + total - result.duplicate_count,
        }

        # Show "open folder" button whenever scan finishes
        if total >= 0:
            self._open_export_btn.pack(side=tk.LEFT, padx=(12, 0))

    def _on_scan_error(self, msg: str) -> None:
        self._step_var.set(f"❌  Lỗi: {msg[:80]}")
        self._pct_var.set("Kiểm tra kết nối và thử lại.")
        self._progress_bar["value"] = 0
        self._append_log(f"❌ Lỗi: {msg}")

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
            fg=_RED,
        )

    def _reset_progress(self) -> None:
        self._step_var.set("Sẵn sàng")
        self._pct_var.set("")
        self._progress_bar["value"] = 0
        self._stat_ok[1].set("0")
        self._stat_file_err[1].set("0")
        self._stat_scan[1].set("0")
        self._stat_read_err[1].set("0")
        self._stat_dup[1].set("0")
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
            self._scan_btn.config(state=state_btn, bg=_BLUE, fg=_WHITE, cursor=cursor_btn)
            self._logout_btn.config(state=state_btn, bg=_NAVY_LIGHT, fg="#AAC4E0", cursor=cursor_btn)
            self._choose_folder_btn.config(state=state_btn, bg=_BORDER, fg=_TEXT, cursor=cursor_btn)
        else:
            self._scan_btn.config(state=state_btn, bg=_DISABLED_BG, fg=_DISABLED_FG, cursor=cursor_btn)
            self._logout_btn.config(state=state_btn, bg=_DISABLED_BG, fg=_DISABLED_FG, cursor=cursor_btn)
            self._choose_folder_btn.config(state=state_btn, bg=_DISABLED_BG, fg=_DISABLED_FG, cursor=cursor_btn)

        self._from_date_entry.config(state=state_entry)
        self._to_date_entry.config(state=state_entry)
        self._sender_email_entry.config(state=state_entry)
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
