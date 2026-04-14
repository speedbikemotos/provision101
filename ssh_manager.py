"""Gestionnaire SSH/SFTP pour le provisionnement Cisco."""

from __future__ import annotations

import socket
from typing import Callable, Optional, Tuple

import paramiko


LogCallback = Optional[Callable[[str], None]]


class SSHManager:
    """Encapsule la connexion SSH et les operations distantes."""

    def __init__(self) -> None:
        self._ssh_client: Optional[paramiko.SSHClient] = None
        self._sftp_client: Optional[paramiko.SFTPClient] = None
        self._sudo_password: Optional[str] = None

    @property
    def is_connected(self) -> bool:
        return self._ssh_client is not None

    def connect(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        timeout: int = 10,
    ) -> Tuple[bool, str]:
        """Ouvre une connexion SSH."""
        self.disconnect()
        try:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            client.connect(
                hostname=host,
                port=port,
                username=username,
                password=password,
                timeout=timeout,
                look_for_keys=False,
                allow_agent=False,
            )
            self._ssh_client = client
            self._sudo_password = password
            return True, "Connexion SSH reussie."
        except Exception as exc:  # pragma: no cover - depend du reseau
            return False, f"Echec de connexion: {exc}"

    def test_connection(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        timeout: int = 8,
    ) -> Tuple[bool, str]:
        """Teste la connexion sans conserver la session."""
        test_client = paramiko.SSHClient()
        test_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            test_client.connect(
                hostname=host,
                port=port,
                username=username,
                password=password,
                timeout=timeout,
                look_for_keys=False,
                allow_agent=False,
            )
            return True, "Test de connexion OK."
        except Exception as exc:  # pragma: no cover - depend du reseau
            return False, f"Test de connexion echoue: {exc}"
        finally:
            test_client.close()

    def execute_command(
        self,
        command: str,
        use_sudo: bool = False,
        timeout: int = 120,
        log_callback: LogCallback = None,
    ) -> Tuple[bool, str]:
        """Execute une commande distante et retourne (succes, sortie)."""
        if not self._ssh_client:
            return False, "Aucune connexion SSH active."

        final_command = command
        logged_command = command
        if use_sudo:
            if not self._sudo_password:
                return False, "Mot de passe sudo indisponible."
            escaped = self._sudo_password.replace("'", "'\"'\"'")
            final_command = f"echo '{escaped}' | sudo -S -p '' {command}"
            logged_command = f"echo '***' | sudo -S -p '' {command}"

        if log_callback:
            log_callback(f"$ {logged_command}")

        try:
            stdin, stdout, stderr = self._ssh_client.exec_command(
                final_command, timeout=timeout
            )
            _ = stdin
            out_text = stdout.read().decode("utf-8", errors="replace").strip()
            err_text = stderr.read().decode("utf-8", errors="replace").strip()
            exit_status = stdout.channel.recv_exit_status()

            combined_output = "\n".join(
                part for part in [out_text, err_text] if part
            ).strip()
            if not combined_output:
                combined_output = "(aucune sortie)"

            if log_callback:
                log_callback(combined_output)
                log_callback(f"[code retour: {exit_status}]")

            return exit_status == 0, combined_output
        except Exception as exc:  # pragma: no cover - depend du reseau
            error_text = f"Erreur execution commande: {exc}"
            if log_callback:
                log_callback(error_text)
            return False, error_text

    def upload_file(
        self,
        local_path: str,
        remote_path: str,
        log_callback: LogCallback = None,
    ) -> Tuple[bool, str]:
        """Upload un fichier via SFTP."""
        if not self._ssh_client:
            return False, "Aucune connexion SSH active."

        try:
            if not self._sftp_client:
                self._sftp_client = self._ssh_client.open_sftp()
            self._sftp_client.put(local_path, remote_path)
            message = f"Upload OK: {local_path} -> {remote_path}"
            if log_callback:
                log_callback(message)
            return True, message
        except Exception as exc:  # pragma: no cover - depend du reseau
            error_text = f"Echec upload {local_path}: {exc}"
            if log_callback:
                log_callback(error_text)
            return False, error_text

    def detect_os_release(self, log_callback: LogCallback = None) -> Tuple[bool, str]:
        """Lit /etc/os-release pour identifier la distribution distante."""
        return self.execute_command(
            "cat /etc/os-release", use_sudo=False, log_callback=log_callback
        )

    def disconnect(self) -> None:
        """Ferme proprement la connexion SSH/SFTP."""
        if self._sftp_client:
            self._sftp_client.close()
            self._sftp_client = None
        if self._ssh_client:
            self._ssh_client.close()
            self._ssh_client = None
        self._sudo_password = None


def check_ntp_server(ip: str, timeout: float = 2.0) -> bool:
    """
    Vérifie qu'un serveur NTP répond en UDP/123.
    Ne lève jamais d'exception: retourne False en cas d'erreur.
    """
    client: Optional[socket.socket] = None
    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.settimeout(timeout)
        packet = b"\x1b" + 47 * b"\0"
        client.sendto(packet, (ip, 123))
        data, _ = client.recvfrom(1024)
        return bool(data)
    except Exception:
        return False
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
