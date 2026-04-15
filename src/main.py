"""
Entry point for Xử lý Mail công văn.

Modes:
  GUI (default):   python run_app.py
  Headless:        python run_app.py --headless [options]

Headless options:
  --config PATH            Path to config.json (optional)
  --log-file PATH          Append log output to file (optional)
  --from-datetime STR      Start of email window  (DD/MM/YYYY HH:MM, default: today 00:00)
  --to-datetime   STR      End of email window    (DD/MM/YYYY HH:MM, default: today 23:59)
  --output-folder PATH     Root export folder     (default: ~/Desktop/CongVanExport)

Example — run from Task Scheduler every morning to process today's emails:
  python run_app.py --headless --log-file C:\\Logs\\cong_van.log
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

_DATETIME_FMT = "%d/%m/%Y %H:%M"


def _parse_cli_datetime(raw: str, field: str) -> datetime:
    raw = raw.strip()
    if len(raw) == 10:          # accept "DD/MM/YYYY" and append time
        raw += " 00:00"
    try:
        return datetime.strptime(raw, _DATETIME_FMT)
    except ValueError:
        raise ValueError(
            f"--{field}: định dạng không hợp lệ '{raw}'. "
            f"Dùng DD/MM/YYYY HH:MM  (ví dụ: 14/04/2026 08:00)"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Xử lý Mail công văn — Đọc và xử lý email công văn từ Outlook 365"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Chạy không có giao diện đồ họa (dành cho Task Scheduler)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Đường dẫn đến file config.json (tùy chọn)",
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Ghi log ra file (tùy chọn)",
    )
    parser.add_argument(
        "--from-datetime",
        type=str,
        default=None,
        metavar="DD/MM/YYYY HH:MM",
        help="Thời điểm bắt đầu lọc email (mặc định: hôm nay 00:00)",
    )
    parser.add_argument(
        "--to-datetime",
        type=str,
        default=None,
        metavar="DD/MM/YYYY HH:MM",
        help="Thời điểm kết thúc lọc email (mặc định: hôm nay 23:59)",
    )
    parser.add_argument(
        "--output-folder",
        type=str,
        default=None,
        metavar="PATH",
        help="Thư mục export (mặc định: ~/Desktop/CongVanExport)",
    )
    args = parser.parse_args()

    config_path = Path(args.config) if args.config else None

    # ── configure root logger ──────────────────────────────────────────────
    handlers: list = [logging.StreamHandler(sys.stdout)]
    if args.log_file:
        handlers.append(
            logging.FileHandler(args.log_file, encoding="utf-8", mode="a")
        )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=handlers,
        force=True,
    )

    if args.headless:
        # ── Resolve date range (default: today 00:00 → 23:59) ─────────────
        today = datetime.now()
        try:
            date_from = (
                _parse_cli_datetime(args.from_datetime, "from-datetime")
                if args.from_datetime
                else today.replace(hour=0, minute=0, second=0, microsecond=0)
            )
            date_to = (
                _parse_cli_datetime(args.to_datetime, "to-datetime")
                if args.to_datetime
                else today.replace(hour=23, minute=59, second=59, microsecond=0)
            )
        except ValueError as exc:
            logging.error(str(exc))
            sys.exit(1)

        output_folder = args.output_folder or str(
            Path.home() / "Desktop" / "CongVanExport"
        )
        _run_headless(config_path, date_from, date_to, output_folder)
    else:
        _run_gui()


def _run_headless(
    config_path: Path = None,
    date_from: datetime = None,
    date_to: datetime = None,
    output_folder: str = None,
) -> None:
    """Run the processor in headless/CLI mode (no GUI)."""
    from .config import load_config
    from .auth.graph_auth import GraphAuth
    from .processor.email_processor import EmailProcessor

    logger = logging.getLogger(__name__)
    logger.info("Khởi động ở chế độ headless...")
    logger.info(
        "Khoảng thời gian: %s  →  %s",
        date_from.strftime(_DATETIME_FMT) if date_from else "(không lọc)",
        date_to.strftime(_DATETIME_FMT)   if date_to   else "(không lọc)",
    )
    logger.info("Thư mục export: %s", output_folder or "(dùng config)")

    try:
        cfg = load_config(config_path)
    except Exception as e:
        logger.error("Không thể tải config: %s", e)
        sys.exit(1)

    logging.getLogger().setLevel(cfg.processing.log_level)

    auth = GraphAuth(
        client_id=cfg.azure.client_id,
        authority=cfg.azure.authority,
        scopes=cfg.azure.scopes,
    )

    # Headless mode cannot show a browser — token must already be cached
    if not auth.is_authenticated():
        logger.error(
            "Chưa đăng nhập. Vui lòng chạy ứng dụng GUI (run.bat) trước "
            "để đăng nhập Microsoft một lần, rồi chạy lại headless."
        )
        sys.exit(2)

    processor = EmailProcessor(cfg, auth)
    result = processor.run(
        progress=lambda c, t, m, s=None: logger.info(m),
        date_from=date_from,
        date_to=date_to,
        output_folder_override=output_folder,
    )

    logger.info(result.summary())
    sys.exit(1 if result.error_count > 0 else 0)


def _run_gui() -> None:
    """Launch the tkinter GUI application."""
    from .gui.app import run_gui
    run_gui()


if __name__ == "__main__":
    main()

