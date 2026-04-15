"""
Microsoft Graph API HTTP client.

Features:
- Injects Authorization: Bearer header automatically
- Retries on HTTP 429 (rate-limit) with Retry-After back-off
- Raises PermissionError on HTTP 401 (token expired)
- Paginates automatically via @odata.nextLink
- Separate binary download for attachment $value endpoints
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Generator, Optional

import requests

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_MAX_RETRIES = 3
_DEFAULT_BACKOFF = 5  # seconds when Retry-After header is missing

logger = logging.getLogger(__name__)


class GraphClient:
    """Thin, typed wrapper around requests.Session for Microsoft Graph API."""

    def __init__(self, access_token: str):
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

    # ── Public helpers ─────────────────────────────────────────────────────

    def get(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Perform a GET request, return parsed JSON dict."""
        return self._request("GET", url, params=params, **kwargs)

    def get_bytes(self, url: str, **kwargs: Any) -> bytes:
        """Download raw bytes (e.g. attachment $value endpoint)."""
        full_url = self._full(url)
        for attempt in range(1, _MAX_RETRIES + 1):
            resp = self._session.get(full_url, **kwargs)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", _DEFAULT_BACKOFF))
                logger.warning("Rate limited (attempt %d). Waiting %ds...", attempt, wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.content
        raise RuntimeError(f"Failed to download bytes from {url} after {_MAX_RETRIES} attempts")

    def paginate(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Yield all items across paginated Graph API responses.
        Automatically follows @odata.nextLink until exhausted.
        """
        next_url: Optional[str] = url
        current_params = params
        while next_url:
            data = self.get(next_url, params=current_params)
            yield from data.get("value", [])
            next_url = data.get("@odata.nextLink")
            current_params = None  # nextLink already embeds all query params

    # ── Internal ───────────────────────────────────────────────────────────

    def _request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        full_url = self._full(url)
        for attempt in range(1, _MAX_RETRIES + 1):
            resp = self._session.request(method, full_url, params=params, **kwargs)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", _DEFAULT_BACKOFF))
                logger.warning("Rate limited (attempt %d). Waiting %ds...", attempt, wait)
                time.sleep(wait)
                continue
            if resp.status_code == 401:
                raise PermissionError(
                    "Access token expired or invalid. Please sign in again."
                )
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError(
            f"Request {method} {url} failed after {_MAX_RETRIES} attempts"
        )

    @staticmethod
    def _full(url: str) -> str:
        return url if url.startswith("http") else GRAPH_BASE + url

