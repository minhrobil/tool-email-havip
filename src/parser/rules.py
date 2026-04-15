"""
Rule-based parser for Vietnamese "công văn" (official document) content.

Extracted fields
────────────────
  so_cong_van      "53397/SHTT-NH.IP"
  so_cong_van_num  "53397"              numeric prefix only (matches Excel column)
  issue_date       date(2026, 4, 13)   from "ngày 13 tháng 04 năm 2026"
  so_don           "4-2025-20619"       from "Số đơn: 4-2025-20619" or "(số đơn 4-2025-20619)"
  so_yeu_cau       "CĐ4-2026-00098"    from "Số yêu cầu: CĐ4-2026-00098"
  so_gcn           "286000"             from "GCNĐKNH số 286000" or full certificate field
  deadline_months  2                    from "Trong thời hạn 02 tháng kể từ…"
                                        or converted from "thời hạn 90 ngày" (÷ 30, rounded)
  deadline_date    issue_date + relativedelta(months=deadline_months)
  loai_cong_van    classified label     from CLASSIFICATION_RULES
  loai_hinh_don    "Nhãn hiệu" etc.    from LOAI_HINH_RULES
  noi_dung         "Về việc..." subject line, or first long paragraph (max 300 chars)

Deadline calculation note:
  Uses dateutil.relativedelta for calendar-month addition.
  E.g. 2026-04-13 + 2 months = 2026-06-13  (not 60 days).
  Day-based deadlines (e.g. "90 ngày") are rounded to the nearest whole month.

Adding new classification rules:
  Append a tuple (label, [phrase1, phrase2, ...]) to CLASSIFICATION_RULES.
  All phrases must appear (case-insensitive) for the rule to match.
  First matching rule wins.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import List, Optional

from dateutil.relativedelta import relativedelta

logger = logging.getLogger(__name__)


# ── ParsedDocument ─────────────────────────────────────────────────────────

@dataclass
class ParsedDocument:
    so_cong_van: Optional[str] = None
    so_cong_van_num: Optional[str] = None    # numeric prefix only, e.g. "30369"
    issue_date: Optional[date] = None
    so_don: Optional[str] = None
    so_yeu_cau: Optional[str] = None
    so_gcn: Optional[str] = None             # Giấy chứng nhận đăng ký nhãn hiệu number
    deadline_months: Optional[int] = None
    deadline_date: Optional[date] = None
    loai_cong_van: Optional[str] = None
    loai_hinh_don: Optional[str] = None
    noi_dung_cong_van: Optional[str] = None
    nhan_hieu: Optional[str] = None          # text after "Nhãn hiệu:" until end of line
    raw_text_snippet: str = ""           # first 2000 chars for debugging
    parse_errors: List[str] = field(default_factory=list)


# ── Text normalization ─────────────────────────────────────────────────────

def normalize_text(text: str) -> str:
    """NFC-normalize, collapse horizontal whitespace, unify line endings."""
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[ \t\u00a0\u200b]+", " ", text)   # collapse spaces/tabs/NBSP
    text = re.sub(r"\r\n|\r", "\n", text)
    return text.strip()


# ── Regex patterns ─────────────────────────────────────────────────────────
# NOTE: Vietnamese diacritics inside character classes use literal chars
#       because \w does not reliably cover them in all Python re builds.

# "Số: 53397/SHTT-NH.IP" or "văn bản số 41049/QĐ-SHTT" — the reference number
# [Ss] covers both "Số:" (official document header) and "số" (inline in email body).
# Colon/dash is optional to handle both "Số: 41049/..." and "số 41049/..." formats.
_RE_SO_CONG_VAN = re.compile(
    r"[Ss][oố]\s*[:\-]?\s*(\d{3,6}/[A-ZĐÁÀẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÉÈẺẼẸÊẾỀỂỄỆÍÌỈĨỊÓÒỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÚÙỦŨỤƯỨỪỬỮỰÝỲỶỸỴ"
    r"a-z0-9\-\.]+)",
    re.UNICODE,
)

# "Hà Nội, ngày 13 tháng 04 năm 2026"
_RE_ISSUE_DATE = re.compile(
    r"ng[àa]y\s+(\d{1,2})\s+th[áa]ng\s+(\d{1,2})\s+n[ăa]m\s+(\d{4})",
    re.IGNORECASE | re.UNICODE,
)

# "Số đơn: 4-2025-20619"  or  "(số đơn 4-2015-33594)" (no colon)
# Separator [:\-] is optional so we also catch inline mentions without punctuation.
# The capture group \d+-\d+-\d+ naturally excludes "ĐN1-2017-00311" (ĐN prefix ≠ digit).
_RE_SO_DON = re.compile(
    r"[Ss][oố]\s+đ[ơo]n\s*[:\-]?\s*(\d+-\d+-\d+)",
    re.UNICODE,
)

# "Số yêu cầu: CĐ4-2026-00098"
_RE_SO_YEU_CAU = re.compile(
    r"[Ss][oố]\s+y[êe][uư]\s+c[ầa][uư]\s*[:\-]\s*([A-ZĐa-zđ0-9\-]+)",
    re.UNICODE,
)

# Deadline in months: "Trong thời hạn 02 tháng kể từ ngày ra thông báo này"
_RE_DEADLINE = re.compile(
    r"[Tt]rong\s+th[ờo]i\s+h[ạa]n\s+(\d{1,2})\s+th[áa]ng",
    re.UNICODE,
)

# Deadline in days: "trong thời hạn 90 ngày kể từ ngày nhận được"
_RE_DEADLINE_DAYS = re.compile(
    r"[Tt]rong\s+th[ờo]i\s+h[ạa]n\s+(\d{1,3})\s+ng[àa]y",
    re.UNICODE,
)

# "Nhãn hiệu: SKYLINE" — text after "Nhãn hiệu:" until end of line
_RE_NHAN_HIEU = re.compile(
    r"Nhãn hiệu\s*:\s*(.+)",
    re.UNICODE,
)

# Số Giấy chứng nhận đăng ký nhãn hiệu (GCNĐKNH)
# Matches:
#   "Số Giấy chứng nhận đăng ký nhãn hiệu bị yêu cầu hủy bỏ hiệu lực: 286000"
#   "GCNĐKNH số 286000"
_RE_SO_GCN = re.compile(
    r"(?:"
    r"S[oố]\s+Giấy\s+chứng\s+nhận\s+đăng\s+ký\s+nhãn\s+hiệu"
    r"(?:\s+bị\s+yêu\s+cầu\s+hủy\s+bỏ\s+hiệu\s+lực)?"
    r"\s*[:\-]\s*"
    r"|GCNĐKNH\s+số\s+"
    r")(\d+)",
    re.UNICODE | re.IGNORECASE,
)


# ── Classification rules ───────────────────────────────────────────────────
# Each entry: (label, [required_phrase, ...])
# Phrases are matched case-insensitively (normalized).
# First matching rule wins — ORDER MATTERS.

CLASSIFICATION_RULES: List[tuple] = [
    ("Dự định từ chối",            ["dự định từ chối"]),
    # Must come before "Cấp toàn bộ" because rejection-of-cancellation docs also contain
    # "đáp ứng các điều kiện bảo hộ" in their body text.
    ("Từ chối hủy bỏ HLC",         ["từ chối", "hủy bỏ hiệu lực"]),
    ("Từ chối toàn bộ",            ["từ chối cấp", "toàn bộ"]),
    ("Từ chối một phần",           ["từ chối cấp"]),
    ("Cấp toàn bộ",                ["đáp ứng các điều kiện bảo hộ"]),
    ("Cấp một phần",               ["đáp ứng điều kiện bảo hộ", "một phần"]),
    ("KQTĐ nội dung",              ["kết quả thẩm định nội dung"]),
    ("KQTĐ hình thức",             ["kết quả thẩm định hình thức"]),
    ("KQTĐ đơn thay đổi",          ["thẩm định", "thay đổi"]),
    ("Yêu cầu sửa đổi bổ sung",    ["yêu cầu sửa đổi"]),
    ("Thông báo vi phạm",          ["vi phạm"]),
]

# Application type detection rules
LOAI_HINH_RULES: List[tuple] = [
    ("Nhãn hiệu",               ["nhãn hiệu"]),
    ("Sáng chế",                ["sáng chế"]),
    ("Giải pháp hữu ích",       ["giải pháp hữu ích"]),
    ("Kiểu dáng công nghiệp",   ["kiểu dáng công nghiệp"]),
    ("Chỉ dẫn địa lý",          ["chỉ dẫn địa lý"]),
    ("Thiết kế bố trí",         ["thiết kế bố trí"]),
]

# Lines to skip when extracting noi_dung summary
_SKIP_PATTERNS = re.compile(
    r"^(S[oố]\s*[:\-]|Hà Nội|ng[àa]y\s+\d|\d{1,2}/\d{4}|Kính g[uử]i|Căn cứ|CỘNG HÒA|Độc lập|Tự do)",
    re.IGNORECASE | re.UNICODE,
)


# ── Extraction functions ───────────────────────────────────────────────────

def extract_so_cong_van(text: str) -> Optional[str]:
    m = _RE_SO_CONG_VAN.search(text)
    return m.group(1).strip() if m else None


def extract_issue_date(text: str) -> Optional[date]:
    m = _RE_ISSUE_DATE.search(text)
    if not m:
        return None
    day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(year, month, day)
    except ValueError as exc:
        logger.warning("Invalid issue date parsed (%d-%d-%d): %s", year, month, day, exc)
        return None


def extract_so_don(text: str) -> Optional[str]:
    m = _RE_SO_DON.search(text)
    return m.group(1).strip() if m else None


def extract_so_yeu_cau(text: str) -> Optional[str]:
    m = _RE_SO_YEU_CAU.search(text)
    return m.group(1).strip() if m else None


def extract_nhan_hieu(text: str) -> Optional[str]:
    """Extract trademark name: text after 'Nhãn hiệu:' until end of line."""
    m = _RE_NHAN_HIEU.search(text)
    return m.group(1).strip() if m else None


def extract_so_gcn(text: str) -> Optional[str]:
    """Extract GCNĐKNH (Giấy chứng nhận đăng ký nhãn hiệu) number."""
    m = _RE_SO_GCN.search(text)
    return m.group(1).strip() if m else None


def extract_deadline_months(text: str) -> Optional[int]:
    """
    Return deadline as a number of calendar months.
    - Prefers explicit month values: "Trong thời hạn 02 tháng"
    - Falls back to day-based values: "thời hạn 90 ngày" → rounds to nearest month
    """
    m = _RE_DEADLINE.search(text)
    if m:
        return int(m.group(1))
    # Fall back: deadline expressed in days — convert to nearest whole month
    m = _RE_DEADLINE_DAYS.search(text)
    if m:
        days = int(m.group(1))
        months = round(days / 30)
        return months if months >= 1 else 1
    return None


def calculate_deadline_date(
    issue_date: Optional[date],
    deadline_months: Optional[int],
) -> Optional[date]:
    """
    Compute deadline = issue_date + deadline_months calendar months.
    Uses dateutil.relativedelta (exact calendar month arithmetic).
    Example: date(2026, 4, 13) + 2 months = date(2026, 6, 13)
    """
    if issue_date is None or deadline_months is None:
        return None
    return issue_date + relativedelta(months=deadline_months)


def classify_document(text: str) -> Optional[str]:
    """
    Return the label of the first matching CLASSIFICATION_RULE, or None.
    All phrases in a rule must be present (case-insensitive) for a match.
    """
    text_lower = text.lower()
    for label, phrases in CLASSIFICATION_RULES:
        if all(p.lower() in text_lower for p in phrases):
            return label
    return None


def detect_loai_hinh_don(text: str) -> Optional[str]:
    """Return the application type label (Nhãn hiệu, Sáng chế, …) or None."""
    text_lower = text.lower()
    for label, phrases in LOAI_HINH_RULES:
        if all(p.lower() in text_lower for p in phrases):
            return label
    return None


def extract_noi_dung(text: str) -> Optional[str]:
    """
    Return the document subject / content summary (max 300 chars).

    Priority:
      1. First line starting with "Về việc …" — the formal subject heading.
      2. First substantive line (≥ 40 chars) that does not look like a header,
         date line, or greeting.
    """
    # Pass 1: subject line "Về việc ..."
    for line in text.splitlines():
        stripped = line.strip()
        if re.match(r"[Vv][ềe]\s+vi[eệ]c\b", stripped):
            return stripped[:300]
    # Pass 2: first long non-header line
    for line in text.splitlines():
        stripped = line.strip()
        if len(stripped) >= 40 and not _SKIP_PATTERNS.match(stripped):
            return stripped[:300]
    return None


# ── PDF text extraction ────────────────────────────────────────────────────

def extract_text_from_pdf(pdf_path: Path) -> str:
    """
    Extract all text from a PDF file using PyMuPDF (fitz).
    Returns empty string if extraction fails or library is missing.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.error(
            "PyMuPDF (fitz) is not installed. "
            "Run: pip install PyMuPDF  to enable PDF parsing."
        )
        return ""
    try:
        doc = fitz.open(str(pdf_path))
        pages: List[str] = [page.get_text("text") for page in doc]
        doc.close()
        return normalize_text("\n".join(pages))
    except Exception as exc:
        logger.warning("PDF text extraction failed for %s: %s", pdf_path, exc)
        return ""


# ── Main entry point ───────────────────────────────────────────────────────

def parse_document(
    text: str = "",
    pdf_path: Optional[Path] = None,
) -> ParsedDocument:
    """
    Parse a công văn from email body text and/or a PDF file.

    If pdf_path is provided, its text is extracted and merged with `text`
    so that fields present only in the PDF attachment are captured.

    Returns a ParsedDocument with all available fields populated.
    Fields that cannot be extracted are left as None.
    """
    combined = normalize_text(text or "")

    if pdf_path is not None:
        pdf_text = extract_text_from_pdf(pdf_path)
        if pdf_text:
            combined = normalize_text(combined + "\n" + pdf_text)

    result = ParsedDocument(raw_text_snippet=combined[:2000])

    result.so_cong_van    = extract_so_cong_van(combined)
    # Derive the numeric-only portion (e.g. "30369" from "30369/TB-SHTT.IP")
    if result.so_cong_van:
        m = re.match(r"^(\d+)", result.so_cong_van)
        result.so_cong_van_num = m.group(1) if m else None

    result.issue_date     = extract_issue_date(combined)
    result.so_don         = extract_so_don(combined)
    result.so_yeu_cau     = extract_so_yeu_cau(combined)
    result.so_gcn         = extract_so_gcn(combined)
    result.deadline_months = extract_deadline_months(combined)
    result.deadline_date  = calculate_deadline_date(result.issue_date, result.deadline_months)
    result.loai_cong_van  = classify_document(combined)
    result.loai_hinh_don  = detect_loai_hinh_don(combined)
    result.noi_dung_cong_van = extract_noi_dung(combined)
    result.nhan_hieu      = extract_nhan_hieu(combined)

    return result

