"""Configuration centralisée (portable + PyInstaller + USB)."""

from __future__ import annotations

import os
import sys
import json
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv(dotenv_path: Path) -> None:
    """Charge un fichier .env simple (KEY=VALUE) dans os.environ si absent."""
    if not dotenv_path.exists():
        return
    try:
        for raw in dotenv_path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = value
    except Exception:
        # Ne jamais bloquer l'app sur un .env invalide.
        return


def is_frozen() -> bool:
    """True when running from bundled executable."""
    return bool(getattr(sys, "frozen", False))


def get_base_dir(portable: bool) -> Path:
    """
    Runtime base directory for data/logs/config.
    - Source mode: project root
    - Frozen mode: executable folder (USB-friendly)
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    if portable:
        return Path(sys.argv[0]).resolve().parent
    return Path(__file__).resolve().parent


def get_bundle_dir() -> Path:
    """
    Directory of bundled resources.
    In onefile mode, this is sys._MEIPASS.
    """
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS"))
    return Path(__file__).resolve().parent


@dataclass(frozen=True)
class AppConfig:
    # Réseau
    default_ssh_port: int = 22
    default_sip_port: int = 5060
    socket_timeout_s: float = 3.0

    # TFTP
    tftp_remote_path: str = "/var/lib/tftpboot/"

    # Fichiers locaux (relatifs au projet)
    data_dir_name: str = "data"
    logs_dir_name: str = "logs"
    db_filename: str = "app.db"
    log_filename: str = "app.log"
    settings_filename: str = "settings.json"

    # UI
    default_timezone: str = "Central Europe Standard/Daylight Time"


def load_config(portable: bool) -> tuple[AppConfig, Path, Path, Path]:
    """
    Retourne:
      (config, app_root, db_path, log_path)
    """
    app_root = get_base_dir(portable)
    _load_dotenv(app_root / ".env")
    cfg = AppConfig(
        default_ssh_port=int(os.environ.get("DEFAULT_SSH_PORT", "22")),
        default_sip_port=int(os.environ.get("DEFAULT_SIP_PORT", "5060")),
        socket_timeout_s=float(os.environ.get("SOCKET_TIMEOUT_S", "3.0")),
        tftp_remote_path=os.environ.get("TFTP_REMOTE_PATH", "/var/lib/tftpboot/"),
        default_timezone=os.environ.get(
            "DEFAULT_TIMEZONE", "Central Europe Standard/Daylight Time"
        ),
    )
    data_dir = app_root / cfg.data_dir_name
    logs_dir = app_root / cfg.logs_dir_name
    db_path = data_dir / cfg.db_filename
    log_path = logs_dir / cfg.log_filename
    return cfg, app_root, db_path, log_path


def ensure_app_dirs(app_root: Path, cfg: AppConfig) -> tuple[Path, Path]:
    """Crée les dossiers data/ et logs/."""
    data_dir = app_root / cfg.data_dir_name
    logs_dir = app_root / cfg.logs_dir_name
    data_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    return data_dir, logs_dir


def ensure_default_config(app_root: Path, cfg: AppConfig) -> Path:
    """Create default runtime config in data/settings.json if missing."""
    data_dir = app_root / cfg.data_dir_name
    data_dir.mkdir(parents=True, exist_ok=True)
    settings_path = data_dir / cfg.settings_filename
    if settings_path.exists():
        return settings_path

    payload = {
        "created_at": datetime.utcnow().isoformat() + "Z",
        "default_ssh_port": cfg.default_ssh_port,
        "default_sip_port": cfg.default_sip_port,
        "socket_timeout_s": cfg.socket_timeout_s,
        "tftp_remote_path": cfg.tftp_remote_path,
        "default_timezone": cfg.default_timezone,
    }
    settings_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return settings_path


def is_probably_removable(base_dir: Path) -> bool:
    """
    Best-effort removable-media detection (optional UX logging only).
    """
    try:
        if os.name == "nt":
            drive = base_dir.drive
            if not drive:
                return False
            import ctypes

            DRIVE_REMOVABLE = 2
            dtype = ctypes.windll.kernel32.GetDriveTypeW(f"{drive}\\")
            return dtype == DRIVE_REMOVABLE
        p = str(base_dir)
        return p.startswith("/media/") or p.startswith("/run/media/") or p.startswith("/mnt/")
    except Exception:
        return False

