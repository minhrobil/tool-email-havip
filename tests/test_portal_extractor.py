"""
Unit tests for src/portal/url_extractor.py

Run with:  python -m pytest tests/test_portal_extractor.py -v
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from src.portal.url_extractor import extract_portal_urls, extract_first_portal_url

PATTERNS = ["ipvietnam.gov.vn", "dichvucong.ipvietnam"]


class TestExtractPortalUrls:

    def test_basic_href_in_html(self):
        html = '<p>Xem hồ sơ: <a href="https://dichvucong.ipvietnam.gov.vn/tra-cuu?so=53397">tại đây</a></p>'
        urls = extract_portal_urls(html, "", PATTERNS)
        assert len(urls) == 1
        assert "53397" in urls[0]

    def test_multiple_hrefs_deduped(self):
        html = (
            '<a href="https://ipvietnam.gov.vn/page?id=1">link1</a>'
            '<a href="https://ipvietnam.gov.vn/page?id=1">link1 again</a>'
            '<a href="https://ipvietnam.gov.vn/page?id=2">link2</a>'
        )
        urls = extract_portal_urls(html, "", PATTERNS)
        assert len(urls) == 2

    def test_url_in_plain_text(self):
        text = "Truy cập: https://ipvietnam.gov.vn/tra-cuu?so=ABC để tra cứu."
        urls = extract_portal_urls("", text, PATTERNS)
        assert len(urls) == 1
        assert "ipvietnam.gov.vn" in urls[0]

    def test_non_portal_url_excluded(self):
        html = '<a href="https://google.com">Google</a><a href="https://ipvietnam.gov.vn/x">IP</a>'
        urls = extract_portal_urls(html, "", PATTERNS)
        assert len(urls) == 1
        assert "ipvietnam" in urls[0]

    def test_html_entities_unescaped(self):
        html = '<a href="https://ipvietnam.gov.vn/tra-cuu?a=1&amp;b=2">link</a>'
        urls = extract_portal_urls(html, "", PATTERNS)
        assert len(urls) == 1
        assert "&" in urls[0]     # &amp; should be decoded to &

    def test_empty_bodies_returns_empty(self):
        assert extract_portal_urls("", "", PATTERNS) == []

    def test_no_matching_pattern_returns_empty(self):
        html = '<a href="https://example.com/doc">link</a>'
        assert extract_portal_urls(html, "", PATTERNS) == []

    def test_url_in_onclick_attr(self):
        html = '<button onclick="window.open(\'https://ipvietnam.gov.vn/x\')">Open</button>'
        urls = extract_portal_urls(html, "", PATTERNS)
        assert len(urls) >= 1

    def test_trailing_punctuation_stripped(self):
        text = "Link: https://ipvietnam.gov.vn/doc?id=99."
        urls = extract_portal_urls("", text, PATTERNS)
        assert len(urls) == 1
        assert not urls[0].endswith(".")

    def test_both_html_and_text_combined(self):
        html = '<a href="https://ipvietnam.gov.vn/a">link</a>'
        text = "Alternate: https://ipvietnam.gov.vn/b"
        urls = extract_portal_urls(html, text, PATTERNS)
        # Should have at least one from HTML href
        assert any("ipvietnam.gov.vn/a" in u for u in urls)


class TestExtractFirstPortalUrl:

    def test_returns_first(self):
        html = (
            '<a href="https://ipvietnam.gov.vn/first">first</a>'
            '<a href="https://ipvietnam.gov.vn/second">second</a>'
        )
        url = extract_first_portal_url(html, "", PATTERNS)
        assert url is not None
        assert "first" in url

    def test_returns_none_when_no_match(self):
        assert extract_first_portal_url("", "no links here", PATTERNS) is None

    def test_real_world_html_fragment(self):
        """Simulate a realistic IP Vietnam notification email."""
        html = """
        <html><body>
        <p>Kính gửi Quý khách,</p>
        <p>Cục Sở hữu trí tuệ thông báo kết quả thẩm định đơn đăng ký nhãn hiệu.</p>
        <p>Để xem chi tiết, vui lòng truy cập:
           <a href="https://dichvucong.ipvietnam.gov.vn/tra-cuu-nhan-hieu?so_don=4-2025-20619&loai=NH">
             Tra cứu hồ sơ
           </a>
        </p>
        </body></html>
        """
        url = extract_first_portal_url(html, "", PATTERNS)
        assert url is not None
        assert "4-2025-20619" in url

