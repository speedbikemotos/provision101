"""SIP NOTIFY low-level sender for Cisco phones (UDP/5060).

Supports:
- Event: check-sync (config resync / reload)
- Event: reboot (full reboot, model dependent)
"""

from __future__ import annotations

import secrets
import socket
import time
from typing import Tuple


def _rand_token(nbytes: int = 8) -> str:
    return secrets.token_hex(nbytes)


def send_sip_notify(
    phone_ip: str,
    extension: str,
    server_ip: str,
    event: str = "check-sync",
    port: int = 5060,
    timeout: float = 3.0,
) -> Tuple[bool, str]:
    """
    Send SIP NOTIFY to a Cisco phone over UDP.

    Returns:
      (ok, response_text)
      - ok True if the message was sent successfully (even if no response)
      - response_text contains SIP response (e.g. 200 OK) or "(no response)"
    """
    sock: socket.socket | None = None
    try:
        # Auto-detect a usable source IP if server_ip is empty/invalid.
        if not server_ip or server_ip == "0.0.0.0":
            try:
                probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                probe.connect((phone_ip, port))
                server_ip = probe.getsockname()[0]
                probe.close()
            except Exception:
                server_ip = "127.0.0.1"

        branch = f"z9hG4bK{_rand_token(8)}"
        tag = _rand_token(6)
        call_id = f"{_rand_token(10)}@{server_ip}"
        local_port = secrets.randbelow(20000) + 40000  # 40000-59999

        # SIP headers require CRLF line endings.
        message = (
            f"NOTIFY sip:{extension}@{phone_ip} SIP/2.0\r\n"
            f"Via: SIP/2.0/UDP {server_ip}:{local_port};branch={branch}\r\n"
            f"Max-Forwards: 70\r\n"
            f"From: <sip:provision@{server_ip}>;tag={tag}\r\n"
            f"To: <sip:{extension}@{phone_ip}>\r\n"
            f"Call-ID: {call_id}\r\n"
            f"CSeq: 1 NOTIFY\r\n"
            f"Contact: <sip:provision@{server_ip}>\r\n"
            f"Event: {event}\r\n"
            f"Content-Length: 0\r\n"
            f"\r\n"
        )

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(timeout)
        # Bind to the chosen local port so Via matches the source port.
        sock.bind(("0.0.0.0", local_port))
        sock.sendto(message.encode("utf-8", errors="ignore"), (phone_ip, port))

        # Optional response handling (best-effort).
        try:
            data, _ = sock.recvfrom(4096)
            text = data.decode("utf-8", errors="replace").strip()
            return True, text if text else "(empty response)"
        except socket.timeout:
            return True, "(no response)"
        except Exception as exc:
            return True, f"(response read failed: {exc})"
    except Exception as exc:
        return False, f"Failed to send SIP NOTIFY: {exc}"
    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass


def reboot_phone(phone_ip: str, extension: str, server_ip: str, port: int = 5060, timeout: float = 3.0) -> Tuple[bool, str]:
    return send_sip_notify(phone_ip, extension, server_ip, event="reboot", port=port, timeout=timeout)


def resync_phone(phone_ip: str, extension: str, server_ip: str, port: int = 5060, timeout: float = 3.0) -> Tuple[bool, str]:
    return send_sip_notify(phone_ip, extension, server_ip, event="check-sync", port=port, timeout=timeout)

