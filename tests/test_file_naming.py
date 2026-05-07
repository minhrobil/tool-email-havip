"""
Unit tests for file-renaming helpers in email_processor.py
Run with:  python -m pytest tests/test_file_naming.py -v
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from pathlib import Path

from src.processor.email_processor import _make_seq_filename, _rename_downloaded_files


class TestMakeSeqFilename:
    def test_basic(self):
        assert _make_seq_filename(1, "thongbao", ".pdf") == "1-thongbao.pdf"

    def test_seq_3(self):
        assert _make_seq_filename(3, "van_ban", ".pdf") == "3-van_ban.pdf"

    def test_non_pdf_extension(self):
        assert _make_seq_filename(5, "image", ".png") == "5-image.png"

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

