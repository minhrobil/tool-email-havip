"""
Unit tests for src/folder/routing.py

Run with:  python -m pytest tests/test_folder_routing.py -v
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import datetime, timezone

import pytest

from src.folder.routing import (
    parse_received_datetime,
    get_date_folder_name,
    get_daily_folder,
)


# ── parse_received_datetime ────────────────────────────────────────────────

class TestParseReceivedDatetime:
    def test_basic_utc_z(self):
        dt = parse_received_datetime("2026-04-14T08:30:00Z")
        assert dt.year == 2026
        assert dt.month == 4
        assert dt.day == 14
        assert dt.hour == 8
        assert dt.tzinfo == timezone.utc

    def test_fractional_seconds(self):
        dt = parse_received_datetime("2026-04-14T08:30:00.0000000Z")
        assert dt.day == 14
        assert dt.tzinfo == timezone.utc

    def test_without_z_suffix(self):
        dt = parse_received_datetime("2026-04-14T23:59:59")
        assert dt.day == 14

    def test_returns_utc_aware(self):
        dt = parse_received_datetime("2026-04-14T00:00:00Z")
        assert dt.tzinfo is not None


# ── get_date_folder_name ───────────────────────────────────────────────────

class TestGetDateFolderName:
    def test_format_yy_mm_dd(self):
        # 2026-04-14 UTC midnight — local date depends on timezone, but format is stable
        name = get_date_folder_name("2026-04-14T00:30:00Z", "%y.%m.%d")
        # The result should be either 26.04.14 or 26.04.13 depending on UTC offset,
        # but the FORMAT should always be correct.
        parts = name.split(".")
        assert len(parts) == 3
        assert len(parts[0]) == 2   # yy
        assert len(parts[1]) == 2   # mm
        assert len(parts[2]) == 2   # dd

    def test_folder_name_from_email_not_today(self):
        """
        CRITICAL: The folder name must come from the email date, NOT from today.
        A 2025 email must produce a 2025 folder name even when run in 2026.
        """
        name = get_date_folder_name("2025-01-05T12:00:00Z", "%y.%m.%d")
        # Year part must be 25 regardless of when the test runs
        assert name.startswith("25.")

    def test_custom_format(self):
        name = get_date_folder_name("2026-04-14T12:00:00Z", "%Y-%m-%d")
        assert name.startswith("2026-04-")


# ── get_daily_folder ───────────────────────────────────────────────────────

class TestGetDailyFolder:
    def test_creates_folder(self, tmp_path):
        folder, used_fallback = get_daily_folder("2026-04-14T12:00:00Z", str(tmp_path), "%y.%m.%d")
        assert used_fallback is False
        assert folder.exists()
        assert folder.is_dir()

    def test_folder_name_matches(self, tmp_path):
        folder, used_fallback = get_daily_folder("2025-01-05T12:00:00Z", str(tmp_path), "%y.%m.%d")
        assert used_fallback is False
        assert folder.parent == tmp_path
        assert folder.name.startswith("25.")

    def test_idempotent(self, tmp_path):
        """Calling twice with same args should not raise."""
        get_daily_folder("2026-04-14T12:00:00Z", str(tmp_path), "%y.%m.%d")
        get_daily_folder("2026-04-14T12:00:00Z", str(tmp_path), "%y.%m.%d")

    def test_invalid_root_raises(self, tmp_path):
        bad_root = tmp_path / "root_file"
        bad_root.write_text("not a directory", encoding="utf-8")
        bad_fallback = tmp_path / "fallback_file"
        bad_fallback.write_text("not a directory", encoding="utf-8")

        with pytest.raises(OSError):
            get_daily_folder(
                "2026-04-14T12:00:00Z",
                str(bad_root),
                "%y.%m.%d",
                str(bad_fallback),
            )
