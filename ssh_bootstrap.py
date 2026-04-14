"""System SSH client detection/installation helpers."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Tuple


def check_ssh_available() -> Tuple[bool, str]:
    """Check whether system ssh command is available."""
    ssh_path = shutil.which("ssh")
    if not ssh_path:
        return False, "ssh command not found in PATH."
    try:
        result = subprocess.run(
            ["ssh", "-V"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        # OpenSSH often writes version to stderr.
        msg = (result.stderr or result.stdout or "").strip()
        if result.returncode == 0 or msg.lower().startswith("openssh"):
            return True, f"ssh detected: {msg or ssh_path}"
        return False, f"ssh command returned code {result.returncode}: {msg}"
    except Exception as exc:
        return False, f"ssh detection failed: {exc}"


def ensure_ssh_on_windows() -> Tuple[bool, str]:
    """
    Ensure SSH client exists on Windows.
    Attempts OpenSSH Client capability install if missing.
    """
    ok, msg = check_ssh_available()
    if ok:
        return True, msg

    if os.name != "nt":
        return False, msg

    install_cmd = [
        "powershell",
        "-NoProfile",
        "-Command",
        "Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0",
    ]
    try:
        result = subprocess.run(
            install_cmd,
            check=False,
            capture_output=True,
            text=True,
            timeout=240,
        )
        post_ok, post_msg = check_ssh_available()
        if post_ok:
            return True, f"OpenSSH install succeeded. {post_msg}"
        details = (result.stdout or "") + "\n" + (result.stderr or "")
        return (
            False,
            "OpenSSH install attempt failed or requires admin rights. "
            "Please install OpenSSH Client from Windows Features.\n"
            f"{details.strip()}",
        )
    except Exception as exc:
        return (
            False,
            "OpenSSH install could not be executed. "
            "Please install OpenSSH Client from Windows Features.\n"
            f"Error: {exc}",
        )

