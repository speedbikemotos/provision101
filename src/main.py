"""Portable entrypoint from src/ for build/distribution."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Allow importing project-root modules while keeping src entrypoint.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config import ensure_app_dirs, ensure_default_config, is_probably_removable, load_config
from database import get_connection, init_db
from ssh_bootstrap import check_ssh_available, ensure_ssh_on_windows
from ui_main import MainWindow
from PyQt6.QtWidgets import QApplication


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portable", action="store_true", help="Mode USB (chemins relatifs)")
    parser.add_argument("--debug", action="store_true", help="Logs plus verbeux")
    args = parser.parse_args()

    cfg, app_root, db_path, log_path = load_config(portable=args.portable)
    ensure_app_dirs(app_root, cfg)
    settings_path = ensure_default_config(app_root, cfg)

    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(str(log_path), encoding="utf-8")],
    )
    logging.info("Runtime base directory: %s", app_root)
    logging.info("Runtime settings file: %s", settings_path)
    if is_probably_removable(app_root):
        logging.info("USB/removable media detected. Running in portable mode.")

    ssh_available = True
    if sys.platform.startswith("win"):
        ssh_available, ssh_msg = ensure_ssh_on_windows()
        logging.info("SSH detection/install (Windows): %s", ssh_msg)
    else:
        ssh_available, ssh_msg = check_ssh_available()
        logging.info("SSH detection: %s", ssh_msg)
    if not ssh_available:
        logging.warning("SSH is unavailable. SSH-dependent actions will be disabled.")

    conn = get_connection(db_path)
    init_db(conn)

    app = QApplication(sys.argv)
    app.setApplicationName("Cisco Provisioning Tool + SIP Reboot")
    window = MainWindow(db_connection=conn, ssh_available=ssh_available)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

