"""
Configuration loader for Công Văn Processor.
Reads config.json, provides typed dataclasses, validates required fields.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class AzureConfig:
    client_id: str
    tenant_id: str = "common"
    authority: str = ""
    scopes: List[str] = field(default_factory=lambda: [
        "https://graph.microsoft.com/Mail.Read",
        "https://graph.microsoft.com/Mail.ReadBasic",
    ])

    def __post_init__(self) -> None:
        if not self.authority:
            self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"


@dataclass
class MailConfig:
    target_folder_name: str = "Công văn"
    page_size: int = 50
    sender_email: str = "cucsohuutritue@ipvietnam.gov.vn"


@dataclass
class OutputConfig:
    root_folder: str = str(Path.home() / "Desktop" / "CongVanExport")
    excel_filename: str = "SO CONG VAN DEN-LIENDO.xlsx"
    date_folder_format: str = "%y.%m.%d"
    # If root_folder is unreachable, use this folder instead.
    # Empty string = auto-detect: ~/Desktop/CongVanExport
    fallback_output_folder: str = ""


@dataclass
class ProcessingConfig:
    strict_single_attachment: bool = False
    log_level: str = "INFO"


@dataclass
class PortalConfig:
    """Browser automation settings for IP Vietnam document portal downloads."""
    url_patterns: List[str] = field(default_factory=lambda: [
        "ipvietnam.gov.vn",
        "dichvucong.ipvietnam",
    ])
    download_button_selectors: List[str] = field(default_factory=lambda: [
        "button:has-text('Tải tất cả')",
        "a:has-text('Tải tất cả')",
        "button:has-text('Tải xuống tất cả')",
        "a:has-text('Tải xuống tất cả')",
        "[class*='download-all']",
    ])
    page_load_timeout_ms: int = 60000
    wait_after_click_ms: int = 15000
    pre_click_wait_ms: int = 3000         # extra wait after networkidle before clicking
    portal_retry_count: int = 3           # number of download attempts per portal URL
    retry_delay_ms: int = 4000            # wait between retry attempts
    headless: bool = True
    parallel_downloads: int = 5           # number of portal downloads to run concurrently


@dataclass
class AppConfig:
    azure: AzureConfig
    mail: MailConfig
    output: OutputConfig
    processing: ProcessingConfig
    portal: PortalConfig = field(default_factory=PortalConfig)


def load_config(config_path: Optional[Path] = None) -> AppConfig:
    """
    Load and parse configuration from config.json.
    Search order if config_path is None:
      1. Same directory as the frozen .exe, if running from PyInstaller
      2. Same directory as this module's package root
      3. Current working directory
    """
    if config_path is None:
        # Package root = parent of src/
        pkg_root = Path(__file__).parent.parent
        candidates = []
        if getattr(sys, "frozen", False):
            candidates.append(Path(sys.executable).parent / "config.json")
        candidates.extend([
            pkg_root / "config.json",
            Path(os.getcwd()) / "config.json",
        ])
        for c in candidates:
            if c.exists():
                config_path = c
                break

    if config_path is None or not config_path.exists():
        raise FileNotFoundError(
            "config.json not found. "
            "Please place config.json next to run_app.py or the .exe. "
            "See README.md for setup instructions."
        )

    with open(config_path, encoding="utf-8") as f:
        raw = json.load(f)

    azure_raw = raw.get("azure", {})
    client_id = azure_raw.get("client_id", "")
    if not client_id or client_id == "YOUR_AZURE_APP_CLIENT_ID_HERE":
        raise ValueError(
            "config.json: 'azure.client_id' is not set. "
            "Register an Azure App and paste the Application (client) ID. "
            "See README.md → Azure App Registration."
        )

    azure = AzureConfig(
        client_id=client_id,
        tenant_id=azure_raw.get("tenant_id", "common"),
        authority=azure_raw.get("authority", ""),
        scopes=azure_raw.get("scopes", [
            "https://graph.microsoft.com/Mail.Read",
        ]),
    )

    mail_raw = raw.get("mail", {})
    mail = MailConfig(
        target_folder_name=mail_raw.get("target_folder_name", "Công văn"),
        page_size=int(mail_raw.get("page_size", 50)),
        sender_email=mail_raw.get("sender_email", "cucsohuutritue@ipvietnam.gov.vn"),
    )

    out_raw = raw.get("output", {})
    root_folder_raw = out_raw.get(
        "root_folder",
        str(Path.home() / "Desktop" / "CongVanExport"),
    )
    fallback_folder_raw = out_raw.get("fallback_output_folder", "")
    output = OutputConfig(
        root_folder=str(Path(str(root_folder_raw)).expanduser()),
        excel_filename=out_raw.get("excel_filename", "SO CONG VAN DEN-LIENDO.xlsx"),
        date_folder_format=out_raw.get("date_folder_format", "%y.%m.%d"),
        fallback_output_folder=(
            str(Path(str(fallback_folder_raw)).expanduser())
            if fallback_folder_raw
            else ""
        ),
    )

    proc_raw = raw.get("processing", {})
    processing = ProcessingConfig(
        strict_single_attachment=bool(proc_raw.get("strict_single_attachment", False)),
        log_level=str(proc_raw.get("log_level", "INFO")),
    )

    portal_raw = raw.get("portal", {})
    portal = PortalConfig(
        url_patterns=portal_raw.get("url_patterns", [
            "ipvietnam.gov.vn",
            "dichvucong.ipvietnam",
        ]),
        download_button_selectors=portal_raw.get("download_button_selectors", [
            "button:has-text('Tải tất cả')",
            "a:has-text('Tải tất cả')",
            "button:has-text('Tải xuống tất cả')",
            "a:has-text('Tải xuống tất cả')",
            "[class*='download-all']",
        ]),
        page_load_timeout_ms=int(portal_raw.get("page_load_timeout_ms", 60000)),
        wait_after_click_ms=int(portal_raw.get("wait_after_click_ms", 15000)),
        pre_click_wait_ms=int(portal_raw.get("pre_click_wait_ms", 3000)),
        portal_retry_count=int(portal_raw.get("portal_retry_count", 3)),
        retry_delay_ms=int(portal_raw.get("retry_delay_ms", 4000)),
        headless=bool(portal_raw.get("headless", True)),
        parallel_downloads=int(portal_raw.get("parallel_downloads", 5)),
    )

    return AppConfig(azure=azure, mail=mail, output=output, processing=processing, portal=portal)
