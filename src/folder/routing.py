"""
Daily folder routing.

Rules (CRITICAL — do not change):
  - The folder name is ALWAYS derived from the email's receivedDateTime.
  - It is NEVER derived from the current run date / datetime.now().
  - The email's receivedDateTime from Graph is UTC; we convert to local time
    before computing the folder name, so that emails sent at 23:00 UTC do not
    land in the wrong local-date folder.

Fallback:
  - If root_folder is unreachable (e.g. WinError 53 — network path not found),
    automatically fall back to fallback_output_folder.
  - fallback_output_folder="" → ~/Desktop/ToolXuLyMailCongVan
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple

logger = logging.getLogger(__name__)


def parse_received_datetime(received_str: str) -> datetime:
    """
    Parse the ISO 8601 UTC string returned by Microsoft Graph API.
    Returns a timezone-aware datetime in UTC.
    """
    s = received_str.rstrip("Z")
    if "." in s:
        s = s[:19]
    dt = datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")
    return dt.replace(tzinfo=timezone.utc)


def to_local(utc_dt: datetime) -> datetime:
    return utc_dt.astimezone(tz=None)


def get_date_folder_name(
    received_datetime_str: str,
    date_format: str = "%y.%m.%d",
) -> str:
    """
    Compute the folder name for an email based on its received date (local time).
    E.g. "2026-04-14T08:30:00Z" → "26.04.14"
    """
    utc_dt = parse_received_datetime(received_datetime_str)
    local_dt = to_local(utc_dt)
    return local_dt.strftime(date_format)


def _default_fallback_root() -> Path:
    """~/Desktop/ToolXuLyMailCongVan — always writable on any Windows machine."""
    return Path.home() / "Desktop" / "ToolXuLyMailCongVan"


def get_tool_export_folder(date_folder_name: str) -> Path:
    """
    Return (and create) the per-day export folder under ~/.tool_mail_cong_van/.

    Used for mirroring _processed.json and _run.log so they are always
    available locally regardless of the primary output location.

    Example: date_folder_name="26.04.15"
        → ~/.tool_mail_cong_van/26.04.15/
    """
    tool_dir = Path.home() / ".tool_mail_cong_van" / date_folder_name
    tool_dir.mkdir(parents=True, exist_ok=True)
    return tool_dir


def get_daily_folder(
    received_datetime_str: str,
    root_folder: str,
    date_format: str = "%y.%m.%d",
    fallback_folder: str = "",
) -> Tuple[Path, bool]:
    """
    Build and create the daily folder path.

    Tries root_folder first. If that fails with OSError (e.g. network
    unavailable), falls back to fallback_folder (or ~/Desktop/ToolXuLyMailCongVan).

    Returns:
        (daily_path, used_fallback)
        used_fallback=True means the network was down and the fallback was used.

    Raises:
        OSError: only if BOTH primary and fallback paths fail.
    """
    folder_name = get_date_folder_name(received_datetime_str, date_format)

    # ── Try primary path ───────────────────────────────────────────────────
    primary = Path(root_folder) / folder_name
    try:
        primary.mkdir(parents=True, exist_ok=True)
        logger.debug("Daily folder ready (primary): %s", primary)
        return primary, False
    except OSError as primary_err:
        logger.warning(
            "⚠ Network folder không truy cập được: %s\n"
            "  Lỗi: %s\n"
            "  → Chuyển sang thư mục dự phòng trên Desktop.",
            root_folder, primary_err,
        )

    # ── Fallback path ──────────────────────────────────────────────────────
    fb_root = Path(fallback_folder) if fallback_folder else _default_fallback_root()
    fallback = fb_root / folder_name
    try:
        fallback.mkdir(parents=True, exist_ok=True)
        logger.warning("📂 Đang lưu vào thư mục dự phòng: %s", fallback)
        return fallback, True
    except OSError as fb_err:
        logger.error("Cả hai đường dẫn đều không tạo được: %s", fb_err)
        raise


