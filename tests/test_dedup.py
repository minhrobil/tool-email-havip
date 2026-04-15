"""
Unit tests for src/dedup/manager.py

Run with:  python -m pytest tests/test_dedup.py -v
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import tempfile
from pathlib import Path

import pytest

from src.dedup.manager import DedupManager


# ── Helpers ────────────────────────────────────────────────────────────────

def make_manager(tmp_path: Path) -> DedupManager:
    return DedupManager(tmp_path)


# ── Tests ──────────────────────────────────────────────────────────────────

class TestDedupManagerFreshFolder:
    def test_no_duplicates_on_empty(self, tmp_path):
        mgr = make_manager(tmp_path)
        is_dup, _ = mgr.is_duplicate("msg1", "imid1", "26.04.14")
        assert is_dup is False

    def test_register_and_detect_by_message_id(self, tmp_path):
        mgr = make_manager(tmp_path)
        mgr.register("msg1", "imid1", "26.04.14", so_don="4-2025-001")
        is_dup, reason = mgr.is_duplicate("msg1", None, "26.04.14")
        assert is_dup is True
        assert "message_id" in reason

    def test_register_and_detect_by_internet_message_id(self, tmp_path):
        mgr = make_manager(tmp_path)
        mgr.register("msg1", "imid1", "26.04.14", so_don="4-2025-001")
        # New message_id, same internet_message_id
        is_dup, reason = mgr.is_duplicate("msg-different", "imid1", "26.04.14")
        assert is_dup is True
        assert "internetMessageId" in reason

    def test_register_and_detect_by_so_don(self, tmp_path):
        mgr = make_manager(tmp_path)
        mgr.register("msg1", None, "26.04.14", so_don="4-2025-001")
        # Different technical keys, same so_don
        is_dup, reason = mgr.is_duplicate("msg2", "imid2", "26.04.14", so_don="4-2025-001")
        assert is_dup is True
        assert "so_don" in reason

    def test_register_and_detect_by_filename(self, tmp_path):
        mgr = make_manager(tmp_path)
        mgr.register(
            "msg1", None, "26.04.14",
            so_don=None,
            attachment_filenames=["thong_bao.pdf"],
        )
        is_dup, reason = mgr.is_duplicate(
            "msg2", "imid2", "26.04.14",
            attachment_filenames=["thong_bao.pdf"],
        )
        assert is_dup is True
        assert "filename" in reason

    def test_different_folder_not_duplicate(self, tmp_path):
        """Dedup is scoped per folder; same email in a different day is NOT a dup."""
        mgr = make_manager(tmp_path)
        mgr.register("msg1", "imid1", "26.04.14", so_don="4-2025-001")
        # Different date folder
        mgr2 = make_manager(tmp_path)  # reload from disk
        _, _ = mgr2.is_duplicate("msg1", "imid1", "26.04.15", so_don="4-2025-001")
        # same manager but different date_folder in the business key
        is_dup_bk, _ = mgr.is_duplicate("msg9", "imid9", "26.04.15", so_don="4-2025-001")
        assert is_dup_bk is False  # different folder → not dup in business key

    def test_persistence_across_instances(self, tmp_path):
        """Records must survive creating a new DedupManager from the same folder."""
        mgr1 = make_manager(tmp_path)
        mgr1.register("msg1", "imid1", "26.04.14", so_don="4-2025-001")

        mgr2 = make_manager(tmp_path)  # reload from disk
        is_dup, _ = mgr2.is_duplicate("msg1", "imid1", "26.04.14")
        assert is_dup is True

    def test_json_file_written(self, tmp_path):
        mgr = make_manager(tmp_path)
        mgr.register("msg1", "imid1", "26.04.14", so_don="4-2025-001")
        proc_file = tmp_path / "_processed.json"
        assert proc_file.exists()
        data = json.loads(proc_file.read_text(encoding="utf-8"))
        assert len(data["records"]) == 1
        assert data["records"][0]["message_id"] == "msg1"

    def test_multiple_registrations(self, tmp_path):
        mgr = make_manager(tmp_path)
        for i in range(5):
            mgr.register(f"msg{i}", f"imid{i}", "26.04.14", so_don=f"4-2025-00{i}")
        assert mgr.count() == 5

    def test_idempotent_register(self, tmp_path):
        """Registering the same message twice should not increase count."""
        mgr = make_manager(tmp_path)
        mgr.register("msg1", "imid1", "26.04.14", so_don="4-2025-001")
        mgr.register("msg1", "imid1", "26.04.14", so_don="4-2025-001")
        assert mgr.count() == 1  # dict keyed by message_id deduplicates

    def test_corrupted_json_does_not_crash(self, tmp_path):
        proc_file = tmp_path / "_processed.json"
        proc_file.write_text("{invalid json!!!", encoding="utf-8")
        # Should not raise; should start with empty state
        mgr = make_manager(tmp_path)
        assert mgr.count() == 0

