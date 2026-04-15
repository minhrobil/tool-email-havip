"""
Browser-based file downloader for the IP Vietnam document portal.

Uses Playwright (sync API) with headless Chromium to:
  1. Navigate to the portal lookup URL from the email body
  2. Wait for the page to fully load
  3. Enter access code if required
  4. Try to click the "Tải tất cả" (Download all) button
  5. If that yields no downloads, fall back to clicking each .file-item__title link
  6. Capture all triggered file downloads and save to the target daily folder

Prerequisites (run once after pip install):
  pip install playwright
  playwright install chromium

Design notes:
  - Downloads are captured via page.on("download", ...) event listener
  - save_as() is called inside the browser context (before browser.close())
  - Button discovery tries each selector in order; first visible match wins
  - File-item fallback clicks individual file links one at a time if the bulk
    download button is missing or triggers no downloads
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

_WIN_ILLEGAL = re.compile(r'[\\/:*?"<>|]')


@dataclass
class PortalDownloadResult:
    """Result of a portal download attempt."""
    portal_url: str = ""
    downloaded_paths: List[Path] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    success: bool = False


class BrowserDownloader:
    """Downloads files from a portal URL using Playwright browser automation."""

    def __init__(
        self,
        button_selectors: List[str],
        page_load_timeout_ms: int = 30000,
        wait_after_click_ms: int = 8000,
        headless: bool = True,
    ):
        """
        Args:
            button_selectors:      CSS/text selectors tried in order to find the
                                   download button. First visible match is clicked.
            page_load_timeout_ms:  Max ms to wait for the page to reach networkidle.
            wait_after_click_ms:   How long to wait after clicking for downloads to
                                   start (and complete for small files).
            headless:              Run Chromium in headless mode (True for production).
        """
        self._selectors = button_selectors or [
            "button:has-text('Tải tất cả')",
            "a:has-text('Tải tất cả')",
            "button:has-text('Tải xuống tất cả')",
            "a:has-text('Tải xuống tất cả')",
            "[class*='download-all']",
        ]
        self._page_load_timeout = page_load_timeout_ms
        self._wait_after_click = wait_after_click_ms
        self._headless = headless

    # ── Public ─────────────────────────────────────────────────────────────

    def download(self, portal_url: str, target_folder: Path, access_code: str = "") -> PortalDownloadResult:
        """
        Navigate to portal_url, optionally enter an access code, click the download button,
        and save all files.

        Args:
            portal_url:    The lookup URL extracted from the email body.
            target_folder: Daily folder where downloaded files will be saved.
            access_code:   Optional access code ("mã tra cứu") to enter on the portal page
                           before looking for the download button.

        Returns:
            PortalDownloadResult with paths of successfully saved files.
        """
        result = PortalDownloadResult(portal_url=portal_url)

        try:
            from playwright.sync_api import sync_playwright  # noqa: F401
        except ImportError:
            msg = (
                "Playwright chưa cài đặt. Chạy lệnh sau để cài:\n"
                "  pip install playwright\n"
                "  playwright install chromium"
            )
            logger.error(msg)
            result.notes.append(msg)
            return result

        target_folder.mkdir(parents=True, exist_ok=True)

        try:
            saved = self._run(portal_url, target_folder, result, access_code)
            result.downloaded_paths = saved
            result.success = bool(saved)
        except Exception as exc:
            logger.error("Browser download failed for %s: %s", portal_url, exc)
            result.notes.append(f"Lỗi tải file từ portal: {exc}")

        if not result.success and not result.notes:
            result.notes.append("Không tải được file nào từ portal")

        return result

    # ── Private ────────────────────────────────────────────────────────────

    def _run(
        self,
        url: str,
        target_folder: Path,
        result: PortalDownloadResult,
        access_code: str = "",
    ) -> List[Path]:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

        downloads_received = []
        saved: List[Path] = []

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=self._headless)
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()

            # Capture every download that the page triggers
            page.on("download", lambda d: downloads_received.append(d))

            # ── Navigate ───────────────────────────────────────────────────
            logger.info("Mở portal: %s", url)
            try:
                page.goto(url, timeout=self._page_load_timeout, wait_until="networkidle")
            except PWTimeout:
                logger.warning("Page load timed out — proceeding anyway: %s", url)
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass

            page_title = (page.title() or "")[:80]
            logger.info("Trang đã tải: %s", page_title)

            if _is_error_page(page):
                result.notes.append(f"Trang portal trả về lỗi (title='{page_title}')")
                browser.close()
                return []

            # ── Enter access code if provided ──────────────────────────────
            if access_code:
                self._enter_access_code(page, access_code, result)

            # ── Strategy 1: "Tải tất cả" bulk download button ─────────────
            button_clicked = self._click_download_button(page)
            if button_clicked:
                page.wait_for_timeout(self._wait_after_click)

            # ── Strategy 2: individual file-item links (fallback) ──────────
            if not downloads_received:
                if button_clicked:
                    logger.info("Nút tải đã click nhưng không có file — thử tải từng file")
                else:
                    logger.info("Không tìm thấy nút 'Tải tất cả' — thử tải từng file")

                items_clicked = self._click_file_items(page, result)
                if items_clicked:
                    page.wait_for_timeout(self._wait_after_click)

            # ── Nothing worked ─────────────────────────────────────────────
            if not downloads_received:
                if button_clicked and items_clicked:
                    result.notes.append("Đã thử nút tải và tải từng file nhưng không nhận được file nào")
                elif button_clicked:
                    result.notes.append("Nút tải đã được nhấn nhưng không có file nào được tải xuống")
                elif items_clicked:
                    result.notes.append("Thử tải từng file riêng lẻ nhưng không nhận được file nào")
                else:
                    result.notes.append("Không tìm thấy nút tải và không tìm thấy link file riêng lẻ trên trang portal")
                browser.close()
                return []

            # ── Save downloads (must happen BEFORE browser.close()) ────────
            for dl in downloads_received:
                filename = _sanitize(dl.suggested_filename or "download")
                dest = _unique_path(target_folder, filename)
                try:
                    dl.save_as(str(dest))   # blocks until download completes
                    saved.append(dest)
                    logger.info(
                        "  Đã tải: %-40s  (%s bytes)",
                        dest.name, f"{dest.stat().st_size:,}",
                    )
                except Exception as exc:
                    logger.error("Không lưu được file '%s': %s", filename, exc)
                    result.notes.append(f"Lỗi lưu: {filename} — {exc}")

            browser.close()

        return saved

    def _enter_access_code(self, page, access_code: str, result: PortalDownloadResult) -> bool:
        """
        Find the access code input field on the portal page, fill the code, and submit.
        Returns True if the code was entered, False if no input field was found.
        """
        from playwright.sync_api import TimeoutError as PWTimeout

        code_input_selectors = [
            "input[placeholder*='mã']",
            "input[placeholder*='Mã']",
            "input[placeholder*='code']",
            "input[placeholder*='tra cứu']",
            "input[type='text']",
            "input[type='password']",
        ]
        submit_selectors = [
            "button[type='submit']",
            "button:has-text('Xem')",
            "button:has-text('Tra cứu')",
            "button:has-text('Tìm kiếm')",
            "button:has-text('OK')",
            "input[type='submit']",
        ]

        for selector in code_input_selectors:
            try:
                inp = page.locator(selector).first
                if inp.count() == 0 or not inp.is_visible(timeout=3000):
                    continue
                inp.fill(access_code)
                logger.info("Nhập mã tra cứu (selector='%s'): %s…", selector, access_code[:14])

                # Try clicking a submit button
                submitted = False
                for sub_sel in submit_selectors:
                    try:
                        btn = page.locator(sub_sel).first
                        if btn.count() > 0 and btn.is_visible(timeout=2000):
                            btn.click(timeout=5000)
                            submitted = True
                            break
                    except Exception:
                        continue

                # Fallback: press Enter in the input field
                if not submitted:
                    inp.press("Enter")

                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass
                logger.info("Đã submit mã tra cứu")
                return True

            except PWTimeout:
                continue
            except Exception as exc:
                logger.debug("Code input selector '%s' error: %s", selector, exc)

        logger.debug("Không tìm thấy ô nhập mã tra cứu — bỏ qua")
        return False

    def _click_download_button(self, page) -> bool:
        """
        Try each configured selector in order.
        Returns True if a button was found and clicked, False otherwise.
        (Notes are added by the caller based on overall download outcome.)
        """
        from playwright.sync_api import TimeoutError as PWTimeout

        for selector in self._selectors:
            try:
                btn = page.locator(selector).first
                if btn.count() > 0 and btn.is_visible(timeout=3000):
                    logger.info("Nhấn nút tải: selector='%s'", selector)
                    btn.click(timeout=5000)
                    return True
            except PWTimeout:
                continue
            except Exception as exc:
                logger.debug("Selector '%s' không dùng được: %s", selector, exc)

        logger.info("Không tìm thấy nút 'Tải tất cả' trên trang: %s", page.url)
        return False

    def _click_file_items(self, page, result: PortalDownloadResult) -> bool:
        """
        Fallback: click each .file-item__title anchor individually to trigger downloads.
        Returns True if at least one item was found and clicked.
        """
        FILE_ITEM_SELECTOR = "a.file-item__title"

        try:
            items = page.locator(FILE_ITEM_SELECTOR)
            count = items.count()
            if count == 0:
                logger.debug("Không tìm thấy file-item links (selector='%s')", FILE_ITEM_SELECTOR)
                return False

            logger.info("Tải từng file riêng lẻ: tìm thấy %d file-item link(s)", count)
            clicked_any = False
            for i in range(count):
                try:
                    item = items.nth(i)
                    if item.is_visible(timeout=2000):
                        label = (item.inner_text() or "").strip()[:60]
                        logger.info("  Click file-item %d/%d: %s", i + 1, count, label)
                        item.click(timeout=5000)
                        # Brief pause so the download event fires before next click
                        page.wait_for_timeout(1500)
                        clicked_any = True
                except Exception as exc:
                    logger.debug("file-item[%d] click error: %s", i, exc)

            return clicked_any

        except Exception as exc:
            logger.debug("_click_file_items error: %s", exc)
            return False


# ── Helpers ────────────────────────────────────────────────────────────────

def _is_error_page(page) -> bool:
    """Heuristic: check for common error indicators on the page."""
    try:
        title = (page.title() or "").lower()
        error_words = ["404", "403", "500", "not found", "error", "access denied", "forbidden"]
        return any(w in title for w in error_words)
    except Exception:
        return False


def _sanitize(name: str) -> str:
    """Replace Windows-illegal chars and strip leading dots/spaces."""
    name = _WIN_ILLEGAL.sub("_", name)
    name = name.strip(". ")
    return name or "download"


def _unique_path(folder: Path, filename: str) -> Path:
    """
    Return a unique, deterministic path.
    If the filename exists, append _1, _2, … before the extension.
    """
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    candidate = folder / filename
    counter = 1
    while candidate.exists():
        candidate = folder / f"{stem}_{counter}{suffix}"
        counter += 1
    return candidate

