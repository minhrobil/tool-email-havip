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

@pytest.fixture(autouse=True)
def isolate_tool_folder(tmp_path, monkeypatch):
    """Keep _processed.json inside pytest tmp_path instead of ~/.tool_mail_cong_van."""
    monkeypatch.setattr(
        "src.dedup.manager.get_tool_export_folder",
        lambda _date_folder: tmp_path,
    )


def make_manager(tmp_path: Path) -> DedupManager:
    return DedupManager(tmp_path)


# ── Tests ──────────────────────────────────────────────────────────────────

class TestDedupManagerFreshFolder:
    def test_no_duplicates_on_empty(self, tmp_path):
        mgr = make_manager(tmp_path)
        result = mgr.is_duplicate("msg1", "26.04.14")
        assert result.is_dup is False

    def test_register_and_detect_by_message_id(self, tmp_path):
        mgr = make_manager(tmp_path)
        mgr.register("msg1", "26.04.14", so_don="4-2025-001")
        result = mgr.is_duplicate("msg1", "26.04.14")
        assert result.is_dup is True
        assert "message_id" in result.reason

    def test_internet_message_id_no_longer_a_dedup_key(self, tmp_path):
        mgr = make_manager(tmp_path)
        mgr.register("msg1", "26.04.14", so_don="4-2025-001")
        # New message_id — should NOT be dup (internetMessageId removed as key)
        result = mgr.is_duplicate("msg-different", "26.04.14")
        assert result.is_dup is False

    def test_so_don_no_longer_a_dedup_key(self, tmp_path):
        mgr = make_manager(tmp_path)
        mgr.register("msg1", "26.04.14", so_don="4-2025-001")
        # Same so_don but different message — should NOT be dup (so_don removed as key)
        result = mgr.is_duplicate("msg2", "26.04.14", so_don="4-2025-001")
        assert result.is_dup is False

    def test_register_and_detect_by_filename(self, tmp_path):
        mgr = make_manager(tmp_path)
        mgr.register(
            "msg1", "26.04.14",
            so_don=None,
            attachment_filenames=["thong_bao.pdf"],
        )
        # Create the file so the existence check passes
        (tmp_path / "thong_bao.pdf").write_bytes(b"%PDF")
        result = mgr.is_duplicate(
            "msg2", "26.04.14",
            attachment_filenames=["thong_bao.pdf"],
        )
        assert result.is_dup is True
        assert "filename" in result.reason

    def test_detects_same_filename_with_different_index_prefixes(self, tmp_path):
        """Download indexes must not hide a duplicate business filename."""
        mgr = make_manager(tmp_path)
        stored = tmp_path / "1-thong_bao.pdf"
        stored.write_bytes(b"%PDF")
        mgr.register(
            "msg1", "26.04.14",
            attachment_filenames=[stored.name],
        )

        result = mgr.is_duplicate(
            "msg2", "26.04.14",
            attachment_filenames=["2-thong_bao.pdf"],
        )

        assert result.is_dup is True
        assert "filename" in result.reason
        assert result.matched_message_id == "msg1"
        assert result.matched_excel_seq is None

    def test_duplicate_reports_original_excel_sequence(self, tmp_path):
        mgr = make_manager(tmp_path)
        stored = tmp_path / "1-thong_bao.pdf"
        stored.write_bytes(b"%PDF")
        mgr.register(
            "msg1", "26.04.14",
            attachment_filenames=[stored.name],
            excel_seq=1,
        )

        result = mgr.is_duplicate(
            "msg2", "26.04.14",
            attachment_filenames=["2-thong_bao.pdf"],
        )

        assert result.matched_excel_seq == 1

    def test_rerun_matches_own_message_before_shared_portal_url(self, tmp_path):
        mgr = make_manager(tmp_path)
        portal_url = "https://example.test/shared"
        for seq, message_id in enumerate(("msg1", "msg2"), start=1):
            filename = f"{seq}-same.pdf"
            (tmp_path / filename).write_bytes(b"%PDF")
            mgr.register(
                message_id,
                "26.04.14",
                attachment_filenames=[filename],
                download_url=portal_url,
                excel_seq=seq,
            )

        result = mgr.is_duplicate(
            "msg1",
            "26.04.14",
            attachment_filenames=["1-same.pdf"],
            portal_url=portal_url,
        )

        assert result.matched_message_id == "msg1"
        assert result.matched_excel_seq == 1

    def test_multiple_duplicates_keep_referring_to_first_excel_row(self, tmp_path):
        mgr = make_manager(tmp_path)
        for seq, message_id in enumerate(("msg1", "msg2"), start=1):
            filename = f"{seq}-same.pdf"
            (tmp_path / filename).write_bytes(b"%PDF")
            mgr.register(
                message_id,
                "26.04.14",
                attachment_filenames=[filename],
                excel_seq=seq,
            )

        result = mgr.is_duplicate(
            "msg3",
            "26.04.14",
            attachment_filenames=["3-same.pdf"],
        )

        assert result.matched_message_id == "msg1"
        assert result.matched_excel_seq == 1

    def test_file_deleted_triggers_redownload(self, tmp_path):
        """If a previously downloaded file is deleted, needs_redownload=True is signalled."""
        mgr = make_manager(tmp_path)
        pdf = tmp_path / "thong_bao.pdf"
        pdf.write_bytes(b"%PDF")
        mgr.register(
            "msg1", "26.04.14",
            attachment_filenames=["thong_bao.pdf"],
        )
        # Confirm it's a normal dup while the file exists
        result = mgr.is_duplicate("msg1", "26.04.14")
        assert result.is_dup is True
        assert result.needs_redownload is False

        # Delete the file — should signal needs_redownload (dup but file missing)
        pdf.unlink()
        mgr2 = make_manager(tmp_path)
        result_after = mgr2.is_duplicate("msg1", "26.04.14")
        assert result_after.is_dup is True
        assert result_after.needs_redownload is True

    def test_different_folder_not_duplicate(self, tmp_path):
        """Dedup is scoped per folder; same email in a different day is NOT a dup."""
        mgr = make_manager(tmp_path)
        mgr.register("msg1", "26.04.14", so_don="4-2025-001")
        # Different date folder
        mgr2 = make_manager(tmp_path)  # reload from disk
        mgr2.is_duplicate("msg1", "26.04.15", so_don="4-2025-001")
        # same manager but different date_folder in the business key
        result_bk = mgr.is_duplicate("msg9", "26.04.15", so_don="4-2025-001")
        assert result_bk.is_dup is False  # different folder → not dup in business key

    def test_persistence_across_instances(self, tmp_path):
        """Records must survive creating a new DedupManager from the same folder."""
        mgr1 = make_manager(tmp_path)
        mgr1.register("msg1", "26.04.14", so_don="4-2025-001")

        mgr2 = make_manager(tmp_path)  # reload from disk
        result = mgr2.is_duplicate("msg1", "26.04.14")
        assert result.is_dup is True

    def test_json_file_written(self, tmp_path):
        mgr = make_manager(tmp_path)
        mgr.register("msg1", "26.04.14", so_don="4-2025-001")
        proc_file = tmp_path / "_processed.json"
        assert proc_file.exists()
        data = json.loads(proc_file.read_text(encoding="utf-8"))
        assert len(data["records"]) == 1
        assert data["records"][0]["message_id"] == "msg1"

    def test_multiple_registrations(self, tmp_path):
        mgr = make_manager(tmp_path)
        for i in range(5):
            mgr.register(f"msg{i}", "26.04.14", so_don=f"4-2025-00{i}")
        assert mgr.count() == 5

    def test_idempotent_register(self, tmp_path):
        """Registering the same message twice should not increase count."""
        mgr = make_manager(tmp_path)
        mgr.register("msg1", "26.04.14", so_don="4-2025-001")
        mgr.register("msg1", "26.04.14", so_don="4-2025-001")
        assert mgr.count() == 1  # dict keyed by message_id deduplicates

    def test_corrupted_json_does_not_crash(self, tmp_path):
        proc_file = tmp_path / "_processed.json"
        proc_file.write_text("{invalid json!!!", encoding="utf-8")
        # Should not raise; should start with empty state
        mgr = make_manager(tmp_path)
        assert mgr.count() == 0

    def test_clear_removes_all_records_for_fresh_run(self, tmp_path):
        mgr = make_manager(tmp_path)
        mgr.register("msg1", "26.04.14", excel_seq=1)

        mgr.clear()

        assert mgr.count() == 0
        assert not (tmp_path / "_processed.json").exists()
        reloaded = make_manager(tmp_path)
        assert reloaded.is_duplicate("msg1", "26.04.14").is_dup is False
