"""
Unit tests for src/parser/rules.py

Run with:  python -m pytest tests/test_parser.py -v
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from datetime import date
import pytest

from src.parser.rules import (
    normalize_text,
    extract_so_cong_van,
    extract_issue_date,
    extract_so_don,
    extract_so_yeu_cau,
    extract_so_gcn,
    extract_deadline_months,
    calculate_deadline_date,
    classify_document,
    detect_loai_hinh_don,
    extract_noi_dung,
    parse_document,
)


# ── normalize_text ─────────────────────────────────────────────────────────

class TestNormalizeText:
    def test_collapses_spaces(self):
        assert normalize_text("hello   world") == "hello world"

    def test_strips(self):
        assert normalize_text("  abc  ") == "abc"

    def test_unifies_crlf(self):
        assert normalize_text("a\r\nb") == "a\nb"

    def test_nfc_normalization(self):
        # NFC and NFD representations of "ộ" should both normalize to same string
        import unicodedata
        nfd = unicodedata.normalize("NFD", "ộ")
        nfc = unicodedata.normalize("NFC", "ộ")
        assert normalize_text(nfd) == normalize_text(nfc)


# ── extract_so_cong_van ────────────────────────────────────────────────────

class TestSoCongVan:
    def test_basic(self):
        text = "Số: 53397/SHTT-NH.IP"
        assert extract_so_cong_van(text) == "53397/SHTT-NH.IP"

    def test_with_spaces_around_colon(self):
        text = "Số :  12345/SHTT-AB"
        assert extract_so_cong_van(text) == "12345/SHTT-AB"

    def test_not_found(self):
        assert extract_so_cong_van("Không có số công văn ở đây") is None

    def test_in_longer_text(self):
        text = "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM\nSố: 99001/SHTT-NH\nHà Nội, ngày 01 tháng 01 năm 2026"
        assert extract_so_cong_van(text) == "99001/SHTT-NH"


# ── extract_issue_date ─────────────────────────────────────────────────────

class TestIssueDate:
    def test_basic(self):
        text = "Hà Nội, ngày 13 tháng 04 năm 2026"
        assert extract_issue_date(text) == date(2026, 4, 13)

    def test_lowercase_variant(self):
        text = "hà nội, ngày 01 tháng 01 năm 2025"
        assert extract_issue_date(text) == date(2025, 1, 1)

    def test_not_found(self):
        assert extract_issue_date("Không có ngày") is None

    def test_end_of_month(self):
        text = "ngày 31 tháng 12 năm 2025"
        assert extract_issue_date(text) == date(2025, 12, 31)

    def test_invalid_date_returns_none(self):
        # February 30 is invalid
        text = "ngày 30 tháng 02 năm 2026"
        assert extract_issue_date(text) is None


# ── extract_so_don ─────────────────────────────────────────────────────────

class TestSoDon:
    def test_basic(self):
        text = "Số đơn: 4-2025-20619"
        assert extract_so_don(text) == "4-2025-20619"

    def test_another_pattern(self):
        text = "Số đơn: 4-2025-22677"
        assert extract_so_don(text) == "4-2025-22677"

    def test_no_colon_separator(self):
        # Inline reference without colon: "(số đơn 4-2015-33594)"
        text = "có ngày nộp đơn là ngày 30/11/2015 (số đơn 4-2015-33594)"
        assert extract_so_don(text) == "4-2015-33594"

    def test_dn_format_not_matched(self):
        # ĐN prefix (cancellation request) must NOT match — digits-only pattern
        text = "Số đơn: ĐN1-2017-00311"
        assert extract_so_don(text) is None

    def test_dn_skipped_prefers_standard_format(self):
        # Document has both ĐN and standard format; should return standard format
        text = "Số đơn: ĐN1-2017-00311\nngày nộp đơn là ngày 30/11/2015 (số đơn 4-2015-33594)"
        assert extract_so_don(text) == "4-2015-33594"

    def test_not_found(self):
        assert extract_so_don("Không có số đơn") is None


# ── extract_so_yeu_cau ─────────────────────────────────────────────────────

class TestSoYeuCau:
    def test_basic(self):
        text = "Số yêu cầu: CĐ4-2026-00098"
        assert extract_so_yeu_cau(text) == "CĐ4-2026-00098"

    def test_not_found(self):
        assert extract_so_yeu_cau("Không có số yêu cầu") is None


# ── extract_deadline_months ────────────────────────────────────────────────

class TestDeadlineMonths:
    def test_02_months(self):
        text = "Trong thời hạn 02 tháng kể từ ngày ra thông báo này"
        assert extract_deadline_months(text) == 2

    def test_03_months(self):
        text = "Trong thời hạn 03 tháng kể từ ngày ký công văn này"
        assert extract_deadline_months(text) == 3

    def test_single_digit(self):
        text = "Trong thời hạn 1 tháng"
        assert extract_deadline_months(text) == 1

    def test_90_days_converts_to_3_months(self):
        text = "trong thời hạn 90 ngày kể từ ngày nhận được hoặc biết được Thông báo này"
        assert extract_deadline_months(text) == 3

    def test_60_days_converts_to_2_months(self):
        text = "Trong thời hạn 60 ngày kể từ ngày"
        assert extract_deadline_months(text) == 2

    def test_30_days_converts_to_1_month(self):
        text = "Trong thời hạn 30 ngày kể từ ngày"
        assert extract_deadline_months(text) == 1

    def test_months_takes_priority_over_days(self):
        # If both patterns appear, months wins
        text = "Trong thời hạn 02 tháng kể từ ngày ký. Trong thời hạn 90 ngày khiếu nại."
        assert extract_deadline_months(text) == 2

    def test_not_found(self):
        assert extract_deadline_months("Không có thời hạn") is None


# ── calculate_deadline_date ────────────────────────────────────────────────

class TestCalculateDeadline:
    def test_two_months(self):
        result = calculate_deadline_date(date(2026, 4, 13), 2)
        assert result == date(2026, 6, 13)

    def test_three_months(self):
        result = calculate_deadline_date(date(2026, 1, 31), 3)
        # dateutil: Jan 31 + 3 months = Apr 30 (month-end clamping)
        assert result == date(2026, 4, 30)

    def test_none_issue_date(self):
        assert calculate_deadline_date(None, 2) is None

    def test_none_months(self):
        assert calculate_deadline_date(date(2026, 4, 13), None) is None

    def test_both_none(self):
        assert calculate_deadline_date(None, None) is None


# ── classify_document ─────────────────────────────────────────────────────

class TestClassifyDocument:
    def test_du_dinh_tu_choi(self):
        text = "Thông báo dự định từ chối đơn đăng ký nhãn hiệu"
        assert classify_document(text) == "Dự định từ chối"

    def test_tu_choi_huy_bo_hlc(self):
        # Must be classified BEFORE "Cấp toàn bộ" even though body contains
        # "đáp ứng các điều kiện bảo hộ"
        text = (
            "Từ chối yêu cầu hủy bỏ hiệu lực GCNĐKNH số 286000 vì việc cấp "
            "GCNĐKNH là đáp ứng các điều kiện bảo hộ theo quy định pháp luật."
        )
        assert classify_document(text) == "Từ chối hủy bỏ HLC"

    def test_tu_choi_toan_bo(self):
        text = "Cục từ chối cấp văn bằng bảo hộ đối với toàn bộ các sản phẩm"
        assert classify_document(text) == "Từ chối toàn bộ"

    def test_cap_toan_bo(self):
        text = "Đơn đăng ký đáp ứng các điều kiện bảo hộ, đề nghị nộp lệ phí"
        assert classify_document(text) == "Cấp toàn bộ"

    def test_kqtd_noi_dung(self):
        text = "Thông báo kết quả thẩm định nội dung đơn đăng ký nhãn hiệu"
        assert classify_document(text) == "KQTĐ nội dung"

    def test_unclassified(self):
        text = "Đây là nội dung không rõ ràng"
        assert classify_document(text) is None


# ── detect_loai_hinh_don ──────────────────────────────────────────────────

class TestLoaiHinhDon:
    def test_nhan_hieu(self):
        assert detect_loai_hinh_don("đơn đăng ký nhãn hiệu quốc gia") == "Nhãn hiệu"

    def test_sang_che(self):
        assert detect_loai_hinh_don("đơn yêu cầu cấp bằng sáng chế") == "Sáng chế"

    def test_kieu_dang(self):
        assert detect_loai_hinh_don("kiểu dáng công nghiệp cho sản phẩm") == "Kiểu dáng công nghiệp"

    def test_not_found(self):
        assert detect_loai_hinh_don("nội dung không rõ loại hình") is None


# ── extract_noi_dung ──────────────────────────────────────────────────────

class TestNoiDung:
    def test_returns_first_long_line(self):
        text = "Số: 001/SHTT\nHà Nội, ngày 01\nCục Sở hữu trí tuệ thông báo kết quả thẩm định đơn đăng ký nhãn hiệu số 4-2025-20619 như sau:"
        result = extract_noi_dung(text)
        assert result is not None
        assert "Cục Sở hữu" in result

    def test_max_300_chars(self):
        long_line = "A" * 400
        text = f"Header line\n{long_line}"
        result = extract_noi_dung(text)
        assert result is not None
        assert len(result) == 300

    def test_ve_viec_takes_priority_over_long_line(self):
        # "Về việc" subject appears before a longer line — must be chosen
        text = (
            "Hà Nội, ngày 06 tháng 03 năm 2026\n"
            "THÔNG BÁO\n"
            "Về việc từ chối hủy bỏ hiệu lực\n"
            "Cục Sở hữu trí tuệ thông báo kết quả thẩm định đơn đăng ký nhãn hiệu số như sau:"
        )
        result = extract_noi_dung(text)
        assert result is not None
        assert result.startswith("Về việc")

    def test_ve_viec_short_line_still_returned(self):
        # "Về việc" line is shorter than 40 chars — still returned
        text = "Số: 001/SHTT\nVề việc từ chối"
        result = extract_noi_dung(text)
        assert result is not None
        assert result.startswith("Về việc")


# ── parse_document integration ────────────────────────────────────────────

class TestParseDocument:
    SAMPLE_TEXT = """
    CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
    Số: 53397/SHTT-NH.IP
    Hà Nội, ngày 13 tháng 04 năm 2026

    Kính gửi: Công ty TNHH ABC

    Căn cứ đơn đăng ký nhãn hiệu
    Số đơn: 4-2025-20619
    Số yêu cầu: CĐ4-2026-00098

    Cục Sở hữu trí tuệ thông báo dự định từ chối đăng ký nhãn hiệu quốc gia.

    Trong thời hạn 03 tháng kể từ ngày ra thông báo này, quý khách cần nộp ý kiến phản đối.
    """

    def test_full_parse(self):
        result = parse_document(text=self.SAMPLE_TEXT)
        assert result.so_cong_van == "53397/SHTT-NH.IP"
        assert result.so_cong_van_num == "53397"
        assert result.issue_date == date(2026, 4, 13)
        assert result.so_don == "4-2025-20619"
        assert result.so_yeu_cau == "CĐ4-2026-00098"
        assert result.deadline_months == 3
        assert result.deadline_date == date(2026, 7, 13)
        assert result.loai_cong_van == "Dự định từ chối"
        assert result.loai_hinh_don == "Nhãn hiệu"

    def test_empty_text(self):
        result = parse_document(text="")
        assert result.so_cong_van is None
        assert result.so_don is None
        assert result.deadline_months is None


# ── extract_so_gcn ────────────────────────────────────────────────────────

class TestSoGcn:
    def test_from_full_certificate_field(self):
        text = "Số Giấy chứng nhận đăng ký nhãn hiệu bị yêu cầu hủy bỏ hiệu lực: 286000"
        assert extract_so_gcn(text) == "286000"

    def test_from_full_field_no_optional_part(self):
        text = "Số Giấy chứng nhận đăng ký nhãn hiệu: 123456"
        assert extract_so_gcn(text) == "123456"

    def test_from_gcndknh_abbrev(self):
        text = "hủy bỏ hiệu lực GCNĐKNH số 286000 cấp ngày 09/08/2017"
        assert extract_so_gcn(text) == "286000"

    def test_not_found(self):
        assert extract_so_gcn("Không có giấy chứng nhận") is None


# ── so_cong_van_num ───────────────────────────────────────────────────────

class TestSoCongVanNum:
    def test_numeric_prefix_extracted(self):
        result = parse_document(text="Số: 30369/TB-SHTT.IP\nHà Nội, ngày 06 tháng 03 năm 2026")
        assert result.so_cong_van == "30369/TB-SHTT.IP"
        assert result.so_cong_van_num == "30369"

    def test_none_when_no_so_cong_van(self):
        result = parse_document(text="Không có số công văn")
        assert result.so_cong_van is None
        assert result.so_cong_van_num is None


# ── Integration: Từ chối hủy bỏ hiệu lực (sample document) ───────────────

class TestSampleTuChoiHuyBoDocument:
    """
    Integration test using text from the actual sample document:
    '30369/TB-SHTT.IP — Thông báo từ chối hủy bỏ hiệu lực GCNĐKNH 286000'
    """
    SAMPLE_TEXT = """
BỘ KHOA HỌC VÀ CÔNG NGHỆ
CỤC SỞ HỮU TRÍ TUỆ
Số: 30369/TB-SHTT.IP
CỘNG HOÀ XÃ HỘI CHỦ NGHĨA VIỆT NAM
Độc lập - Tự do - Hạnh phúc
Hà Nội, ngày 06 tháng 03 năm 2026
THÔNG BÁO
Về việc từ chối hủy bỏ hiệu lực
Giấy chứng nhận đăng ký nhãn hiệu
Số đơn: ĐN1-2017-00311 Ngày nộp: 22/12/2017
Số Giấy chứng nhận đăng ký nhãn hiệu bị yêu cầu hủy bỏ hiệu lực: 286000
Ngày cấp: 09/08/2017
có ngày nộp đơn là ngày 30/11/2015 (số đơn 4-2015-33594) đã trùng với tên thương mại
việc cấp GCNĐKNH số 286000 là đáp ứng các điều kiện bảo hộ theo quy định pháp luật.
1. Từ chối yêu cầu hủy bỏ hiệu lực GCNĐKNH số 286000 của Hộ kinh doanh cá thể Thanh Bình (VN).
2. Người nộp đơn có quyền khiếu nại theo quy định trong thời hạn 90 ngày
kể từ ngày nhận được hoặc biết được Thông báo này.
"""

    def test_so_cong_van(self):
        result = parse_document(text=self.SAMPLE_TEXT)
        assert result.so_cong_van == "30369/TB-SHTT.IP"

    def test_so_cong_van_num(self):
        result = parse_document(text=self.SAMPLE_TEXT)
        assert result.so_cong_van_num == "30369"

    def test_issue_date(self):
        result = parse_document(text=self.SAMPLE_TEXT)
        assert result.issue_date == date(2026, 3, 6)

    def test_so_don_skips_dn_format_returns_standard(self):
        # ĐN1-2017-00311 must be skipped; 4-2015-33594 should be returned
        result = parse_document(text=self.SAMPLE_TEXT)
        assert result.so_don == "4-2015-33594"

    def test_so_gcn(self):
        result = parse_document(text=self.SAMPLE_TEXT)
        assert result.so_gcn == "286000"

    def test_deadline_90_days_converts_to_3_months(self):
        result = parse_document(text=self.SAMPLE_TEXT)
        assert result.deadline_months == 3

    def test_deadline_date(self):
        # 06/03/2026 + 3 months = 06/06/2026
        result = parse_document(text=self.SAMPLE_TEXT)
        assert result.deadline_date == date(2026, 6, 6)

    def test_loai_cong_van(self):
        result = parse_document(text=self.SAMPLE_TEXT)
        assert result.loai_cong_van == "Từ chối hủy bỏ HLC"

    def test_loai_hinh_don(self):
        result = parse_document(text=self.SAMPLE_TEXT)
        assert result.loai_hinh_don == "Nhãn hiệu"

    def test_noi_dung_starts_with_ve_viec(self):
        result = parse_document(text=self.SAMPLE_TEXT)
        assert result.noi_dung_cong_van is not None
        assert result.noi_dung_cong_van.startswith("Về việc")


