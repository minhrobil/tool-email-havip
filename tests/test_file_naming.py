"""
Unit tests for file-renaming helpers in email_processor.py
Run with:  python -m pytest tests/test_file_naming.py -v
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from pathlib import Path
from types import SimpleNamespace

from src.processor.email_processor import (
    EmailProcessor,
    _assign_fresh_sequences,
    _make_seq_filename,
    _rename_downloaded_files,
    _with_mail_position,
)
from src.portal.browser_downloader import _indexed_filename


class TestMakeSeqFilename:
    def test_basic(self):
        assert _make_seq_filename(1, "thongbao", ".pdf") == "1-thongbao.pdf"

    def test_seq_3(self):
        assert _make_seq_filename(3, "van_ban", ".pdf") == "3-van_ban.pdf"

    def test_non_pdf_extension(self):
        assert _make_seq_filename(5, "image", ".png") == "5-image.png"

    def test_portal_download_name_uses_email_index(self):
        assert _indexed_filename("thong_bao.pdf", 7) == "7-thong_bao.pdf"

    def test_sub_log_includes_mail_position(self):
        assert _with_mail_position("  ↳ Link portal: https://example", 5, 22) == (
            "  ↳ [5/22] Link portal: https://example"
        )

    def test_rerun_reuses_same_email_indexes(self):
        assigned = _assign_fresh_sequences(["mail-1", "mail-2", "mail-3"])

        assert assigned == {"mail-1": 1, "mail-2": 2, "mail-3": 3}

    def test_new_email_gets_one_new_index_even_if_file_will_duplicate(self):
        assigned = _assign_fresh_sequences(["mail-1", "mail-new"])

        assert assigned == {"mail-1": 1, "mail-new": 2}

    def test_scan_index_follows_global_email_position_across_date_folders(self):
        processor = EmailProcessor.__new__(EmailProcessor)
        messages = [
            SimpleNamespace(id="mail-1", received_datetime="2026-07-16T12:00:00Z"),
            SimpleNamespace(id="mail-2", received_datetime="2026-07-17T12:00:00Z"),
            SimpleNamespace(id="mail-3", received_datetime="2026-07-17T12:10:00Z"),
        ]

        assigned = processor._pre_assign_seq(messages)

        assert assigned == {"mail-1": 1, "mail-2": 2, "mail-3": 3}

    def test_seq_10(self):
        assert _make_seq_filename(10, "document", ".xlsx") == "10-document.xlsx"


class TestRenameDownloadedFiles:
    def test_renames_file(self, tmp_path):
        f = tmp_path / "original.pdf"
        f.write_bytes(b"content")

        _, new_names = _rename_downloaded_files([f], seq=1)

        assert new_names == ["1-original.pdf"]
        assert (tmp_path / "1-original.pdf").exists()
        assert not f.exists()

    def test_renames_multiple_files(self, tmp_path):
        f1 = tmp_path / "doc1.pdf"
        f2 = tmp_path / "doc2.xlsx"
        f1.write_bytes(b"a")
        f2.write_bytes(b"b")

        _, new_names = _rename_downloaded_files([f1, f2], seq=3)

        assert "3-doc1.pdf" in new_names
        assert "3-doc2.xlsx" in new_names

    def test_seq_overwrites_existing(self, tmp_path):
        # If 3-file.pdf already exists it must be removed and replaced (overwrite, no _1 suffix)
        existing = tmp_path / "3-file.pdf"
        existing.write_bytes(b"old")
        f = tmp_path / "file.pdf"
        f.write_bytes(b"new")

        _, new_names = _rename_downloaded_files([f], seq=3)

        assert new_names == ["3-file.pdf"]
        assert (tmp_path / "3-file.pdf").read_bytes() == b"new"

    def test_skips_missing_file(self, tmp_path):
        ghost = tmp_path / "ghost.pdf"  # does not exist

        new_paths, _ = _rename_downloaded_files([ghost], seq=1)

        # Should return the original path unchanged (no crash)
        assert new_paths == [ghost]

