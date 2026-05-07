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
  Append a tuple (label, [phrase]) to CLASSIFICATION_RULES.
  Each tuple = one phrase (OR logic: any matching phrase → its label).
  First matching rule wins — ORDER MATTERS.
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
    is_scan: bool = False                    # True when text was obtained via OCR (scanned PDF)
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
    # "Số: 72820/SHTT-SC.IP"  — OCR may garble "Số:" to "Sô%", "Só#", "sá:", etc.
    # Label charset: oôố (normal) + ó (U+00F3) + á (U+00E1) for OCR noise variants.
    # Separator: exclude Ø (U+00D8) so it is captured as part of the number, not skipped.
    # Number: allow leading Ø (U+00D8) as OCR noise for digit '2' (e.g. "Ø3788" = "23788").
    # Separator after number: allow ) in addition to / (OCR often confuses / and ));
    # also allow no separator when digits run directly into uppercase suffix.
    r"[Ss][oôốóá][^\dØ\n]{0,8}"
    r"([Ø\d]{3,6}(?:[/\)]\s*)?[A-ZĐÁÀẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÉÈẺẼẸÊẾỀỂỄỆÍÌỈĨỊÓÒỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÚÙỦŨỤƯỨỪỬỮỰÝỲỶỸỴ"
    r"a-z0-9\-\.]+)",
    re.UNICODE,
)

# "Hà Nội, ngày 13 tháng 04 năm 2026"
# OCR noise: rotated-scan PDFs sometimes give "0gày" instead of "Ngày"
_RE_ISSUE_DATE = re.compile(
    r"(?:[Nn]|0)g[àa]y\s+(\d{1,2})\s+th[áa]ng\s+(\d{1,2})\s+n[ăa]m\s+(\d{4})",
    re.IGNORECASE | re.UNICODE,
)

# "Số đơn: 4-2025-20619"  or  "(số đơn 4-2015-33594)" (no colon)
# Separator [:\-] is optional so we also catch inline mentions without punctuation.
# The capture group \d+-\d+-\d+ naturally excludes "ĐN1-2017-00311" (ĐN prefix ≠ digit).
_RE_SO_DON = re.compile(
    # Standard: "Số đơn: 4-2025-20619"  or  OCR "Sốđơn1-2022-08586" (no space/colon)
    # Letter-prefix: "Số đơn: DT1-2025-14774" (maintenance/duy-trì type)
    # OCR noise: "sá đơn:" (sá for Số), "ØT1-..." (Ø for D in DT prefix)
    # [^\w\n]{0,5}   = separator, no line crossing
    # [^\s\dĐđ]{0,2} = 0-2 char optional prefix (allows DT/ØT); excludes Đ/đ so ĐN1-format is blocked
    r"[Ss][oốáa][\s]*đ[ơo]n[^\w\n]{0,5}([^\s\dĐđ]{0,2}\d+-\d+-\d+)",
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

# "Nhãn hiệu: SKYLINE" — OCR may use { or space instead of colon
# [^\w\n]{1,5} requires at least one separator char (prevents matching "Nhãn hiệu." as noun)
_RE_NHAN_HIEU = re.compile(
    r"Nh[ãa]n hi[eệ]u[^\w\n]{1,5}([^\n]+)",
    re.UNICODE,
)

# "Tên sáng chế: Quạt trần" — OCR may give "ché" for "chế" and "{" for ":"
_RE_TEN_SANG_CHE = re.compile(
    r"T[êe]n s[áa]ng ch[^\s]{1,2}[^\w\n]{1,5}([^\n]+)",
    re.UNICODE,
)

# "Tên giải pháp hữu ích: BỘ GIẢM XÓC" — OCR-robust separator
_RE_TEN_GPHI = re.compile(
    r"T[êe]n gi[ảa]i ph[áa]p h[ữu][uư] [íiì]ch[^\w\n]{1,5}([^\n]+)",
    re.UNICODE,
)

# "Tên kiểu dáng công nghiệp: Bàn cờ caro" — OCR-robust separator
_RE_TEN_KIEU_DANG = re.compile(
    r"T[êe]n ki[eể][uư] d[áa]ng c[oô]ng ngh[iệ][eệ]p[^\w\n]{1,5}([^\n]+)",
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
    # ── TBCB: thông báo cấp bằng / văn bằng ──────────────────────────────────
    # Source: Mapping.docx phrases 1-4. Check first — these docs also contain
    # "đáp ứng các điều kiện bảo hộ" (TBND phrase 6), so must take priority.
    ("TBCB", ["để được cấp Giấy chứng nhận đăng ký nhãn hiệu"]),
    ("TBCB", ["để được cấp Bằng độc quyền kiểu dáng công nghiệp"]),
    ("TBCB", ["để được cấp và duy trì hiệu lực năm thứ nhất của Bằng độc quyền sáng chế"]),
    ("TBCB", ["để được cấp và duy trì hiệu lực năm thứ nhất của Bằng độc quyền giải pháp hữu ích"]),

    # ── TBND/QĐTC: thông báo nêu dự định từ chối / quyết định từ chối ────────
    # Source: Mapping.docx phrases 5-12
    ("TBND/QĐTC", ["Đối tượng trong đơn nêu trên sẽ bị từ chối cấp Giấy chứng nhận đăng ký nhãn hiệu"]),
    ("TBND/QĐTC", ["Đối tượng trong đơn nêu trên đáp ứng các điều kiện bảo hộ đối với"]),
    ("TBND/QĐTC", ["Đối tượng nêu trong đơn không đáp ứng tiêu chuẩn bảo hộ"]),
    ("TBND/QĐTC", ["Về việc từ chối cấp Giấy chứng nhận đăng ký nhãn hiệu"]),
    ("TBND/QĐTC", ["Về việc từ chối cấp Bằng độc quyền kiểu dáng công nghiệp"]),
    ("TBND/QĐTC", ["Về việc từ chối cấp Bằng độc quyền sáng chế"]),
    ("TBND/QĐTC", ["Về việc từ chối cấp Bằng độc quyền giải pháp hữu ích"]),
    ("TBND/QĐTC", ["Về việc từ chối bảo hộ kiểu dáng công nghiệp đăng ký quốc tế tại Việt Nam"]),
    # Contract registration rejection (scan PDFs — body text only, no subject line captured)
    # Both phrases appear in file 14 OCR body text (multi-phrase: ALL must match).
    # "chối đăng ký" is in the rejection sentence; "hợp đồng" is in the document body.
    ("TBND/QĐTC", ["chối đăng ký", "hợp đồng"]),

    # ── TĐHT/DL2M: thẩm định hình thức, deadline 2 tháng ─────────────────────
    # Source: Mapping.docx phrases 13-14
    ("TĐHT/DL2M", ["V/v thông báo kết quả thẩm định hình thức"]),
    ("TĐHT/DL2M", ["Trong thời hạn 02 tháng kể từ ngày"]),

    # ── CNĐ: chấp nhận đơn hợp lệ ────────────────────────────────────────────
    # Source: Mapping.docx phrase 15
    ("CNĐ", ["Về việc chấp nhận đơn hợp lệ"]),

    # ── TB0DL: thông báo không có deadline ────────────────────────────────────
    # Source: Mapping.docx phrases 16-23
    ("TB0DL", ["V/v thông báo kết quả xử lý ý kiến phản đối đơn"]),
    ("TB0DL", ["Về việc gia hạn hiệu lực Giấy chứng nhận đăng ký nhãn hiệu"]),
    ("TB0DL", ["Về việc duy trì hiệu lực Bằng độc quyền sáng chế"]),
    ("TB0DL", ["Ghi nhận yêu cầu duy trì hiệu lực Bằng độc quyền giải pháp hữu ích"]),
    ("TB0DL", ["sẽ được tiếp tục xử lý theo quy định sau khi có kết quả thẩm định cuối cùng"]),
    ("TB0DL", ["Chấp nhận yêu cầu sửa đổi, bổ sung đơn"]),
    ("TB0DL", ["Ghi nhận thay đổi người nộp đơn"]),
    ("TB0DL", ["Về việc thụ lý giải quyết khiếu nại lần đầu"]),
    # Fallback phrases for scan PDFs where subject line is not captured by OCR.
    # These are shorter substrings of existing rules above, matched from document body.
    # Multi-phrase entries: ALL phrases must appear (order-independent).
    ("TB0DL", ["Gia hạn hiệu lực", "nhãn hiệu"]),                         # file 17 scan (OCR has "04" between words)
    ("TB0DL", ["duy trì hiệu lực Bằng độc quyền sáng chế"]),              # file 18 scan
    ("TB0DL", ["duy trì hiệu lực Bằng độc quyền giải pháp hữu ích"]),     # file 19 scan
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
    if not m:
        return None
    val = m.group(1).strip()
    # Clean OCR artifacts introduced by _RE_SO_CONG_VAN's looser patterns:
    #   Ø at start of number = OCR noise for digit '2' (e.g. "Ø3788" → "23788")
    val = re.sub(r"^Ø(\d{2,})", r"2\1", val)
    #   No separator between digits and uppercase suffix → insert "/"
    #   e.g. "22868SHTT-SCVB" → "22868/SHTT-SCVB"
    val = re.sub(r"(\d{3,6})(?=[A-ZĐ])", r"\1/", val)
    #   ')' used as separator instead of '/' (OCR confusion) → fix
    val = val.replace(")", "/")
    #   Trailing period + lowercase letters = OCR noise from adjacent word
    #   e.g. "SHTT.v" → "SHTT" (but preserve ".IP" or other uppercase suffixes)
    val = re.sub(r"\.[a-z]+$", "", val)
    #   Trailing isolated period = OCR noise
    val = re.sub(r"\.$", "", val)
    return val


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
    """Extract product/trademark name from the document.

    Tries each field label in priority order:
      - Nhãn hiệu: X
      - Tên sáng chế: X
      - Tên giải pháp hữu ích: X
      - Tên kiểu dáng công nghiệp: X
    Returns the first match, stripped of whitespace.
    """
    for pattern in (_RE_NHAN_HIEU, _RE_TEN_SANG_CHE, _RE_TEN_GPHI, _RE_TEN_KIEU_DANG):
        m = pattern.search(text)
        if m:
            return m.group(1).strip()
    return None


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


def _norm_for_match(s: str) -> str:
    """Lowercase + strip all punctuation/special chars + collapse whitespace.
    Keeps Unicode letters (including Vietnamese diacritics) and digits.
    This makes matching robust against PDF extraction artifacts like extra
    commas, slashes, or other punctuation variations.
    """
    s = s.lower()
    s = re.sub(r"[^\w\s]", "", s, flags=re.UNICODE)  # keep letters/digits/spaces
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def classify_document(text: str) -> Optional[str]:
    """
    Return the label of the first matching CLASSIFICATION_RULE, or None.
    All phrases in a rule must be present for a match.
    Matching is case-insensitive and ignores commas/semicolons (PDF extraction
    sometimes inserts or omits punctuation without changing the meaning).
    """
    text_norm = _norm_for_match(text)
    for label, phrases in CLASSIFICATION_RULES:
        if all(_norm_for_match(p) in text_norm for p in phrases):
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

_SIG_BLOCK_RE = re.compile(
    r"(Ký bởi|Cơ quan|Bộ Khoa học|Ngày ký|Giờ ký|Cục Sở hữu trí tuệ)[^\n]*",
    re.IGNORECASE,
)


def _is_scan_pdf(text: str) -> bool:
    """Return True if extracted text is only the digital-signature block (image-based PDF)."""
    stripped = _SIG_BLOCK_RE.sub("", text).strip()
    return len(stripped) < 50


def _is_scan_pdf_file(pdf_path: Path) -> bool:
    """Return True if pdf_path is an image-based (scanned) PDF requiring OCR.

    Opens the file with PyMuPDF's native text extractor (no OCR) and checks
    whether the resulting text is essentially empty (only the digital-signature
    block). This is used to set ParsedDocument.is_scan without running OCR twice.
    """
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        pages = [page.get_text("text") for page in doc]
        doc.close()
        return _is_scan_pdf(normalize_text("\n".join(pages)))
    except Exception:
        return False


def _extract_text_ocr(pdf_path: Path) -> str:
    """OCR fallback for image-based PDFs.

    Renders each page to a correctly-oriented PNG (applying any stored page rotation)
    and calls Tesseract directly via subprocess. This is necessary because PyMuPDF's
    get_textpage_ocr() returns text in PDF coordinates which are rotated for scanned
    documents (rotation=270 is common for Vietnamese IP office docs).

    Requirements (system-level, not Python packages):
      - macOS:   brew install tesseract tesseract-lang
      - Windows: winget install UB-Mannheim.TesseractOCR
                 then download vie.traineddata to Tesseract's tessdata folder
                 https://github.com/tesseract-ocr/tessdata_best
    """
    import os
    import subprocess
    import tempfile

    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        texts: List[str] = []
        for page in doc:
            try:
                if page.rotation != 0:
                    # Rotated pages (e.g. rotation=270): render to upright PNG first so
                    # Tesseract reads in the correct visual order.  get_textpage_ocr()
                    # would OCR an upright image but then map text back to the rotated
                    # PDF coordinate system, causing the header area to be missed.
                    pix = page.get_pixmap(dpi=300)  # applies page.rotation automatically
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                        tmp_path = f.name
                    pix.save(tmp_path)
                    try:
                        proc = subprocess.run(
                            ["tesseract", tmp_path, "stdout", "-l", "vie"],
                            capture_output=True, text=True, encoding="utf-8", timeout=60,
                        )
                        texts.append(proc.stdout)
                    finally:
                        os.unlink(tmp_path)
                else:
                    # Non-rotated pages: built-in OCR is fine.
                    tp = page.get_textpage_ocr(language="vie", dpi=300, full=True)
                    texts.append(page.get_text(textpage=tp))
            except Exception as page_exc:
                logger.debug("OCR page %d of %s failed: %s", page.number, pdf_path.name, page_exc)
        doc.close()
        result = normalize_text("\n".join(texts))
        logger.info("OCR extracted %d chars from %s", len(result), pdf_path.name)
        return result
    except Exception as exc:
        logger.warning("OCR failed for %s: %s — install Tesseract + vie language pack", pdf_path.name, exc)
        return ""


def extract_text_from_pdf(pdf_path: Path) -> str:
    """
    Extract all text from a PDF file using PyMuPDF (fitz).
    For image-based (scanned) PDFs, falls back to Tesseract OCR automatically.
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
        text = normalize_text("\n".join(pages))
        if _is_scan_pdf(text):
            logger.info("Scan PDF detected (%s), falling back to OCR …", pdf_path.name)
            return _extract_text_ocr(pdf_path)
        return text
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

    is_scan = False
    if pdf_path is not None:
        is_scan = _is_scan_pdf_file(pdf_path)
        pdf_text = extract_text_from_pdf(pdf_path)
        if pdf_text:
            combined = normalize_text(combined + "\n" + pdf_text)

    result = ParsedDocument(raw_text_snippet=combined[:2000], is_scan=is_scan)

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

    # For scanned PDFs: always use filename as so_don (more reliable than OCR text)
    # Pattern: {seq}-[{so_don}]-... e.g. "1-[GH4-2026-00466]-154-ONLI-2026-156666_signed.pdf"
    if is_scan and pdf_path is not None:
        m = re.search(r"\[([^\]]+)\]", pdf_path.name)
        if m:
            result.so_don = m.group(1)
            logger.debug("so_don from filename (OCR): %s → %s", pdf_path.name, result.so_don)

    return result

