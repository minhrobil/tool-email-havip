"""
Microsoft Graph OAuth2 authentication using MSAL PublicClientApplication.

Token cache is stored at:  ~/.tool_mail_cong_van/token_cache.bin

First run:   opens browser for interactive login
Later runs:  uses cached token silently (auto-refresh if expired)
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable, List, Optional

import msal

logger = logging.getLogger(__name__)

# Cache location in user home directory (writable on any Windows machine)
_CACHE_DIR  = Path.home() / ".tool_mail_cong_van"
_CACHE_FILE = _CACHE_DIR / "token_cache.bin"

# MSAL error codes that mean the account itself is invalid — interactive
# login cannot fix these, so we clear the cache and force re-login.
_FATAL_AUTH_ERRORS = {
    "invalid_grant",        # refresh token revoked / expired
    "interaction_required", # silent auth impossible; needs fresh interactive login
}
_FATAL_ERROR_CODES = {
    50053,   # account locked out
    50055,   # password expired
    50057,   # account disabled
    50064,   # credential validation failed
    70008,   # refresh token expired / revoked
    70011,   # invalid scope
    90072,   # account not in tenant
}


class AuthRequiredError(Exception):
    """Raised when authentication has completely failed and the user must log in again.

    The GUI catches this to clear the token cache and redirect to the login screen.
    """
    def __init__(self, reason: str = ""):
        super().__init__(reason or "Cần đăng nhập lại Microsoft 365.")
        self.reason = reason


class GraphAuth:
    """Manages Microsoft Graph authentication with persistent token cache."""

    def __init__(self, client_id: str, authority: str, scopes: List[str]):
        self.client_id = client_id
        self.authority = authority
        self.scopes = scopes
        self._cache = self._load_cache()
        self._app = msal.PublicClientApplication(
            client_id=self.client_id,
            authority=self.authority,
            token_cache=self._cache,
            validate_authority=False,  # skip tenant discovery at init; network call deferred to login
        )

    # ── Cache helpers ──────────────────────────────────────────────────────

    def _load_cache(self) -> msal.SerializableTokenCache:
        cache = msal.SerializableTokenCache()
        if _CACHE_FILE.exists():
            try:
                cache.deserialize(_CACHE_FILE.read_text(encoding="utf-8"))
                logger.debug("Token cache loaded from %s", _CACHE_FILE)
            except Exception as exc:
                logger.warning("Could not load token cache (%s) — will re-authenticate.", exc)
        return cache

    def _save_cache(self) -> None:
        if self._cache.has_state_changed:
            _CACHE_DIR.mkdir(parents=True, exist_ok=True)
            _CACHE_FILE.write_text(self._cache.serialize(), encoding="utf-8")
            logger.debug("Token cache saved.")

    # ── Public API ─────────────────────────────────────────────────────────

    def get_token(self, on_tick: Optional[Callable[[int], None]] = None) -> str:
        """Return a valid access token.

        1. Tries silent acquisition first (uses refresh token automatically).
        2. Falls back to interactive browser login if silent fails.

        Raises AuthRequiredError if:
          - The account is blocked / disabled / refresh token revoked.
          - Interactive login times out or the user cancels.
        Never returns None — either returns a valid token or raises.
        """
        accounts = self._app.get_accounts()
        if accounts:
            result = self._app.acquire_token_silent(
                scopes=self.scopes, account=accounts[0]
            )
            if result and "access_token" in result:
                self._save_cache()
                logger.debug("Token acquired silently for %s", accounts[0].get("username"))
                return result["access_token"]

            # Silent failed — check if it's a fatal account error
            if result and "error" in result:
                self._check_fatal(result)
                # Non-fatal (e.g. interaction_required) → fall through to interactive

        # Interactive login
        token = self.get_token_interactive_force(on_tick=on_tick)
        if not token:
            raise AuthRequiredError("Đăng nhập thất bại hoặc quá thời gian chờ.")
        return token

    def get_token_interactive_force(
        self,
        timeout_seconds: int = 120,
        on_tick: Optional[Callable[[int], None]] = None,
    ) -> Optional[str]:
        """Force an interactive browser login, ignoring any cached account.

        Runs the MSAL blocking call in a daemon thread so this method can
        enforce a hard timeout (default 120 s = 2 minutes).

        on_tick(remaining) is called once per second with the remaining seconds
        so callers can show a countdown to the user.

        Returns None on timeout/cancellation (caller should raise AuthRequiredError).
        """
        logger.info("Đang mở trình duyệt để đăng nhập Microsoft...")
        result_box: list = [None]
        done = threading.Event()

        def _acquire() -> None:
            try:
                result_box[0] = self._app.acquire_token_interactive(
                    scopes=self.scopes,
                    prompt="select_account",
                )
            except Exception as exc:
                logger.error("Interactive login failed: %s", exc)
            finally:
                done.set()

        threading.Thread(target=_acquire, daemon=True).start()

        # Poll every second so we can deliver countdown ticks and honour the timeout
        for remaining in range(timeout_seconds, 0, -1):
            if done.wait(timeout=1.0):
                break           # login finished (success or error)
            if on_tick:
                on_tick(remaining)
        else:
            logger.warning(
                "Đăng nhập quá %d giây — hết thời gian chờ. "
                "Vui lòng nhấn 'Đăng nhập Microsoft' để thử lại.",
                timeout_seconds,
            )
            return None

        result = result_box[0]
        if result and "access_token" in result:
            self._save_cache()
            claims = result.get("id_token_claims") or {}
            username = claims.get("preferred_username", "unknown")
            logger.info("Đăng nhập thành công: %s", username)
            return result["access_token"]

        if result and "error" in result:
            self._check_fatal(result)   # may raise AuthRequiredError

        err = (result or {}).get("error_description", "Unknown error")
        logger.error("Không lấy được token: %s", err)
        return None

    def is_authenticated(self) -> bool:
        """Return True if there is at least one cached account."""
        return bool(self._app.get_accounts())

    def get_username(self) -> Optional[str]:
        """Return the username of the first cached account, or None."""
        accounts = self._app.get_accounts()
        return accounts[0].get("username") if accounts else None

    def logout(self) -> None:
        """Remove all cached accounts and delete the cache file."""
        for account in self._app.get_accounts():
            self._app.remove_account(account)
        if _CACHE_FILE.exists():
            _CACHE_FILE.unlink()
        logger.info("Đã đăng xuất và xóa cache token.")

    # ── Private ────────────────────────────────────────────────────────────

    def _check_fatal(self, result: dict) -> None:
        """Raise AuthRequiredError if the MSAL result indicates a fatal auth failure."""
        error = result.get("error", "")
        error_codes = result.get("error_codes", [])
        desc = result.get("error_description", "")

        is_fatal_error = error in _FATAL_AUTH_ERRORS
        is_fatal_code  = bool(set(error_codes) & _FATAL_ERROR_CODES)

        if is_fatal_error or is_fatal_code:
            logger.warning("Auth fatal error [%s %s]: %s", error, error_codes, desc)
            raise AuthRequiredError(
                f"Tài khoản không thể xác thực ({error or error_codes}). "
                "Vui lòng đăng nhập lại."
            )

