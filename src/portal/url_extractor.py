"""
Portal URL extractor — finds IP Vietnam document lookup URLs inside email bodies.

Strategy (in order):
  1. Parse href="..." attributes from HTML body
  2. Scan raw text of HTML body for bare URLs (catches onclick= and data-* attrs)
  3. Scan plain text body for URLs
  4. Filter by configured domain patterns (e.g. "ipvietnam.gov.vn")
  5. Deduplicate and return ordered list

Configuration:
  portal.url_patterns in config.json — list of substrings that must appear
  in the URL's host/path for it to be considered a portal link.

Example email body fragment (HTML):
  <a href="https://dichvucong.ipvietnam.gov.vn/tra-cuu?so=53397">Xem hồ sơ</a>
  → extracts "https://dichvucong.ipvietnam.gov.vn/tra-cuu?so=53397"
"""
from __future__ import annotations

import html as _html_module
import logging
import re
from typing import List, Optional

logger = logging.getLogger(__name__)

# Match http(s) URLs — stop at whitespace, quotes, angle-brackets, closing parens/brackets
_RE_URL = re.compile(
    r'https?://[^\s\'"<>()\[\]]+',
    re.IGNORECASE,
)

# Match href="..." and href='...' attributes in HTML
_RE_HREF = re.compile(
    r'href=["\']([^"\']+)["\']',
    re.IGNORECASE,
)

# Match the portal access code: "nhập mã <hex32>" in email body
_RE_ACCESS_CODE = re.compile(
    r"nh[ậa]p\s+m[ãa]\s+([a-fA-F0-9]{14,})",
    re.IGNORECASE | re.UNICODE,
)

# Base URL used to construct portal links from access code when no href is found
_PORTAL_BASE_URL = "https://thongbao.ipvietnam.gov.vn/tra-cuu-don/"


def extract_portal_urls(
    body_html: str,
    body_text: str,
    url_patterns: List[str],
) -> List[str]:
    """
    Extract all portal document URLs from an email body.

    Strategy:
      1. href attributes in HTML (covers "Ấn vào đây" links)
      2. Bare URLs in plain text and HTML
      3. Construct URL from access code pattern "nhập mã <hex>" if nothing else found

    Args:
        body_html:    Full HTML body string (may be empty).
        body_text:    Plain text body string (may be empty).
        url_patterns: Domain/path substrings to match (case-insensitive).

    Returns:
        Deduplicated list of matching URLs, preserving discovery order.
    """
    raw_candidates = (
        _hrefs_from_html(body_html)
        + _bare_urls(body_text)
        + _bare_urls(body_html)
    )
    found = _filter_and_dedup(raw_candidates, url_patterns)

    # Fallback: construct URL from the "nhập mã <code>" access code in the email body
    if not found:
        access_code = extract_portal_access_code(body_text, body_html)
        if access_code:
            constructed = _PORTAL_BASE_URL + access_code
            logger.debug("Constructed portal URL from access code: %s", constructed)
            found = [constructed]

    return found


def _hrefs_from_html(html: str) -> List[str]:
    """Extract href attribute values that start with http(s)."""
    if not html:
        return []
    result = []
    for href in _RE_HREF.findall(html):
        url = _html_module.unescape(href).strip()
        if url.startswith(("http://", "https://")):
            result.append(url)
    return result


def _bare_urls(text: str) -> List[str]:
    """Find raw http(s) URLs in any text string."""
    if not text:
        return []
    return [u.rstrip(".,;)'\"") for u in _RE_URL.findall(text)]


def _filter_and_dedup(candidates: List[str], patterns: List[str]) -> List[str]:
    """Keep only URLs matching at least one pattern; remove duplicates."""
    matched: List[str] = []
    seen: set = set()
    for url in candidates:
        url_lower = url.lower()
        if any(p.lower() in url_lower for p in patterns) and url not in seen:
            matched.append(url)
            seen.add(url)
    if matched:
        logger.debug("Found %d portal URL(s): %s", len(matched), matched[:3])
    else:
        logger.debug("No portal URLs found (patterns=%s)", patterns)
    return matched


def extract_portal_access_code(body_text: str, body_html: str = "") -> Optional[str]:
    """
    Extract the portal access code from email body.

    Looks for the pattern "nhập mã <hex_code>" which appears in IP Vietnam
    notification emails, e.g. "nhập mã eaf68de2849446a481472877dc83486a".

    Returns the hex code string, or None if not found.
    """
    for text in (body_text, body_html):
        if not text:
            continue
        m = _RE_ACCESS_CODE.search(text)
        if m:
            code = m.group(1).strip()
            logger.debug("Found portal access code: %s", code)
            return code
    return None


def extract_first_portal_url(
    body_html: str,
    body_text: str,
    url_patterns: List[str],
) -> Optional[str]:
    """
    Return the first portal URL found, or None if the email contains no portal link.
    """
    urls = extract_portal_urls(body_html, body_text, url_patterns)
    return urls[0] if urls else None

