"""Interface principale PyQt6 pour le provisionnement Cisco."""

from __future__ import annotations

import logging
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
import re
from typing import Dict, List

from PyQt6.QtCore import QObject, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QGuiApplication
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QFileDialog,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from csv_handler import format_mac_display, is_valid_mac, load_phones_from_csv, normalize_mac
from ssh_manager import SSHManager
from ssh_manager import check_ntp_server
from sip_notify import reboot_phone, resync_phone
from xml_generator import generate_xml_files
from theme import Theme, get_theme_manager

DEFAULT_TIMEZONE = "Central Europe Standard/Daylight Time"
SUPPORTED_TIMEZONES = [
    "Central Europe Standard/Daylight Time",
    "Arab Standard/Daylight Time",
    "Arab Standard Time",
    "UTC",
]
TIMEZONE_TOOLTIP = "Certain timezones are required due to Cisco firmware bugs"
COL_MAC = 0
COL_EXT = 1
COL_PWD = 2
COL_IP = 3
COL_TZ = 4
COL_STATUS = 5


class NetworkScanWorker(QObject):
    """Worker QThread pour scan réseau non bloquant."""

    progress = pyqtSignal(int, str)
    log = pyqtSignal(str, str)
    finished = pyqtSignal(list, str)
    failed = pyqtSignal(str)

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        subnet: str,
        existing_macs: set[str],
    ) -> None:
        super().__init__()
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.subnet = subnet
        self.existing_macs = existing_macs

    def run(self) -> None:
        scan_ssh = SSHManager()
        self.progress.emit(5, "Initialisation du scan réseau...")
        ok, msg = scan_ssh.connect(self.host, self.port, self.username, self.password)
        self.log.emit("SSH", msg)
        if not ok:
            self.failed.emit("Impossible d'ouvrir une session SSH dédiée au scan.")
            return

        try:
            subnet = self.subnet.strip()
            if not subnet and re.fullmatch(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", self.host):
                subnet = ".".join(self.host.split(".")[:3])
            if not subnet:
                self.progress.emit(15, "Détection automatique du sous-réseau...")
                ok, auto_subnet = scan_ssh.execute_command(
                    "hostname -I | awk '{print $1}' | awk -F. '{print $1\".\"$2\".\"$3}' | head -n 1"
                )
                if not ok or not auto_subnet.strip():
                    self.failed.emit("Impossible de détecter automatiquement le sous-réseau.")
                    return
                subnet = auto_subnet.strip().splitlines()[-1].strip()

            if not re.fullmatch(r"\d{1,3}\.\d{1,3}\.\d{1,3}", subnet):
                self.failed.emit("Sous-réseau invalide. Exemple attendu: 192.168.1")
                return

            self.log.emit("SCAN", f"Scan du sous-réseau {subnet}.0/24 ...")
            self.progress.emit(30, "Lecture du cache ARP/NDP...")
            ok, neigh_output = scan_ssh.execute_command("ip neigh show", timeout=20)
            if not ok:
                self.failed.emit("Impossible de lire la table réseau (ip neigh).")
                return

            if subnet not in neigh_output:
                self.progress.emit(50, "Découverte active des hôtes (ping rapide)...")
                ping_cmd = (
                    f"for i in $(seq 1 254); do "
                    f"(ping -c 1 -W 1 {subnet}.$i >/dev/null 2>&1) & "
                    "if [ $((i % 32)) -eq 0 ]; then wait; fi; "
                    "done; wait; ip neigh show"
                )
                ok, neigh_output = scan_ssh.execute_command(ping_cmd, timeout=45)
                if not ok:
                    self.failed.emit("Le scan réseau a expiré ou échoué.")
                    return

            self.progress.emit(75, "Analyse des équipements détectés...")
            found: list[tuple[str, str]] = []
            seen = set(self.existing_macs)
            for line in neigh_output.splitlines():
                match = re.search(r"(\d+\.\d+\.\d+\.\d+).*\s([0-9a-f:]{17})\s", line, re.IGNORECASE)
                if not match:
                    continue
                ip_addr, mac_raw = match.groups()
                mac = normalize_mac(mac_raw)
                if not is_valid_mac(mac) or mac in seen:
                    continue
                seen.add(mac)
                found.append((ip_addr, mac))

            self.progress.emit(100, "Scan terminé.")
            self.finished.emit(found, subnet)
        finally:
            scan_ssh.disconnect()


class RebootWorker(QObject):
    """Worker QThread SIP NOTIFY (resync/reboot) non bloquant."""

    progress = pyqtSignal(int, str)
    per_phone = pyqtSignal(str, str)
    finished = pyqtSignal(int, int)

    def __init__(self, phones: list[dict], ssh: SSHManager, server_ip: str, mode: str) -> None:
        super().__init__()
        self.phones = phones
        self.ssh = ssh
        self.server_ip = server_ip
        self.mode = mode  # "check-sync" or "reboot"

    def run(self) -> None:
        total = len(self.phones)
        success = 0
        for idx, phone in enumerate(self.phones, start=1):
            ip = phone.get("ip", "").strip()
            ext = str(phone.get("ext", "")).strip()
            label = phone.get("mac", "N/A")
            if not ext:
                self.per_phone.emit(label, "Extension manquante")
                self.progress.emit(int(idx * 100 / max(total, 1)), f"{idx}/{total}")
                continue
            action = "Resync envoyé" if self.mode != "reboot" else "Reboot envoyé"
            ok = False
            resp = ""

            # Preferred path: direct SIP NOTIFY when phone IP is known.
            if ip:
                if self.mode == "reboot":
                    ok, resp = reboot_phone(ip, ext, self.server_ip)
                else:
                    ok, resp = resync_phone(ip, ext, self.server_ip)
                if ok:
                    success += 1
                    self.per_phone.emit(label, f"{action} | {resp.splitlines()[0] if resp else ''}".strip())
            else:
                resp = "IP du téléphone inconnue"

            # Fallback path: Asterisk notify by endpoint.
            if not ok:
                endpoint = ext
                if endpoint and self.ssh.is_connected:
                    event = "reboot" if self.mode == "reboot" else "check-sync"
                    cmd = f'asterisk -rx "pjsip send notify {event} {endpoint}"'
                    aok, _ = self.ssh.execute_command(cmd, use_sudo=True)
                    if aok:
                        success += 1
                        self.per_phone.emit(label, f"{action} (fallback Asterisk)")
                    else:
                        self.per_phone.emit(label, f"Echec ({resp or 'SIP NOTIFY'})")
                else:
                    self.per_phone.emit(label, f"Echec ({resp or 'SIP NOTIFY'})")
            self.progress.emit(int(idx * 100 / max(total, 1)), f"{idx}/{total}")
            # Bulk support: small delay between sends
            try:
                import time

                time.sleep(0.2)
            except Exception:
                pass
        self.finished.emit(success, total)


class NtpTestWorker(QObject):
    """Worker QThread pour test NTP non bloquant."""

    finished = pyqtSignal(bool, str)

    def __init__(self, ip: str) -> None:
        super().__init__()
        self.ip = ip

    def run(self) -> None:
        ok = False
        try:
            ok = check_ntp_server(self.ip)
        except Exception:
            ok = False
        self.finished.emit(ok, self.ip)


class MainWindow(QMainWindow):
    """Fenetre principale avec onglets et persistance SQLite."""

    def __init__(self, db_connection: sqlite3.Connection, ssh_available: bool = True) -> None:
        super().__init__()
        self.ssh = SSHManager()
        self.db = db_connection
        self.ssh_available = ssh_available
        self._connected_state = False
        self._is_busy = False
        self._suspend_table_events = False
        self.last_uc_ip = ""
        self.ntp_thread: QThread | None = None
        self.ntp_worker: NtpTestWorker | None = None
        self.reboot_thread: QThread | None = None
        self.reboot_worker: RebootWorker | None = None
        self.scan_thread: QThread | None = None
        self.scan_worker: NetworkScanWorker | None = None
        self.theme_manager = get_theme_manager()
        self.setWindowTitle("Cisco IP Phone Provisioning Tool")
        self._apply_adaptive_window_size()

        self._build_ui()
        self._apply_style()
        self._set_connected_ui(False)
        self._load_phones_from_db()
        self._log("INFO", "Application démarrée.")
        if not self.ssh_available:
            self._log("WARNING", "Client SSH système non détecté. Fonctions SSH désactivées.")

    # DB init is handled in database.init_db()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._make_scroll_tab(self._build_tab_connection()), "Connexion")
        self.tabs.addTab(self._make_scroll_tab(self._build_tab_server()), "Serveur")
        self.tabs.addTab(self._make_scroll_tab(self._build_tab_phones()), "Téléphones")
        self.tabs.addTab(self._make_scroll_tab(self._build_tab_database()), "DB")
        self.tabs.addTab(self._make_scroll_tab(self._build_tab_logs()), "Logs")
        self.tabs.currentChanged.connect(lambda _i: self._refresh_connection_dependent_ui())
        root.addWidget(self.tabs)

    def _make_scroll_tab(self, content: QWidget) -> QWidget:
        """Wrap each tab content in a scroll area for small screens."""
        area = QScrollArea()
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        area.setWidget(content)
        return area

    def _apply_adaptive_window_size(self) -> None:
        """Resize window to fit small/medium laptop screens safely."""
        screen = QGuiApplication.primaryScreen()
        if not screen:
            self.resize(1100, 760)
            return
        geom = screen.availableGeometry()
        width = max(900, min(1220, geom.width() - 40))
        height = max(620, min(820, geom.height() - 60))
        self.resize(width, height)

    def _build_tab_connection(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(16)
        group = QGroupBox("Connexion SSH")
        group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        grid = QGridLayout(group)
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(12)

        self.edt_host = QLineEdit()
        self.edt_host.setPlaceholderText("IP du serveur")
        self.spn_port = QSpinBox()
        self.spn_port.setRange(1, 65535)
        self.spn_port.setValue(22)
        self.edt_user = QLineEdit()
        self.edt_user.setPlaceholderText("Nom d'utilisateur")
        self.edt_password = QLineEdit()
        self.edt_password.setEchoMode(QLineEdit.EchoMode.Password)
        self.edt_password.setPlaceholderText("Mot de passe SSH/sudo")

        self.btn_test_connect = QPushButton("Tester connexion")
        self.btn_test_connect.clicked.connect(self.test_ssh_connection)
        self.btn_connect = QPushButton("Connexion")
        self.btn_connect.clicked.connect(self.connect_ssh)
        self.btn_disconnect = QPushButton("Déconnexion")
        self.btn_disconnect.clicked.connect(self.disconnect_ssh)

        self.lbl_status_dot = QLabel("●")
        self.lbl_status_dot.setObjectName("status_dot")
        self.lbl_status_text = QLabel("Non connecté")

        self.progress_label = QLabel("Action SSH en cours...")
        self.progress_label.hide()
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()

        grid.addWidget(QLabel("IP du serveur"), 0, 0)
        grid.addWidget(self.edt_host, 0, 1)
        grid.addWidget(QLabel("Port SSH"), 0, 2)
        grid.addWidget(self.spn_port, 0, 3)
        grid.addWidget(QLabel("Nom d'utilisateur"), 1, 0)
        grid.addWidget(self.edt_user, 1, 1)
        grid.addWidget(QLabel("Mot de passe"), 1, 2)
        grid.addWidget(self.edt_password, 1, 3)
        grid.addWidget(self.btn_test_connect, 2, 1)
        grid.addWidget(self.btn_connect, 2, 2)
        grid.addWidget(self.btn_disconnect, 2, 3)
        grid.addWidget(self.lbl_status_dot, 3, 0)
        grid.addWidget(self.lbl_status_text, 3, 1, 1, 3)
        grid.addWidget(self.progress_label, 4, 0, 1, 4)
        grid.addWidget(self.progress, 5, 0, 1, 4)

        # Theme switcher
        theme_group = QGroupBox("Apparence")
        theme_layout = QHBoxLayout(theme_group)
        self.btn_theme_light = QPushButton("Mode Clair")
        self.btn_theme_light.clicked.connect(lambda: self.switch_theme(Theme.LIGHT))
        self.btn_theme_dark = QPushButton("Mode Sombre")
        self.btn_theme_dark.clicked.connect(lambda: self.switch_theme(Theme.DARK))
        theme_layout.addWidget(self.btn_theme_light)
        theme_layout.addWidget(self.btn_theme_dark)
        theme_layout.addStretch()

        layout.addWidget(group)
        layout.addWidget(theme_group)
        layout.addStretch()
        return tab

    def _build_tab_server(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(14)

        setup_group = QGroupBox("Setup serveur TFTP")
        setup_row = QHBoxLayout(setup_group)
        self.btn_install_tftp = QPushButton("Installer TFTP + Chrony")
        self.btn_install_tftp.clicked.connect(self.install_tftp)
        self.btn_check_tftp = QPushButton("Vérifier dossier TFTP")
        self.btn_check_tftp.clicked.connect(self.check_tftp_folder)
        self.btn_restart_tftp = QPushButton("Redémarrer TFTP")
        self.btn_restart_tftp.clicked.connect(self.restart_tftp)
        setup_row.addWidget(self.btn_install_tftp)
        setup_row.addWidget(self.btn_check_tftp)
        setup_row.addWidget(self.btn_restart_tftp)
        setup_row.addStretch()
        self.server_progress_label = QLabel("Installation serveur inactif.")
        self.server_progress = QProgressBar()
        self.server_progress.setRange(0, 100)
        self.server_progress.setValue(0)
        self.server_progress.hide()

        config_group = QGroupBox("2) Paramètres SIP / UC / NTP")
        config_form = QFormLayout(config_group)
        self.edt_uc_ip = QLineEdit()
        self.edt_uc_ip.setPlaceholderText("IP du serveur SIP (UC)")
        self.edt_ntp_ip = QLineEdit()
        self.edt_ntp_ip.setPlaceholderText("IP du serveur NTP")
        self.sync_checkbox = QCheckBox("Utiliser IP UC comme serveur NTP")
        self.sync_checkbox.setChecked(True)
        self.sync_checkbox.toggled.connect(self._on_sync_checkbox_toggled)
        self.edt_uc_ip.textChanged.connect(self.sync_ntp_with_uc)
        self.edt_ntp_ip.textChanged.connect(lambda _t: self._set_ntp_status(False))
        self.btn_test_ntp = QPushButton("Tester NTP")
        self.btn_test_ntp.clicked.connect(self.test_ntp_server)
        self.lbl_ntp_status = QLabel("NTP: KO")
        self.lbl_ntp_status.setStyleSheet("color: #ef4444; font-weight: 700;")
        config_form.addRow("IP serveur SIP (UC)", self.edt_uc_ip)
        config_form.addRow("IP serveur NTP", self.edt_ntp_ip)
        config_form.addRow("", self.sync_checkbox)
        config_form.addRow("", self.btn_test_ntp)
        config_form.addRow("Statut NTP", self.lbl_ntp_status)

        deploy_group = QGroupBox("3) Déploiement")
        deploy_row = QHBoxLayout(deploy_group)
        self.lbl_deploy_hint = QLabel(
            "Sélectionnez des téléphones dans l'onglet Téléphones, puis cliquez sur Déployer."
        )
        self.lbl_deploy_hint.setWordWrap(True)
        deploy_row.addWidget(self.lbl_deploy_hint)
        self.lbl_deploy_result = QLabel("Résultat: en attente.")
        self.lbl_deploy_result.setStyleSheet("color: #9ca3af; font-weight: 600;")
        deploy_row.addWidget(self.lbl_deploy_result)
        deploy_row.addStretch()
        self.btn_deployer = QPushButton("Déployer")
        self.btn_deployer.setObjectName("btn_deployer")
        self.btn_deployer.clicked.connect(self.deploy_all)
        deploy_row.addWidget(self.btn_deployer)

        layout.addWidget(setup_group)
        layout.addWidget(self.server_progress_label)
        layout.addWidget(self.server_progress)
        layout.addWidget(config_group)
        layout.addWidget(deploy_group)
        layout.addStretch()
        return tab

    def _build_tab_phones(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(14)

        # Input Fields Group
        input_group = QGroupBox("Ajouter un téléphone")
        input_layout = QHBoxLayout(input_group)
        input_layout.setSpacing(8)
        self.edt_mac = QLineEdit()
        self.edt_mac.setPlaceholderText("MAC (scan code-barres supporté)")
        self.edt_mac.setMaxLength(17)
        self.edt_mac.textChanged.connect(self._on_mac_input_changed)
        self.edt_ext = QLineEdit()
        self.edt_ext.setPlaceholderText("Extension")
        self.edt_phone_pwd = QLineEdit()
        self.edt_phone_pwd.setPlaceholderText("Mot de passe")
        self.edt_phone_pwd.setEchoMode(QLineEdit.EchoMode.Password)
        self.edt_phone_ip = QLineEdit()
        self.edt_phone_ip.setPlaceholderText("IP du téléphone")
        self.cmb_timezone = QComboBox()
        self.cmb_timezone.addItems(SUPPORTED_TIMEZONES)
        self.cmb_timezone.setCurrentText(DEFAULT_TIMEZONE)
        self.cmb_timezone.setToolTip(TIMEZONE_TOOLTIP)

        self.edt_mac.returnPressed.connect(self._scanner_submit_if_ready)
        self.edt_ext.returnPressed.connect(self.add_phone_row)
        self.edt_phone_pwd.returnPressed.connect(self.add_phone_row)
        
        self.btn_add = QPushButton("Ajouter")
        self.btn_add.clicked.connect(self.add_phone_row)
        
        input_layout.addWidget(self.edt_mac, 2)
        input_layout.addWidget(self.edt_ext, 1)
        input_layout.addWidget(self.edt_phone_pwd, 1)
        input_layout.addWidget(self.edt_phone_ip, 1)
        input_layout.addWidget(self.cmb_timezone, 1)
        input_layout.addWidget(self.btn_add)

        self.tbl_phones = QTableWidget(0, 6)
        self.tbl_phones.setHorizontalHeaderLabels(
            ["MAC", "Extension", "Mot de passe", "IP", "Timezone", "Status"]
        )
        self.tbl_phones.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl_phones.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_phones.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tbl_phones.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tbl_phones.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.tbl_phones.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_phones.verticalHeader().setVisible(False)
        self.tbl_phones.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_phones.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.tbl_phones.setAlternatingRowColors(True)
        self.tbl_phones.setShowGrid(False)
        self.tbl_phones.setEditTriggers(
            QTableWidget.EditTrigger.DoubleClicked | QTableWidget.EditTrigger.SelectedClicked
        )
        self.tbl_phones.setMinimumHeight(220)
        self.tbl_phones.itemChanged.connect(self._on_phone_item_changed)
        self.tbl_phones.itemSelectionChanged.connect(self._on_phone_selection_changed)

        # Create buttons and groups
        self.btn_remove = QPushButton("Supprimer")
        self.btn_remove.clicked.connect(self.remove_selected_rows)
        self.btn_import_csv = QPushButton("Importer CSV")
        self.btn_import_csv.clicked.connect(self.import_csv)
        self.btn_generate_range = QPushButton("Générer extensions (plage)")
        self.btn_generate_range.clicked.connect(self.generate_extension_range)
        self.btn_scan_network = QPushButton("Scanner réseau")
        self.btn_scan_network.clicked.connect(self.scan_network_phones)
        self.btn_resync_phones = QPushButton("Resync sélectionnés")
        self.btn_resync_phones.clicked.connect(self.resync_selected_phones)
        self.btn_reboot_phones = QPushButton("Reboot sélectionnés")
        self.btn_reboot_phones.clicked.connect(self.reboot_selected_phones)
        self.edt_scan_subnet = QLineEdit()
        self.edt_scan_subnet.setPlaceholderText("Sous-réseau (ex: 192.168.1)")
        self.cmb_global_timezone = QComboBox()
        self.cmb_global_timezone.addItems(SUPPORTED_TIMEZONES)
        self.cmb_global_timezone.setCurrentText(DEFAULT_TIMEZONE)
        self.cmb_global_timezone.setToolTip(TIMEZONE_TOOLTIP)
        self.btn_apply_global_timezone = QPushButton("Appliquer timezone")
        self.btn_apply_global_timezone.clicked.connect(self.apply_global_timezone)
        
        # Data Management Group
        data_group = QGroupBox("Gestion des données")
        data_layout = QHBoxLayout(data_group)
        data_layout.setSpacing(8)
        data_layout.addWidget(self.btn_import_csv)
        data_layout.addWidget(self.btn_generate_range)
        data_layout.addWidget(self.btn_remove)
        data_layout.addStretch()
        
        # Network Scan Group
        scan_group = QGroupBox("Scan réseau")
        scan_layout = QHBoxLayout(scan_group)
        scan_layout.setSpacing(8)
        scan_layout.addWidget(self.edt_scan_subnet)
        scan_layout.addWidget(self.btn_scan_network)
        scan_layout.addStretch()
        
        # Settings Group
        settings_group = QGroupBox("Paramètres globaux")
        settings_layout = QHBoxLayout(settings_group)
        settings_layout.setSpacing(8)
        settings_layout.addWidget(QLabel("Timezone:"))
        settings_layout.addWidget(self.cmb_global_timezone)
        settings_layout.addWidget(self.btn_apply_global_timezone)
        settings_layout.addStretch()
        
        # Actions Group
        actions_group = QGroupBox("Actions téléphones")
        actions_layout = QHBoxLayout(actions_group)
        actions_layout.setSpacing(8)
        actions_layout.addWidget(self.btn_deployer)
        actions_layout.addWidget(self.btn_resync_phones)
        actions_layout.addWidget(self.btn_reboot_phones)
        actions_layout.addStretch()

        self.scan_progress_label = QLabel("Scan réseau inactif.")
        self.scan_progress = QProgressBar()
        self.scan_progress.setRange(0, 100)
        self.scan_progress.setValue(0)
        self.scan_progress.hide()
        self.reboot_progress_label = QLabel("Reboot SIP inactif.")
        self.reboot_progress = QProgressBar()
        self.reboot_progress.setRange(0, 100)
        self.reboot_progress.setValue(0)
        self.reboot_progress.hide()
        self.lbl_selected_count = QLabel("0 téléphone sélectionné.")
        self.chk_deploy_selected = QCheckBox("Déployer uniquement les téléphones sélectionnés")
        self.chk_auto_reboot = QCheckBox("Reboot automatique après déploiement")
        self.chk_auto_reboot.setChecked(True)
        self.btn_clear_except_db = QPushButton("Tout effacer sauf téléphones")
        self.btn_clear_except_db.clicked.connect(self.clear_except_phone_db)
        self.btn_clear_all = QPushButton("Tout effacer")
        self.btn_clear_all.clicked.connect(self.clear_everything)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        left_layout.addWidget(input_group)
        left_layout.addWidget(self.tbl_phones, 1)
        footer = QHBoxLayout()
        footer.addWidget(self.lbl_selected_count)
        footer.addStretch()
        footer.addWidget(self.chk_deploy_selected)
        footer.addWidget(self.chk_auto_reboot)
        left_layout.addLayout(footer)
        left_layout.addWidget(self.scan_progress_label)
        left_layout.addWidget(self.scan_progress)
        left_layout.addWidget(self.reboot_progress_label)
        left_layout.addWidget(self.reboot_progress)
        
        # Add action groups
        left_layout.addWidget(data_group)
        left_layout.addWidget(scan_group)
        left_layout.addWidget(settings_group)
        left_layout.addWidget(actions_group)
        
        advanced_actions = QHBoxLayout()
        advanced_actions.addStretch()
        advanced_actions.addWidget(self.btn_clear_except_db)
        advanced_actions.addWidget(self.btn_clear_all)
        left_layout.addLayout(advanced_actions)

        side_card = QGroupBox("Détails sélection")
        side_layout = QFormLayout(side_card)
        self.sel_mac = QLineEdit()
        self.sel_ext = QLineEdit()
        self.sel_pwd = QLineEdit()
        self.sel_ip = QLineEdit()
        self.sel_tz = QComboBox()
        self.sel_tz.addItems(SUPPORTED_TIMEZONES)
        self.sel_reboot = QPushButton("Reboot téléphone")
        self.sel_reboot.clicked.connect(self._reboot_single_selected)
        self.sel_resync = QPushButton("Resync téléphone")
        self.sel_resync.clicked.connect(self._resync_single_selected)
        self.sel_apply = QPushButton("Appliquer modifications")
        self.sel_apply.clicked.connect(self._apply_selected_edit)
        side_layout.addRow("MAC", self.sel_mac)
        side_layout.addRow("Extension", self.sel_ext)
        side_layout.addRow("Mot de passe", self.sel_pwd)
        side_layout.addRow("IP", self.sel_ip)
        side_layout.addRow("Timezone", self.sel_tz)
        side_layout.addRow(self.sel_apply)
        side_layout.addRow(self.sel_resync)
        side_layout.addRow(self.sel_reboot)

        splitter = QSplitter()
        splitter.addWidget(left)
        splitter.addWidget(side_card)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)
        return tab

    def _build_tab_logs(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        actions = QHBoxLayout()
        self.btn_clear_logs = QPushButton("Clear logs")
        self.btn_export_logs = QPushButton("Export logs")
        self.btn_clear_logs.clicked.connect(lambda: self.txt_logs.clear())
        self.btn_export_logs.clicked.connect(self._export_logs)
        actions.addStretch()
        actions.addWidget(self.btn_clear_logs)
        actions.addWidget(self.btn_export_logs)
        layout.addLayout(actions)
        self.txt_logs = QTextEdit()
        self.txt_logs.setReadOnly(True)
        self.txt_logs.setFont(QFont("Consolas", 10))
        layout.addWidget(self.txt_logs)
        return tab

    def _build_tab_database(self) -> QWidget:
        """Dedicated DB tab to manage phones and inspect deployment events."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(12)

        header = QLabel(
            "Base SQLite centralisée: gérez les téléphones enregistrés et consultez l'historique de génération/déploiement."
        )
        header.setWordWrap(True)
        layout.addWidget(header)

        phones_group = QGroupBox("Téléphones enregistrés (CRUD)")
        phones_layout = QVBoxLayout(phones_group)
        actions = QHBoxLayout()
        self.btn_db_refresh = QPushButton("Rafraîchir")
        self.btn_db_refresh.clicked.connect(self._refresh_db_tab)
        self.btn_db_add = QPushButton("Ajouter ligne")
        self.btn_db_add.clicked.connect(self._db_add_phone_row)
        self.btn_db_delete = QPushButton("Supprimer sélection")
        self.btn_db_delete.clicked.connect(self._db_delete_selected_phones)
        self.btn_db_save = QPushButton("Enregistrer modifications")
        self.btn_db_save.clicked.connect(self._db_save_phones)
        actions.addWidget(self.btn_db_refresh)
        actions.addWidget(self.btn_db_add)
        actions.addWidget(self.btn_db_delete)
        actions.addStretch()
        actions.addWidget(self.btn_db_save)
        phones_layout.addLayout(actions)

        self.tbl_db_phones = QTableWidget(0, 6)
        self.tbl_db_phones.setHorizontalHeaderLabels(["MAC", "Extension", "Mot de passe", "IP", "Timezone", "Statut"])
        self.tbl_db_phones.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tbl_db_phones.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_db_phones.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tbl_db_phones.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tbl_db_phones.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.tbl_db_phones.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_db_phones.verticalHeader().setVisible(False)
        self.tbl_db_phones.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_db_phones.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.tbl_db_phones.setAlternatingRowColors(True)
        self.tbl_db_phones.setMinimumHeight(170)
        phones_layout.addWidget(self.tbl_db_phones)

        deploy_group = QGroupBox("Historique génération / déploiement")
        deploy_layout = QVBoxLayout(deploy_group)
        self.tbl_db_events = QTableWidget(0, 3)
        self.tbl_db_events.setHorizontalHeaderLabels(["Horodatage", "Niveau", "Message"])
        self.tbl_db_events.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_db_events.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_db_events.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tbl_db_events.verticalHeader().setVisible(False)
        self.tbl_db_events.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl_db_events.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tbl_db_events.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_db_events.setAlternatingRowColors(True)
        self.tbl_db_events.setMinimumHeight(140)
        deploy_layout.addWidget(self.tbl_db_events)

        layout.addWidget(phones_group)
        layout.addWidget(deploy_group)
        self._refresh_db_tab()
        return tab

    def _refresh_db_tab(self) -> None:
        if not hasattr(self, "tbl_db_phones"):
            return
        self._db_reload_phones()
        self._db_reload_events()

    def _db_reload_phones(self) -> None:
        self.tbl_db_phones.setRowCount(0)
        rows = self.db.cursor().execute(
            "SELECT mac, ext, password, ip, timezone FROM phones ORDER BY ext, mac"
        ).fetchall()
        for mac, ext, pwd, ip, timezone in rows:
            row = self.tbl_db_phones.rowCount()
            self.tbl_db_phones.insertRow(row)
            self.tbl_db_phones.setItem(row, 0, QTableWidgetItem(format_mac_display(mac or "")))
            self.tbl_db_phones.setItem(row, 1, QTableWidgetItem(ext or ""))
            self.tbl_db_phones.setItem(row, 2, QTableWidgetItem(pwd or ""))
            self.tbl_db_phones.setItem(row, 3, QTableWidgetItem(ip or ""))
            self.tbl_db_phones.setItem(row, 4, QTableWidgetItem(timezone or DEFAULT_TIMEZONE))
            self.tbl_db_phones.setItem(row, 5, QTableWidgetItem("En base"))

    def _db_reload_events(self) -> None:
        self.tbl_db_events.setRowCount(0)
        rows = self.db.cursor().execute(
            """
            SELECT timestamp, level, message
            FROM logs
            WHERE level IN ('DEPLOIEMENT', 'XML', 'SFTP', 'SSH', 'REBOOT', 'ERREUR', 'SUCCES')
               OR message LIKE '%déploiement%'
               OR message LIKE '%fichier XML%'
               OR message LIKE '%upload%'
            ORDER BY id DESC
            LIMIT 250
            """
        ).fetchall()
        for ts, level, message in rows:
            row = self.tbl_db_events.rowCount()
            self.tbl_db_events.insertRow(row)
            self.tbl_db_events.setItem(row, 0, QTableWidgetItem(str(ts)))
            self.tbl_db_events.setItem(row, 1, QTableWidgetItem(str(level)))
            self.tbl_db_events.setItem(row, 2, QTableWidgetItem(str(message)))

    def _db_add_phone_row(self) -> None:
        row = self.tbl_db_phones.rowCount()
        self.tbl_db_phones.insertRow(row)
        self.tbl_db_phones.setItem(row, 0, QTableWidgetItem(""))
        self.tbl_db_phones.setItem(row, 1, QTableWidgetItem(""))
        self.tbl_db_phones.setItem(row, 2, QTableWidgetItem(""))
        self.tbl_db_phones.setItem(row, 3, QTableWidgetItem(""))
        self.tbl_db_phones.setItem(row, 4, QTableWidgetItem(DEFAULT_TIMEZONE))
        self.tbl_db_phones.setItem(row, 5, QTableWidgetItem("Nouveau"))

    def _db_delete_selected_phones(self) -> None:
        rows = sorted({idx.row() for idx in self.tbl_db_phones.selectionModel().selectedRows()}, reverse=True)
        if not rows:
            self._show_error("Sélectionnez au moins une ligne DB à supprimer.")
            return
        for row in rows:
            self.tbl_db_phones.removeRow(row)
        self._db_save_phones()

    def _db_save_phones(self) -> None:
        phones: list[tuple[str, str, str, str, str]] = []
        seen: set[str] = set()
        for row in range(self.tbl_db_phones.rowCount()):
            mac_text = self.tbl_db_phones.item(row, 0).text().strip() if self.tbl_db_phones.item(row, 0) else ""
            ext = self.tbl_db_phones.item(row, 1).text().strip() if self.tbl_db_phones.item(row, 1) else ""
            pwd = self.tbl_db_phones.item(row, 2).text().strip() if self.tbl_db_phones.item(row, 2) else ""
            ip = self.tbl_db_phones.item(row, 3).text().strip() if self.tbl_db_phones.item(row, 3) else ""
            timezone = (
                self.tbl_db_phones.item(row, 4).text().strip() if self.tbl_db_phones.item(row, 4) else DEFAULT_TIMEZONE
            )
            if not mac_text and not ext and not pwd:
                continue
            mac = normalize_mac(mac_text)
            if not is_valid_mac(mac):
                self._show_error(f"MAC invalide en ligne {row + 1}.")
                return
            if not ext:
                self._show_error(f"Extension manquante en ligne {row + 1}.")
                return
            if not pwd:
                self._show_error(f"Mot de passe manquant en ligne {row + 1}.")
                return
            if mac in seen:
                self._show_error(f"MAC dupliquée en ligne {row + 1}.")
                return
            seen.add(mac)
            phones.append((mac, ext, pwd, ip, timezone or DEFAULT_TIMEZONE))

        cur = self.db.cursor()
        cur.execute("DELETE FROM phones")
        if phones:
            cur.executemany(
                "INSERT INTO phones (mac, ext, password, ip, timezone) VALUES (?, ?, ?, ?, ?)",
                phones,
            )
        self.db.commit()
        self._show_success(f"DB mise à jour: {len(phones)} téléphone(s).")
        self._log("INFO", f"DB tab: {len(phones)} téléphone(s) enregistré(s).")
        self._reload_phone_table_from_db()
        self._refresh_db_tab()

    def _apply_style(self) -> None:
        """Apply theme stylesheet to all widgets."""
        stylesheet = self.theme_manager.get_stylesheet()
        # Add base font styling
        base_style = """
            * { font-size: 13px; font-family: "Segoe UI"; }
        """
        self.setStyleSheet(base_style + stylesheet)

    def switch_theme(self, theme: Theme) -> None:
        """Switch application theme and refresh UI."""
        self.theme_manager.switch_theme(theme)
        self._apply_style()

    def _set_connected_ui(self, connected: bool) -> None:
        self._connected_state = connected
        color = self.theme_manager.get_color("success") if connected else self.theme_manager.get_color("error")
        text = "Connecté" if connected else "Non connecté"
        self.lbl_status_dot.setStyleSheet(f"color: {color};")
        self.lbl_status_text.setText(text)

        self._refresh_connection_dependent_ui()

    def _refresh_connection_dependent_ui(self) -> None:
        """Force l'UI à refléter l'état de connexion courant."""
        connected = self._connected_state and self.ssh_available

        for button in [
            getattr(self, "btn_test_connect", None),
            getattr(self, "btn_connect", None),
            getattr(self, "btn_disconnect", None),
            getattr(self, "btn_install_tftp", None),
            getattr(self, "btn_check_tftp", None),
            getattr(self, "btn_restart_tftp", None),
            getattr(self, "btn_deployer", None),
            getattr(self, "btn_reboot_phones", None),
            getattr(self, "btn_resync_phones", None),
            getattr(self, "sel_reboot", None),
            getattr(self, "sel_resync", None),
        ]:
            if button is not None:
                button.setEnabled(connected if button == getattr(self, "btn_disconnect", None) else self.ssh_available and (connected or button in [getattr(self, "btn_test_connect", None), getattr(self, "btn_connect", None)]))

        # Le scan réseau ouvre sa propre session SSH; il requiert seulement des identifiants saisis.
        if getattr(self, "btn_scan_network", None) is not None and not (
            self.scan_thread and self.scan_thread.isRunning()
        ):
            self.btn_scan_network.setEnabled(self.ssh_available)

        if getattr(self, "btn_reboot_phones", None) is not None and not (
            self.reboot_thread and self.reboot_thread.isRunning()
        ):
            self.btn_reboot_phones.setEnabled(connected)

        if not self.ssh_available:
            warning_color = self.theme_manager.get_color("warning")
            self.lbl_status_dot.setStyleSheet(f"color: {warning_color};")
            self.lbl_status_text.setText("SSH client manquant (mode limité)")

    def _set_busy(self, busy: bool, message: str = "Action SSH en cours...") -> None:
        self._is_busy = busy
        self.progress_label.setText(message)
        self.progress_label.setVisible(busy)
        self.progress.setVisible(busy)
        QApplication.processEvents()

    def _set_scan_progress(self, value: int, text: str, active: bool = True) -> None:
        self.scan_progress_label.setText(text)
        self.scan_progress.setVisible(active)
        self.scan_progress.setValue(max(0, min(100, value)))
        QApplication.processEvents()

    def _set_reboot_progress(self, value: int, text: str, active: bool = True) -> None:
        self.reboot_progress_label.setText(text)
        self.reboot_progress.setVisible(active)
        self.reboot_progress.setValue(max(0, min(100, value)))
        QApplication.processEvents()

    def _set_server_progress(self, value: int, text: str, active: bool = True) -> None:
        self.server_progress_label.setText(text)
        self.server_progress.setVisible(active)
        self.server_progress.setValue(max(0, min(100, value)))
        QApplication.processEvents()

    def _is_valid_ipv4(self, ip_value: str) -> bool:
        """Valide un format IPv4 simple."""
        value = ip_value.strip()
        parts = value.split(".")
        if len(parts) != 4:
            return False
        for part in parts:
            if not part.isdigit():
                return False
            num = int(part)
            if num < 0 or num > 255:
                return False
        return True

    def _set_ntp_status(self, ok: bool) -> None:
        if ok:
            self.lbl_ntp_status.setText("NTP: OK")
            success_color = self.theme_manager.get_color("success")
            self.lbl_ntp_status.setStyleSheet(f"color: {success_color}; font-weight: 700;")
        else:
            self.lbl_ntp_status.setText("NTP: KO")
            error_color = self.theme_manager.get_color("error")
            self.lbl_ntp_status.setStyleSheet(f"color: {error_color}; font-weight: 700;")

    def _on_sync_checkbox_toggled(self, checked: bool) -> None:
        # Si activé, NTP suit UC en permanence.
        if checked:
            self.sync_ntp_with_uc()

    def sync_ntp_with_uc(self) -> None:
        """
        Sync UC -> NTP:
        - si checkbox cochée: force NTP=UC
        - sinon: auto-fill seulement si NTP est vide ou identique à la dernière UC
        """
        uc_ip = self.edt_uc_ip.text().strip()
        if self.sync_checkbox.isChecked():
            # Prevent unnecessary churn
            if self.edt_ntp_ip.text().strip() != uc_ip:
                self.edt_ntp_ip.setText(uc_ip)
        else:
            current_ntp = self.edt_ntp_ip.text().strip()
            if not current_ntp or current_ntp == getattr(self, "last_uc_ip", ""):
                self.edt_ntp_ip.setText(uc_ip)
        self.last_uc_ip = uc_ip

    def test_ntp_server(self) -> None:
        ntp_ip = self.edt_ntp_ip.text().strip()
        if not self._is_valid_ipv4(ntp_ip):
            self._show_error("IP NTP invalide (format IPv4 requis).")
            return
        if self.ntp_thread and self.ntp_thread.isRunning():
            self._show_error("Un test NTP est déjà en cours.")
            return
        self._log("NTP", f"Test NTP vers {ntp_ip}")
        self.btn_test_ntp.setEnabled(False)
        self.ntp_thread = QThread(self)
        self.ntp_worker = NtpTestWorker(ntp_ip)
        self.ntp_worker.moveToThread(self.ntp_thread)
        self.ntp_thread.started.connect(self.ntp_worker.run)
        self.ntp_worker.finished.connect(self._on_ntp_test_finished)
        self.ntp_worker.finished.connect(self.ntp_thread.quit)
        self.ntp_thread.finished.connect(self._cleanup_ntp_thread)
        self.ntp_thread.start()

    def _on_ntp_test_finished(self, ok: bool, ip: str) -> None:
        self._set_ntp_status(ok)
        self._log("NTP", f"Résultat test NTP {ip}: {'OK' if ok else 'KO'}")
        if ok:
            self._show_success("Serveur NTP valide")
        else:
            answer = QMessageBox.question(
                self,
                "NTP non accessible",
                "Serveur NTP non accessible.\nUtiliser le serveur TFTP comme NTP ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if answer == QMessageBox.StandardButton.Yes:
                fallback_ip = self.edt_host.text().strip()
                if self._is_valid_ipv4(fallback_ip):
                    self.edt_ntp_ip.setText(fallback_ip)
                    self._log("NTP", f"Fallback NTP appliqué: {fallback_ip}")
                else:
                    self._show_error("Fallback impossible: IP serveur invalide.")
            self._show_error("Serveur NTP non accessible")

    def _cleanup_ntp_thread(self) -> None:
        self.btn_test_ntp.setEnabled(True)
        if self.ntp_worker:
            self.ntp_worker.deleteLater()
        if self.ntp_thread:
            self.ntp_thread.deleteLater()
        self.ntp_worker = None
        self.ntp_thread = None

    def _log(self, level: str, message: str) -> None:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        color = {"ERREUR": "#ef4444", "SUCCES": "#10b981", "INFO": "#e2e8f0"}.get(level, "#cbd5e1")
        line = f"[{ts}] [{level}] {message}"
        self.txt_logs.append(f'<span style="color:{color}">{line}</span>')
        self.txt_logs.verticalScrollBar().setValue(self.txt_logs.verticalScrollBar().maximum())
        # File log
        try:
            py_level = {"ERREUR": logging.ERROR, "SUCCES": logging.INFO, "INFO": logging.INFO}.get(level, logging.INFO)
            logging.log(py_level, message)
        except Exception:
            pass
        self.db.execute(
            "INSERT INTO logs (timestamp, level, message) VALUES (?, ?, ?)",
            (ts, level, message),
        )
        self.db.commit()

    def _export_logs(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(self, "Exporter logs", "", "Text (*.txt)")
        if not file_path:
            return
        with open(file_path, "w", encoding="utf-8") as handle:
            handle.write(self.txt_logs.toPlainText())
        self._show_success("Logs exportés.")

    def _show_error(self, message: str) -> None:
        self._log("ERREUR", message)
        QMessageBox.critical(self, "Erreur", message)

    def _show_success(self, message: str) -> None:
        self._log("SUCCES", message)
        QMessageBox.information(self, "Succès", message)

    def _on_mac_input_changed(self, text: str) -> None:
        formatted = format_mac_display(text)
        if text != formatted:
            cursor_pos = self.edt_mac.cursorPosition()
            self.edt_mac.blockSignals(True)
            self.edt_mac.setText(formatted)
            self.edt_mac.setCursorPosition(min(len(formatted), cursor_pos + 1))
            self.edt_mac.blockSignals(False)

    def _scanner_submit_if_ready(self) -> None:
        if self.edt_ext.text().strip() and self.edt_phone_pwd.text().strip():
            self.add_phone_row()
        else:
            self.edt_ext.setFocus()

    def _connection_params(self) -> Dict[str, str | int]:
        return {
            "host": self.edt_host.text().strip(),
            "port": int(self.spn_port.value()),
            "username": self.edt_user.text().strip(),
            "password": self.edt_password.text(),
        }

    def _require_connection(self) -> bool:
        if not self._require_ssh_client():
            return False
        if not self.ssh.is_connected:
            self._show_error("Connectez-vous d'abord au serveur SSH.")
            return False
        return True

    def _require_ssh_client(self) -> bool:
        if self.ssh_available:
            return True
        self._show_error("Client SSH non disponible sur ce système. Fonctions SSH désactivées.")
        return False

    def _save_all_phones_to_db(self) -> None:
        phones = self._collect_phones()
        cur = self.db.cursor()
        cur.execute("DELETE FROM phones")
        cur.executemany(
            "INSERT INTO phones (mac, ext, password, ip, timezone) VALUES (?, ?, ?, ?, ?)",
            [(p["mac"], p["ext"], p["password"], p["ip"], p["timezone"]) for p in phones],
        )
        self.db.commit()
        self._refresh_db_tab()

    def _load_phones_from_db(self) -> None:
        self.tbl_phones.setRowCount(0)
        cur = self.db.cursor()
        rows = cur.execute("SELECT mac, ext, password, ip, timezone FROM phones ORDER BY ext").fetchall()
        for mac, ext, pwd, ip, timezone in rows:
            self._append_phone_row(mac, ext, pwd, ip or "", timezone or DEFAULT_TIMEZONE)
        if rows:
            self._log("INFO", f"{len(rows)} téléphones chargés depuis SQLite.")
        self._refresh_saved_history()
        self._refresh_db_tab()

    def _reload_phone_table_from_db(self) -> None:
        """Reload the Phones tab from DB after CRUD in DB tab."""
        self._load_phones_from_db()

    def _append_phone_row(self, mac: str, ext: str, password: str, ip: str, timezone: str) -> None:
        self._suspend_table_events = True
        row = self.tbl_phones.rowCount()
        self.tbl_phones.insertRow(row)
        self.tbl_phones.setItem(row, COL_MAC, QTableWidgetItem(format_mac_display(mac)))
        self.tbl_phones.setItem(row, COL_EXT, QTableWidgetItem(ext))
        self.tbl_phones.setItem(row, COL_PWD, QTableWidgetItem(password))
        self.tbl_phones.setItem(row, COL_IP, QTableWidgetItem(ip.strip()))
        self.tbl_phones.setItem(row, COL_TZ, QTableWidgetItem(timezone or DEFAULT_TIMEZONE))
        self._suspend_table_events = False
        self._apply_timezone_highlight(row)
        self._set_phone_status(row, "En attente")

    def _apply_selected_edit(self) -> None:
        rows = sorted({idx.row() for idx in self.tbl_phones.selectionModel().selectedRows()})
        if len(rows) != 1:
            self._show_error("Sélectionnez une seule ligne pour modifier les détails.")
            return
        row = rows[0]
        self._suspend_table_events = True
        self.tbl_phones.setItem(row, COL_MAC, QTableWidgetItem(format_mac_display(self.sel_mac.text())))
        self.tbl_phones.setItem(row, COL_EXT, QTableWidgetItem(self.sel_ext.text().strip()))
        self.tbl_phones.setItem(row, COL_PWD, QTableWidgetItem(self.sel_pwd.text().strip()))
        self.tbl_phones.setItem(row, COL_IP, QTableWidgetItem(self.sel_ip.text().strip()))
        self.tbl_phones.setItem(row, COL_TZ, QTableWidgetItem(self.sel_tz.currentText()))
        self._suspend_table_events = False
        self._apply_timezone_highlight(row)
        self._set_phone_status(row, "En attente")
        self._save_all_phones_to_db()
        self._show_success("Modifications appliquées.")

    def _reboot_single_selected(self) -> None:
        rows = sorted({idx.row() for idx in self.tbl_phones.selectionModel().selectedRows()})
        if len(rows) != 1:
            self._show_error("Sélectionnez un seul téléphone.")
            return
        phone = self._collect_selected_phones()
        if phone:
            self._start_sip_notify_worker(phone, mode="reboot")

    def _resync_single_selected(self) -> None:
        rows = sorted({idx.row() for idx in self.tbl_phones.selectionModel().selectedRows()})
        if len(rows) != 1:
            self._show_error("Sélectionnez un seul téléphone.")
            return
        phone = self._collect_selected_phones()
        if phone:
            self._start_sip_notify_worker(phone, mode="check-sync")

    def _on_phone_item_changed(self, item: QTableWidgetItem) -> None:
        if self._suspend_table_events:
            return
        if item.column() == COL_MAC:
            mac = normalize_mac(item.text())
            if not is_valid_mac(mac):
                self._show_error("MAC invalide après modification.")
                return
            self._suspend_table_events = True
            item.setText(format_mac_display(mac))
            self._suspend_table_events = False
        if item.column() == COL_IP:
            ip = item.text().strip()
            if ip and not self._is_valid_ipv4(ip):
                self._show_error("IP téléphone invalide (format IPv4 requis).")
                return
        if item.column() == COL_TZ:
            tz = item.text().strip() or DEFAULT_TIMEZONE
            self._suspend_table_events = True
            item.setText(tz)
            self._suspend_table_events = False
        if item.column() != COL_STATUS:
            self._set_phone_status(item.row(), "En attente")
        self._apply_timezone_highlight(item.row())
        self._save_all_phones_to_db()
        self._refresh_saved_history()

    def _apply_timezone_highlight(self, row: int) -> None:
        timezone_item = self.tbl_phones.item(row, COL_TZ)
        timezone_value = timezone_item.text().strip() if timezone_item else DEFAULT_TIMEZONE
        is_non_default = timezone_value != DEFAULT_TIMEZONE
        bg = QColor("#7c2d12") if is_non_default else QColor("#1f2937")
        for col in range(self.tbl_phones.columnCount()):
            cell = self.tbl_phones.item(row, col)
            if cell:
                cell.setBackground(bg)
                cell.setToolTip(TIMEZONE_TOOLTIP if is_non_default else "")

    def _set_phone_status(self, row: int, status: str) -> None:
        """Set phone status with enhanced color coding based on theme."""
        if row < 0 or row >= self.tbl_phones.rowCount():
            return
        
        self._suspend_table_events = True
        status_item = QTableWidgetItem(status)
        
        # Apply theme-based colors
        if status in ["Déployé", "OK", "Succès"]:
            bg_color = self.theme_manager.get_color("success")
            text_color = "#ffffff"
            tooltip = "Téléphone configuré avec succès"
        elif status in ["Erreur", "Échec", "KO"]:
            bg_color = self.theme_manager.get_color("error")
            text_color = "#ffffff"
            tooltip = "Configuration échouée"
        elif status in ["En cours", "Pendant", "Processing"]:
            bg_color = self.theme_manager.get_color("warning")
            text_color = "#000000"
            tooltip = "Configuration en cours..."
        else:  # "En attente"
            bg_color = self.theme_manager.get_color("text_secondary")
            text_color = "#ffffff"
            tooltip = "En attente de déploiement"
        
        status_item.setBackground(QColor(bg_color))
        status_item.setForeground(QColor(text_color))
        status_item.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        status_item.setToolTip(tooltip)
        status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.tbl_phones.setItem(row, COL_STATUS, status_item)
        self._suspend_table_events = False

    def _on_phone_selection_changed(self) -> None:
        rows = sorted({idx.row() for idx in self.tbl_phones.selectionModel().selectedRows()})
        self.lbl_selected_count.setText(f"{len(rows)} téléphone(s) sélectionné(s).")
        if len(rows) == 1:
            row = rows[0]
            self.sel_mac.setText(self.tbl_phones.item(row, COL_MAC).text() if self.tbl_phones.item(row, COL_MAC) else "")
            self.sel_ext.setText(self.tbl_phones.item(row, COL_EXT).text() if self.tbl_phones.item(row, COL_EXT) else "")
            self.sel_pwd.setText(self.tbl_phones.item(row, COL_PWD).text() if self.tbl_phones.item(row, COL_PWD) else "")
            self.sel_ip.setText(self.tbl_phones.item(row, COL_IP).text() if self.tbl_phones.item(row, COL_IP) else "")
            self.sel_tz.setCurrentText(
                self.tbl_phones.item(row, COL_TZ).text() if self.tbl_phones.item(row, COL_TZ) else DEFAULT_TIMEZONE
            )
        else:
            self.sel_mac.clear()
            self.sel_ext.clear()
            self.sel_pwd.clear()
            self.sel_ip.clear()

    def apply_global_timezone(self) -> None:
        timezone = self.cmb_global_timezone.currentText().strip() or DEFAULT_TIMEZONE
        selected_rows = sorted({idx.row() for idx in self.tbl_phones.selectionModel().selectedRows()})
        target_rows = selected_rows if selected_rows else list(range(self.tbl_phones.rowCount()))
        if not target_rows:
            self._show_error("Aucun téléphone disponible pour appliquer la timezone.")
            return

        self._suspend_table_events = True
        for row in target_rows:
            self.tbl_phones.setItem(row, 4, QTableWidgetItem(timezone))
            self._apply_timezone_highlight(row)
        self._suspend_table_events = False
        self._save_all_phones_to_db()
        self._refresh_saved_history()
        scope = "sélectionnés" if selected_rows else "tous"
        self._show_success(f"Timezone appliquée aux téléphones {scope}.")

    def _refresh_saved_history(self) -> None:
        # Conservé pour compatibilité logique, sans panneau historique visible.
        return

    def _clear_runtime_ui(self) -> None:
        self.edt_mac.clear()
        self.edt_ext.clear()
        self.edt_phone_pwd.clear()
        self.edt_phone_ip.clear()
        self.edt_scan_subnet.clear()
        self.cmb_timezone.setCurrentText(DEFAULT_TIMEZONE)
        self.cmb_global_timezone.setCurrentText(DEFAULT_TIMEZONE)
        self.chk_deploy_selected.setChecked(False)
        self.lbl_selected_count.setText("0 téléphone sélectionné.")
        self.sel_mac.clear()
        self.sel_ext.clear()
        self.sel_pwd.clear()
        self.sel_ip.clear()
        self.scan_progress_label.setText("Scan réseau inactif.")
        self.scan_progress.setValue(0)
        self.scan_progress.hide()
        self.reboot_progress_label.setText("Reboot SIP inactif.")
        self.reboot_progress.setValue(0)
        self.reboot_progress.hide()
        self.progress_label.hide()
        self.progress.hide()

    def clear_everything(self) -> None:
        answer = QMessageBox.question(
            self,
            "Confirmation",
            "Voulez-vous vraiment tout effacer (téléphones + logs + écran) ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.tbl_phones.setRowCount(0)
        self.txt_logs.clear()
        self._clear_runtime_ui()
        cur = self.db.cursor()
        cur.execute("DELETE FROM phones")
        cur.execute("DELETE FROM logs")
        self.db.commit()
        self._refresh_saved_history()
        self._show_success("Tout a été effacé avec succès.")

    def clear_except_phone_db(self) -> None:
        answer = QMessageBox.question(
            self,
            "Confirmation",
            "Effacer l'écran et les logs, mais conserver la base téléphones ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return

        self.tbl_phones.setRowCount(0)
        self.txt_logs.clear()
        self._clear_runtime_ui()
        cur = self.db.cursor()
        cur.execute("DELETE FROM logs")
        self.db.commit()
        self._refresh_saved_history()
        self._show_success("Nettoyage effectué. Base téléphones conservée.")

    def test_ssh_connection(self) -> None:
        if not self._require_ssh_client():
            return
        params = self._connection_params()
        if not params["host"] or not params["username"] or not params["password"]:
            self._show_error("Renseignez IP, utilisateur et mot de passe.")
            return
        self._set_busy(True, "Test de connexion SSH...")
        ok, msg = self.ssh.test_connection(**params)
        self._log("SSH", msg)
        if ok:
            # Le test est valide: on ouvre ensuite une vraie session persistante
            # pour synchroniser l'etat UI (pastille verte + connecte).
            connected, connect_msg = self.ssh.connect(**params)
            self._log("SSH", connect_msg)
            self._set_connected_ui(connected)
            self._refresh_connection_dependent_ui()
            self._set_busy(False)
            if connected:
                self._show_success("Connexion testée et session SSH établie.")
            else:
                self._show_error(connect_msg)
        else:
            self._set_connected_ui(False)
            self._set_busy(False)
            self._show_error(msg)

    def connect_ssh(self) -> None:
        if not self._require_ssh_client():
            return
        params = self._connection_params()
        if not params["host"] or not params["username"] or not params["password"]:
            self._show_error("Renseignez IP, utilisateur et mot de passe.")
            return
        self._set_busy(True, "Connexion SSH...")
        ok, msg = self.ssh.connect(**params)
        self._set_busy(False)
        self._log("SSH", msg)
        self._set_connected_ui(ok)
        # Ensure buttons refresh immediately on success.
        self._refresh_connection_dependent_ui()
        if ok:
            self._show_success("Connexion SSH établie.")
        else:
            self._show_error(msg)

    def disconnect_ssh(self) -> None:
        self.ssh.disconnect()
        self._set_connected_ui(False)
        self._log("SSH", "Session SSH fermée.")

    def install_tftp(self) -> None:
        if not self._require_ssh_client():
            return
        if not self._require_connection():
            return
        self._set_busy(True, "Installation TFTP + Chrony...")
        self._set_server_progress(2, "Initialisation...", True)
        try:
            self._log("SSH", "=== Installation TFTP + Chrony ===")
            ok, os_release = self.ssh.detect_os_release(log_callback=lambda m: self._log("SSH", m))
            if not ok:
                self._show_error("Impossible de détecter le système distant.")
                return
            if "debian" not in os_release.lower() and "ubuntu" not in os_release.lower():
                self._show_error("OS non supporté (attendu: Ubuntu/Debian).")
                return

            steps = [
                "apt update",
                "apt install -y tftpd-hpa chrony",
                "mkdir -p /var/lib/tftpboot",
                "chmod -R 777 /var/lib/tftpboot",
                "bash -lc \"grep -q '^allow 0.0.0.0/0$' /etc/chrony/chrony.conf || echo 'allow 0.0.0.0/0' >> /etc/chrony/chrony.conf\"",
                "bash -lc \"grep -q '^local stratum 10$' /etc/chrony/chrony.conf || echo 'local stratum 10' >> /etc/chrony/chrony.conf\"",
                "systemctl restart chrony",
                "systemctl restart tftpd-hpa",
                "ufw allow 123/udp || true",
            ]
            total = len(steps)
            for idx, cmd in enumerate(steps, start=1):
                self._set_server_progress(
                    int((idx - 1) * 100 / total),
                    f"Exécution: {cmd}",
                    True,
                )
                ok, _ = self.ssh.execute_command(
                    cmd, use_sudo=True, log_callback=lambda m: self._log("SSH", m)
                )
                if not ok:
                    self._show_error(f"Commande échouée: {cmd}")
                    return
            self._set_server_progress(100, "Installation terminée.", True)
            self._show_success("TFTP + Chrony installés et configurés avec succès.")
        finally:
            self._set_busy(False)

    def check_tftp_folder(self) -> None:
        if not self._require_ssh_client():
            return
        if not self._require_connection():
            return
        self._set_busy(True, "Vérification dossier TFTP...")
        ok, out = self.ssh.execute_command(
            "ls -ld /var/lib/tftpboot", log_callback=lambda m: self._log("SSH", m)
        )
        self._set_busy(False)
        if ok:
            self._show_success(f"Dossier TFTP OK:\n{out}")
        else:
            self._show_error("Dossier TFTP introuvable ou inaccessible.")

    def restart_tftp(self) -> None:
        if not self._require_ssh_client():
            return
        if not self._require_connection():
            return
        self._set_busy(True, "Redémarrage TFTP...")
        ok, _ = self.ssh.execute_command(
            "systemctl restart tftpd-hpa",
            use_sudo=True,
            log_callback=lambda m: self._log("SSH", m),
        )
        self._set_busy(False)
        if ok:
            self._show_success("Service TFTP redémarré.")
        else:
            self._show_error("Impossible de redémarrer TFTP.")

    def add_phone_row(self) -> None:
        mac_input = self.edt_mac.text().strip()
        mac = normalize_mac(mac_input)
        ext = self.edt_ext.text().strip()
        password = self.edt_phone_pwd.text().strip()
        ip = self.edt_phone_ip.text().strip()

        # Si l'utilisateur edite directement une ligne du tableau (scan reseau),
        # le bouton "Ajouter" agit comme "Enregistrer les modifications".
        if not mac_input and self.tbl_phones.currentRow() >= 0:
            try:
                self._save_all_phones_to_db()
                self._refresh_saved_history()
                self._show_success("Modifications enregistrées.")
            except ValueError as exc:
                self._show_error(str(exc))
            return

        if not is_valid_mac(mac):
            self._show_error("MAC invalide. Format attendu: 12 hexadécimaux.")
            return
        if not ext or not password:
            self._show_error("Extension et mot de passe sont obligatoires.")
            return
        if ip and not self._is_valid_ipv4(ip):
            self._show_error("IP téléphone invalide (format IPv4 requis).")
            return

        self._append_phone_row(mac, ext, password, ip, self.cmb_timezone.currentText())
        self._save_all_phones_to_db()
        self._refresh_saved_history()
        self._log("INFO", f"Téléphone ajouté: {format_mac_display(mac)} / ext {ext}")
        self.edt_mac.clear()
        self.edt_ext.clear()
        self.edt_phone_pwd.clear()
        self.edt_phone_ip.clear()
        self.edt_mac.setFocus()

    def scan_network_phones(self) -> None:
        if not self._require_ssh_client():
            return
        if self.scan_thread and self.scan_thread.isRunning():
            self._show_error("Un scan est déjà en cours.")
            return

        params = self._connection_params()
        if not params["host"] or not params["username"] or not params["password"]:
            self._show_error("Renseignez IP, utilisateur et mot de passe SSH avant le scan.")
            return

        existing_macs = {
            normalize_mac(self.tbl_phones.item(r, 0).text())
            for r in range(self.tbl_phones.rowCount())
            if self.tbl_phones.item(r, 0)
        }
        self.btn_scan_network.setEnabled(False)
        self._set_scan_progress(1, "Démarrage du scan...", active=True)

        self.scan_thread = QThread(self)
        self.scan_worker = NetworkScanWorker(
            host=str(params["host"]),
            port=int(params["port"]),
            username=str(params["username"]),
            password=str(params["password"]),
            subnet=self.edt_scan_subnet.text().strip(),
            existing_macs=existing_macs,
        )
        self.scan_worker.moveToThread(self.scan_thread)
        self.scan_thread.started.connect(self.scan_worker.run)
        self.scan_worker.progress.connect(lambda v, t: self._set_scan_progress(v, t, True))
        self.scan_worker.log.connect(self._log)
        self.scan_worker.finished.connect(self._on_scan_finished)
        self.scan_worker.failed.connect(self._on_scan_failed)
        self.scan_worker.finished.connect(self.scan_thread.quit)
        self.scan_worker.failed.connect(self.scan_thread.quit)
        self.scan_thread.finished.connect(self._cleanup_scan_thread)
        self.scan_thread.start()

    def _on_scan_finished(self, found: list, subnet: str) -> None:
        if subnet and not self.edt_scan_subnet.text().strip():
            self.edt_scan_subnet.setText(subnet)
        if not found:
            self._set_scan_progress(100, "Scan terminé: aucun nouveau téléphone détecté.", active=True)
            self._show_error("Aucun nouveau téléphone détecté sur le réseau.")
            return

        for idx, (ip_addr, mac) in enumerate(found, start=1):
            self._append_phone_row(mac, f"A_DEFINIR_{idx}", f"pwd_{idx}", ip_addr, DEFAULT_TIMEZONE)
            self._log("SCAN", f"Téléphone détecté: {ip_addr} / {format_mac_display(mac)}")

        self._save_all_phones_to_db()
        self._refresh_saved_history()
        self._set_scan_progress(100, f"Scan terminé: {len(found)} téléphone(s) détecté(s).", active=True)
        self._show_success(
            f"{len(found)} téléphone(s) détecté(s). Complétez extension/mot de passe si nécessaire."
        )

    def _on_scan_failed(self, message: str) -> None:
        self._set_scan_progress(100, "Scan interrompu.", active=True)
        self._show_error(message)

    def _cleanup_scan_thread(self) -> None:
        self.btn_scan_network.setEnabled(self.ssh_available and self.ssh.is_connected)
        if self.scan_worker:
            self.scan_worker.deleteLater()
        if self.scan_thread:
            self.scan_thread.deleteLater()
        self.scan_worker = None
        self.scan_thread = None

    def reboot_selected_phones(self) -> None:
        self._start_sip_notify_worker(self._collect_selected_phones() or self._collect_phones(), mode="reboot")

    def resync_selected_phones(self) -> None:
        self._start_sip_notify_worker(self._collect_selected_phones() or self._collect_phones(), mode="check-sync")

    def _start_sip_notify_worker(self, phones: list[Dict[str, str]] | None, mode: str) -> None:
        if not self._require_ssh_client():
            return
        if self.reboot_thread and self.reboot_thread.isRunning():
            self._show_error("Un reboot est déjà en cours.")
            return
        if not phones:
            self._show_error("Aucun téléphone sélectionné.")
            return

        # Let sip_notify auto-detect a correct source IP. We still log the server fields for clarity.
        server_ip = ""

        action = "RESYNC" if mode != "reboot" else "REBOOT"
        self._log("INFO", f"Sending {action} SIP NOTIFY to {len(phones)} téléphone(s).")
        self.btn_reboot_phones.setEnabled(False)
        if hasattr(self, "btn_resync_phones"):
            self.btn_resync_phones.setEnabled(False)
        self._set_reboot_progress(1, f"Démarrage {action.lower()}...", True)
        self.reboot_thread = QThread(self)
        self.sip_notify_mode = mode
        self.reboot_worker = RebootWorker(phones, self.ssh, server_ip=server_ip, mode=mode)
        self.reboot_worker.moveToThread(self.reboot_thread)
        self.reboot_thread.started.connect(self.reboot_worker.run)
        self.reboot_worker.progress.connect(lambda v, t: self._set_reboot_progress(v, f"Progression: {t}", True))
        self.reboot_worker.per_phone.connect(self._on_reboot_phone_status)
        self.reboot_worker.finished.connect(self._on_reboot_finished)
        self.reboot_worker.finished.connect(self.reboot_thread.quit)
        self.reboot_thread.finished.connect(self._cleanup_reboot_thread)
        self.reboot_thread.start()

    def _on_reboot_phone_status(self, mac: str, status: str) -> None:
        self._log("REBOOT", f"{mac}: {status}")
        for row in range(self.tbl_phones.rowCount()):
            mac_item = self.tbl_phones.item(row, COL_MAC)
            if mac_item and normalize_mac(mac_item.text()) == normalize_mac(mac):
                self.tbl_phones.setItem(row, COL_STATUS, QTableWidgetItem("OK" if "envoyé" in status.lower() else "Erreur"))
                break

    def _on_reboot_finished(self, success: int, total: int) -> None:
        action = "Resync" if getattr(self, "sip_notify_mode", "") != "reboot" else "Reboot"
        self._set_reboot_progress(100, f"{action} terminé: {success}/{total}", True)
        if success:
            self._show_success(f"{action} envoyé pour {success}/{total} téléphone(s).")
            if hasattr(self, "lbl_deploy_result"):
                self.lbl_deploy_result.setText(f"Résultat: {action} envoyé pour {success}/{total} téléphone(s).")
                self.lbl_deploy_result.setStyleSheet("color: #34d399; font-weight: 700;")
        else:
            self._show_error(f"Aucun {action.lower()} n'a pu être envoyé.")
            if hasattr(self, "lbl_deploy_result"):
                self.lbl_deploy_result.setText(f"Résultat: échec {action.lower()} (0/{total}).")
                self.lbl_deploy_result.setStyleSheet("color: #ef4444; font-weight: 700;")

    def _cleanup_reboot_thread(self) -> None:
        self.btn_reboot_phones.setEnabled(self.ssh.is_connected)
        if hasattr(self, "btn_resync_phones"):
            self.btn_resync_phones.setEnabled(self.ssh.is_connected)
        if self.reboot_worker:
            self.reboot_worker.deleteLater()
        if self.reboot_thread:
            self.reboot_thread.deleteLater()
        self.reboot_worker = None
        self.reboot_thread = None

    def remove_selected_rows(self) -> None:
        rows = sorted({idx.row() for idx in self.tbl_phones.selectionModel().selectedRows()}, reverse=True)
        if not rows:
            self._show_error("Sélectionnez au moins une ligne à supprimer.")
            return
        removed = 0
        for row in rows:
            self.tbl_phones.removeRow(row)
            removed += 1
        self._save_all_phones_to_db()
        self._refresh_saved_history()
        self._log("INFO", f"{removed} téléphone(s) supprimé(s).")
        self._show_success(f"{removed} téléphone(s) supprimé(s).")

    def import_csv(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Importer CSV", "", "CSV (*.csv)")
        if not file_path:
            return
        phones, errors = load_phones_from_csv(file_path)
        for phone in phones:
            self._append_phone_row(phone["mac"], phone["ext"], phone["password"], "", DEFAULT_TIMEZONE)
        self._save_all_phones_to_db()
        self._refresh_saved_history()
        self._log("INFO", f"Import CSV: {len(phones)} téléphones valides.")
        if errors:
            self._show_error("Import partiel:\n" + "\n".join(errors[:10]))
        else:
            self._show_success(f"Import réussi: {len(phones)} téléphones ajoutés.")

    def generate_extension_range(self) -> None:
        start_ext, ok1 = QInputDialog.getInt(self, "Plage extensions", "Début", 1000, 1, 999999)
        if not ok1:
            return
        count, ok2 = QInputDialog.getInt(self, "Plage extensions", "Nombre", 10, 1, 5000)
        if not ok2:
            return
        base_mac = normalize_mac(self.edt_mac.text())
        password = self.edt_phone_pwd.text().strip()
        if not is_valid_mac(base_mac):
            self._show_error("Saisissez une MAC de base valide.")
            return
        if not password:
            self._show_error("Saisissez un mot de passe avant génération.")
            return

        base_value = int(base_mac, 16)
        for i in range(count):
            next_mac = f"{(base_value + i) % (1 << 48):012X}"
            self._append_phone_row(next_mac, str(start_ext + i), password, "", self.cmb_timezone.currentText())
        self._save_all_phones_to_db()
        self._refresh_saved_history()
        self._log("INFO", f"Génération plage: {count} entrées.")
        self._show_success(f"{count} entrées générées.")

    def _collect_phones(self) -> List[Dict[str, str]]:
        phones: List[Dict[str, str]] = []
        for row in range(self.tbl_phones.rowCount()):
            mac = normalize_mac(self.tbl_phones.item(row, 0).text() if self.tbl_phones.item(row, 0) else "")
            ext = self.tbl_phones.item(row, 1).text().strip() if self.tbl_phones.item(row, 1) else ""
            password = (
                self.tbl_phones.item(row, 2).text().strip() if self.tbl_phones.item(row, 2) else ""
            )
            ip = self.tbl_phones.item(row, 3).text().strip() if self.tbl_phones.item(row, 3) else ""
            timezone = (
                self.tbl_phones.item(row, 4).text().strip() if self.tbl_phones.item(row, 4) else ""
            )
            if not is_valid_mac(mac):
                raise ValueError(f"Ligne {row + 1}: MAC invalide.")
            if not ext or not password:
                raise ValueError(f"Ligne {row + 1}: extension ou mot de passe vide.")
            if ip and not self._is_valid_ipv4(ip):
                raise ValueError(f"Ligne {row + 1}: IP téléphone invalide.")
            if not timezone:
                timezone = DEFAULT_TIMEZONE
            if timezone not in SUPPORTED_TIMEZONES:
                timezone = DEFAULT_TIMEZONE
            phones.append({"mac": mac, "ext": ext, "password": password, "ip": ip, "timezone": timezone})
        return phones

    def _collect_selected_phones(self) -> List[Dict[str, str]]:
        selected_rows = sorted({idx.row() for idx in self.tbl_phones.selectionModel().selectedRows()})
        phones: List[Dict[str, str]] = []
        for row in selected_rows:
            mac = normalize_mac(self.tbl_phones.item(row, 0).text() if self.tbl_phones.item(row, 0) else "")
            ext = self.tbl_phones.item(row, 1).text().strip() if self.tbl_phones.item(row, 1) else ""
            password = (
                self.tbl_phones.item(row, 2).text().strip() if self.tbl_phones.item(row, 2) else ""
            )
            ip = self.tbl_phones.item(row, 3).text().strip() if self.tbl_phones.item(row, 3) else ""
            timezone = (
                self.tbl_phones.item(row, 4).text().strip() if self.tbl_phones.item(row, 4) else ""
            )
            if not is_valid_mac(mac):
                raise ValueError(f"Ligne sélectionnée {row + 1}: MAC invalide.")
            if not ext or not password:
                raise ValueError(f"Ligne sélectionnée {row + 1}: extension ou mot de passe vide.")
            if ip and not self._is_valid_ipv4(ip):
                raise ValueError(f"Ligne sélectionnée {row + 1}: IP téléphone invalide.")
            if not timezone:
                timezone = DEFAULT_TIMEZONE
            if timezone not in SUPPORTED_TIMEZONES:
                timezone = DEFAULT_TIMEZONE
            phones.append({"mac": mac, "ext": ext, "password": password, "ip": ip, "timezone": timezone})
        return phones

    def _warn_if_missing_timezone(self, selected_only: bool) -> None:
        rows = (
            sorted({idx.row() for idx in self.tbl_phones.selectionModel().selectedRows()})
            if selected_only
            else list(range(self.tbl_phones.rowCount()))
        )
        missing = 0
        for row in rows:
            item = self.tbl_phones.item(row, 4)
            if not item or not item.text().strip():
                missing += 1
        if missing:
            QMessageBox.warning(
                self,
                "Timezone manquante",
                f"{missing} téléphone(s) sans timezone. La valeur par défaut sera appliquée: {DEFAULT_TIMEZONE}",
            )

    def deploy_all(self) -> None:
        if not self._require_connection():
            if hasattr(self, "lbl_deploy_result"):
                self.lbl_deploy_result.setText("Résultat: non connecté au serveur.")
                self.lbl_deploy_result.setStyleSheet("color: #ef4444; font-weight: 700;")
            return
        uc_ip = self.edt_uc_ip.text().strip()
        ntp_ip = self.edt_ntp_ip.text().strip()
        if not uc_ip:
            self._show_error("Renseignez l'IP UC.")
            return
        if not ntp_ip:
            self._show_error("Renseignez l'IP NTP.")
            return
        if not self._is_valid_ipv4(uc_ip):
            self._show_error("IP UC invalide (format IPv4 requis).")
            return
        if not self._is_valid_ipv4(ntp_ip):
            self._show_error("IP NTP invalide (format IPv4 requis).")
            return
        # Vérification NTP avant déploiement
        self._log("NTP", f"Vérification NTP avant déploiement: {ntp_ip}")
        ntp_ok = check_ntp_server(ntp_ip)
        self._set_ntp_status(ntp_ok)
        if not ntp_ok:
            choice = QMessageBox.warning(
                self,
                "Serveur NTP invalide",
                "Serveur NTP invalide ou inaccessible.\nContinuer / Annuler ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if choice != QMessageBox.StandardButton.Yes:
                return
        try:
            self._warn_if_missing_timezone(selected_only=True)
            phones = self._collect_selected_phones()
            if not phones:
                self._show_error("Sélectionnez au moins un téléphone à déployer.")
                return
        except ValueError as exc:
            self._show_error(str(exc))
            return
        if not phones:
            self._show_error("Aucun téléphone à déployer.")
            return

        self._set_busy(True, "Déploiement en cours...")
        if hasattr(self, "lbl_deploy_result"):
            self.lbl_deploy_result.setText("Résultat: déploiement en cours...")
            self.lbl_deploy_result.setStyleSheet("color: #60a5fa; font-weight: 700;")
        try:
            self._log("DEPLOIEMENT", f"Début déploiement de {len(phones)} téléphone(s) sélectionné(s).")
            with tempfile.TemporaryDirectory(prefix="cisco_prov_") as tmp_dir:
                generated = generate_xml_files(phones, uc_ip, ntp_ip, tmp_dir)
                self._log("XML", f"{len(generated)} fichiers XML générés.")
                uploaded = 0
                for xml_file in generated:
                    remote_path = f"/var/lib/tftpboot/{Path(xml_file).name}"
                    ok, _ = self.ssh.upload_file(
                        str(xml_file), remote_path, log_callback=lambda m: self._log("SFTP", m)
                    )
                    if not ok:
                        mac_from_file = xml_file.name.replace("SEP", "").replace(".cnf.xml", "")
                        self._set_phone_status(mac_from_file, "Erreur")
                        self._show_error(f"Echec upload: {xml_file.name}")
                        if hasattr(self, "lbl_deploy_result"):
                            self.lbl_deploy_result.setText(
                                f"Résultat: upload échoué ({uploaded}/{len(generated)})."
                            )
                            self.lbl_deploy_result.setStyleSheet("color: #ef4444; font-weight: 700;")
                        return
                    mac_from_file = xml_file.name.replace("SEP", "").replace(".cnf.xml", "")
                    self._set_phone_status(mac_from_file, "OK")
                    uploaded += 1
            ok, _ = self.ssh.execute_command(
                "systemctl restart tftpd-hpa",
                use_sudo=True,
                log_callback=lambda m: self._log("SSH", m),
            )
            if not ok:
                self._show_error("Redémarrage TFTP échoué après upload.")
                if hasattr(self, "lbl_deploy_result"):
                    self.lbl_deploy_result.setText("Résultat: upload OK, mais restart TFTP échoué.")
                    self.lbl_deploy_result.setStyleSheet("color: #ef4444; font-weight: 700;")
                return
            self._show_success("Déploiement terminé avec succès.")
            if hasattr(self, "lbl_deploy_result"):
                self.lbl_deploy_result.setText(f"Résultat: déploiement terminé ({uploaded}/{len(phones)}).")
                self.lbl_deploy_result.setStyleSheet("color: #34d399; font-weight: 700;")
            if self.chk_auto_reboot.isChecked():
                self._start_sip_notify_worker(phones, mode="check-sync")
            else:
                answer = QMessageBox.question(
                    self,
                    "Reboot téléphones",
                    "Redémarrer les téléphones maintenant ?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes,
                )
                if answer == QMessageBox.StandardButton.Yes:
                    self._start_sip_notify_worker(phones, mode="check-sync")
        finally:
            self._set_busy(False)

    def _set_phone_status(self, mac: str, status: str) -> None:
        for row in range(self.tbl_phones.rowCount()):
            item = self.tbl_phones.item(row, COL_MAC)
            if item and normalize_mac(item.text()) == normalize_mac(mac):
                self.tbl_phones.setItem(row, COL_STATUS, QTableWidgetItem(status))
                break

    def closeEvent(self, event) -> None:  # type: ignore[override]
        if self.reboot_thread and self.reboot_thread.isRunning():
            self.reboot_thread.quit()
            self.reboot_thread.wait(1500)
        if self.scan_thread and self.scan_thread.isRunning():
            self.scan_thread.quit()
            self.scan_thread.wait(1500)
        self.ssh.disconnect()
        # Connexion DB gérée par main.py (peut rester ouverte jusqu'à fermeture).
        event.accept()
