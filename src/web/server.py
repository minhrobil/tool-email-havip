"""
FastAPI web server — Xử lý Mail công văn.

Endpoints:
  GET  /                     → index.html (single-page app)
  GET  /api/auth/status      → {authenticated, username}
  GET  /api/auth/url         → initiate MSAL OAuth, return redirect URL
  GET  /api/auth/callback    → exchange auth code for token, redirect → /
  POST /api/auth/logout      → clear token + cache
  POST /api/scan             → start email processing (async, SSE-driven)
  GET  /api/scan/stream      → Server-Sent Events: real-time progress
  GET  /api/scan/result      → final ProcessResult JSON
  GET  /api/scan/download    → download last output folder as ZIP

Auth flow:
  1. /api/auth/url  → returns Microsoft login URL
  2. browser redirects to Microsoft → user logs in
  3. Microsoft redirects back to /api/auth/callback?code=...&state=...
  4. server exchanges code for token → redirects to /
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import threading
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_DATETIME_FMT = "%d/%m/%Y %H:%M"
_DEFAULT_EXPORT = str(Path.home() / "Desktop" / "CongVanExport")


# ── Single-user server state ────────────────────────────────────────────────

class _State:
    def __init__(self) -> None:
        self.config        = None
        self.auth          = None          # GraphAuth instance
        self.auth_flow: Optional[dict] = None   # pending MSAL code flow
        self.running: bool = False
        self.scan_queue: Optional[asyncio.Queue] = None
        self.scan_result: Optional[dict] = None
        self.last_output_folder: str = _DEFAULT_EXPORT


_st = _State()


# ── App factory ────────────────────────────────────────────────────────────

def create_app(
    config_path: Optional[Path] = None,
    port: int = 8080,
) -> FastAPI:

    redirect_uri = f"http://localhost:{port}/api/auth/callback"

    app = FastAPI(title="Xử lý Mail công văn", docs_url=None, redoc_url=None)

    # ── Startup ────────────────────────────────────────────────────────────
    @app.on_event("startup")
    def _startup() -> None:
        try:
            from ..config import load_config
            from ..auth.graph_auth import GraphAuth
            _st.config = load_config(config_path)
            _st.auth = GraphAuth(
                client_id=_st.config.azure.client_id,
                authority=_st.config.azure.authority,
                scopes=_st.config.azure.scopes,
            )
            if _st.auth.is_authenticated():
                logger.info("Token cache hit — đã đăng nhập: %s", _st.auth.get_username())
        except Exception as exc:
            logger.error("Startup error (config/auth): %s", exc)

    # ── Serve frontend ──────────────────────────────────────────────────────
    _html_path = Path(__file__).parent / "static" / "index.html"

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse(_html_path.read_text(encoding="utf-8"))

    # ── Auth routes ────────────────────────────────────────────────────────
    @app.get("/api/auth/status")
    def auth_status():
        if _st.auth and _st.auth.is_authenticated():
            return {"authenticated": True, "username": _st.auth.get_username() or ""}
        return {"authenticated": False, "username": ""}

    @app.get("/api/auth/url")
    def auth_url():
        if not _st.auth:
            raise HTTPException(500, "Config chưa tải được. Kiểm tra config.json.")
        flow = _st.auth._app.initiate_auth_code_flow(
            scopes=_st.auth.scopes,
            redirect_uri=redirect_uri,
        )
        _st.auth_flow = flow
        return {"url": flow["auth_uri"]}

    @app.get("/api/auth/callback")
    def auth_callback(
        code: Optional[str]  = Query(default=None),
        state: Optional[str] = Query(default=None),
        error: Optional[str] = Query(default=None),
    ):
        if error or not code:
            return RedirectResponse("/?auth_error=" + (error or "cancelled"))
        if not _st.auth_flow:
            return RedirectResponse("/?auth_error=no_flow")
        try:
            result = _st.auth._app.acquire_token_by_auth_code_flow(
                auth_code_flow=_st.auth_flow,
                auth_response={"code": code, "state": state or ""},
            )
            _st.auth_flow = None
            if result and "access_token" in result:
                _st.auth._save_cache()
                claims = result.get("id_token_claims") or {}
                logger.info(
                    "Đăng nhập thành công: %s",
                    claims.get("preferred_username", "?"),
                )
                return RedirectResponse("/")
        except Exception as exc:
            logger.error("Auth callback error: %s", exc)
        return RedirectResponse("/?auth_error=exchange_failed")

    @app.post("/api/auth/logout")
    def auth_logout():
        if _st.auth:
            _st.auth.logout()
        _st.auth_flow = None
        return {"ok": True}

    # ── Scan routes ────────────────────────────────────────────────────────

    class ScanRequest(BaseModel):
        date_from: str       # DD/MM/YYYY HH:MM
        date_to: str         # DD/MM/YYYY HH:MM
        output_folder: str

    def _parse_dt(raw: str) -> datetime:
        raw = raw.strip()
        if len(raw) == 10:
            raw += " 00:00"
        return datetime.strptime(raw, _DATETIME_FMT)

    @app.post("/api/scan")
    async def start_scan(req: ScanRequest):
        if _st.running:
            raise HTTPException(409, "Đang có lần quét đang chạy. Vui lòng đợi.")
        if not _st.auth or not _st.auth.is_authenticated():
            raise HTTPException(401, "Chưa đăng nhập Microsoft.")

        try:
            date_from = _parse_dt(req.date_from)
            date_to   = _parse_dt(req.date_to)
        except ValueError as exc:
            raise HTTPException(400, f"Thời gian không hợp lệ: {exc}")

        output = req.output_folder.strip() or _DEFAULT_EXPORT
        _st.last_output_folder = output

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()
        _st.scan_queue  = queue
        _st.scan_result = None
        _st.running     = True

        def _worker() -> None:
            def _push(obj: Optional[dict]) -> None:
                asyncio.run_coroutine_threadsafe(queue.put(obj), loop)

            def progress(c: int, t: int, m: str, s: Optional[dict] = None) -> None:
                _push({"c": c, "t": t, "m": m, "s": s or {}})

            try:
                from ..processor.email_processor import EmailProcessor
                processor = EmailProcessor(_st.config, _st.auth)
                result = processor.run(
                    progress=progress,
                    date_from=date_from,
                    date_to=date_to,
                    output_folder_override=output,
                )
                _st.scan_result = {
                    "total":         result.total_emails,
                    "success":       result.success_count,
                    "review":        result.review_count,
                    "dup":           result.duplicate_count,
                    "error":         result.error_count,
                    "summary":       result.summary(),
                    "errors":        result.errors[:10],
                    "output_folder": output,
                }
            except Exception as exc:
                logger.exception("Scan worker error")
                _st.scan_result = {"fatal": str(exc), "output_folder": output}
            finally:
                _st.running = False
                _push(None)   # sentinel — tells SSE stream to close

        threading.Thread(target=_worker, daemon=True).start()
        return {"status": "started"}

    @app.get("/api/scan/stream")
    async def scan_stream():
        """Server-Sent Events: push progress updates to browser."""
        queue = _st.scan_queue
        if queue is None:
            raise HTTPException(404, "Chưa có lần quét nào được khởi động.")

        async def _generate():
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=25.0)
                except asyncio.TimeoutError:
                    yield "event: ping\ndata: {}\n\n"
                    continue
                if msg is None:
                    # Scan finished — push final result as "done" event
                    payload = json.dumps(_st.scan_result or {})
                    yield f"event: done\ndata: {payload}\n\n"
                    break
                yield f"data: {json.dumps(msg)}\n\n"

        return StreamingResponse(
            _generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/scan/result")
    def scan_result():
        if _st.scan_result is None:
            raise HTTPException(404, "Chưa có kết quả.")
        return _st.scan_result

    @app.get("/api/scan/download")
    def download_zip():
        """Zip the last output folder and stream it to the browser."""
        folder = Path(_st.last_output_folder)
        if not folder.exists():
            raise HTTPException(404, f"Thư mục không tồn tại: {folder}")

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for fp in sorted(folder.rglob("*")):
                if fp.is_file():
                    zf.write(fp, fp.relative_to(folder))
        buf.seek(0)

        fname = f"CongVanExport_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        return StreamingResponse(
            buf,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename={fname}"},
        )

    return app

# Web server — not implemented yet.
# See docs/tasks/2.md for the plan.
