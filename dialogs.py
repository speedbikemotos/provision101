"""Custom styled dialogs for provisioning tool with theme support."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QWidget, QStyle
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QColor, QIcon, QPixmap
from theme import get_theme_manager, Theme


class StyledDialog(QDialog):
    """Base dialog class with theme-aware styling."""
    
    def __init__(self, parent=None, title: str = ""):
        super().__init__(parent)
        self.theme_manager = get_theme_manager()
        self.setWindowTitle(title)
        self.setMinimumWidth(400)
        self.setMinimumHeight(200)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._apply_styling()
    
    def _apply_styling(self):
        """Apply theme-based styling to dialog."""
        theme = self.theme_manager.current_theme
        if theme == Theme.DARK:
            bg_color = "#0f172a"
            border_color = "#334155"
            text_color = "#e2e8f0"
        else:
            bg_color = "#f8fafc"
            border_color = "#cbd5e1"
            text_color = "#0f172a"
        
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {bg_color};
                color: {text_color};
                border: 1px solid {border_color};
            }}
            QPushButton {{
                padding: 10px 20px;
                border-radius: 6px;
                font-weight: 600;
                min-width: 80px;
            }}
            QLabel {{
                color: {text_color};
            }}
        """)


class ErrorDialog(StyledDialog):
    """Styled error message dialog."""
    
    def __init__(self, parent=None, title: str = "Erreur", message: str = ""):
        super().__init__(parent, title)
        self._build_ui(message)
        self.setModal(True)
    
    def _build_ui(self, message: str):
        """Build dialog UI with error styling."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Icon and message
        header_layout = QHBoxLayout()
        
        # Error icon/indicator
        icon_label = QLabel("⚠️")
        icon_label.setFont(QFont("Segoe UI", 24))
        icon_label.setStyleSheet(f"color: {self.theme_manager.get_color('error')};")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        header_layout.addWidget(icon_label)
        
        # Message text
        msg_label = QLabel(message)
        msg_label.setWordWrap(True)
        msg_label.setFont(QFont("Segoe UI", 11))
        msg_label.setMinimumHeight(80)
        header_layout.addWidget(msg_label, 1)
        
        layout.addLayout(header_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        btn_ok = QPushButton("OK")
        btn_ok.setMinimumWidth(100)
        btn_ok.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.theme_manager.get_color('error')};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {self._lighten_color(self.theme_manager.get_color('error'))};
            }}
        """)
        btn_ok.clicked.connect(self.accept)
        button_layout.addWidget(btn_ok)
        
        layout.addLayout(button_layout)
    
    def _lighten_color(self, hex_color: str) -> str:
        """Lighten a hex color for hover state."""
        try:
            hex_color = hex_color.lstrip('#')
            r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
            r = min(255, r + 30)
            g = min(255, g + 30)
            b = min(255, b + 30)
            return f"#{r:02x}{g:02x}{b:02x}"
        except:
            return hex_color


class WarningDialog(StyledDialog):
    """Styled warning message dialog."""
    
    def __init__(self, parent=None, title: str = "Avertissement", message: str = ""):
        super().__init__(parent, title)
        self._build_ui(message)
        self.setModal(True)
    
    def _build_ui(self, message: str):
        """Build dialog UI with warning styling."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Icon and message
        header_layout = QHBoxLayout()
        
        icon_label = QLabel("⚡")
        icon_label.setFont(QFont("Segoe UI", 24))
        icon_label.setStyleSheet(f"color: {self.theme_manager.get_color('warning')};")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        header_layout.addWidget(icon_label)
        
        msg_label = QLabel(message)
        msg_label.setWordWrap(True)
        msg_label.setFont(QFont("Segoe UI", 11))
        msg_label.setMinimumHeight(80)
        header_layout.addWidget(msg_label, 1)
        
        layout.addLayout(header_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        btn_ok = QPushButton("Compris")
        btn_ok.setMinimumWidth(100)
        btn_ok.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.theme_manager.get_color('warning')};
                color: #000000;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: #fbbf24;
            }}
        """)
        btn_ok.clicked.connect(self.accept)
        button_layout.addWidget(btn_ok)
        
        layout.addLayout(button_layout)


class SuccessDialog(StyledDialog):
    """Styled success message dialog - auto-closes after delay."""
    
    def __init__(self, parent=None, title: str = "Succès", message: str = "", auto_close: bool = True):
        super().__init__(parent, title)
        self.auto_close = auto_close
        self._build_ui(message)
        self.setModal(False)
        
        if auto_close:
            QTimer.singleShot(3000, self.accept)
    
    def _build_ui(self, message: str):
        """Build dialog UI with success styling."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Icon and message
        header_layout = QHBoxLayout()
        
        icon_label = QLabel("✓")
        icon_label.setFont(QFont("Segoe UI", 24, QFont.Weight.Bold))
        icon_label.setStyleSheet(f"color: {self.theme_manager.get_color('success')};")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        header_layout.addWidget(icon_label)
        
        msg_label = QLabel(message)
        msg_label.setWordWrap(True)
        msg_label.setFont(QFont("Segoe UI", 11))
        msg_label.setMinimumHeight(60)
        header_layout.addWidget(msg_label, 1)
        
        layout.addLayout(header_layout)
        
        if not self.auto_close:
            button_layout = QHBoxLayout()
            button_layout.addStretch()
            
            btn_ok = QPushButton("Fermer")
            btn_ok.setMinimumWidth(100)
            btn_ok.setStyleSheet(f"""
                QPushButton {{
                    background-color: {self.theme_manager.get_color('success')};
                    color: white;
                    border: none;
                    border-radius: 6px;
                    padding: 8px 16px;
                    font-weight: 600;
                }}
                QPushButton:hover {{
                    background-color: #34d399;
                }}
            """)
            btn_ok.clicked.connect(self.accept)
            button_layout.addWidget(btn_ok)
            layout.addLayout(button_layout)


class ConfirmDialog(StyledDialog):
    """Styled confirmation dialog with Yes/No buttons."""
    
    def __init__(self, parent=None, title: str = "Confirmation", message: str = ""):
        super().__init__(parent, title)
        self._build_ui(message)
        self.setModal(True)
        self.result_value = False
    
    def _build_ui(self, message: str):
        """Build dialog UI with confirmation styling."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Icon and message
        header_layout = QHBoxLayout()
        
        icon_label = QLabel("❓")
        icon_label.setFont(QFont("Segoe UI", 24))
        icon_label.setStyleSheet(f"color: {self.theme_manager.get_color('info')};")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        header_layout.addWidget(icon_label)
        
        msg_label = QLabel(message)
        msg_label.setWordWrap(True)
        msg_label.setFont(QFont("Segoe UI", 11))
        msg_label.setMinimumHeight(80)
        header_layout.addWidget(msg_label, 1)
        
        layout.addLayout(header_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        btn_no = QPushButton("Non")
        btn_no.setMinimumWidth(100)
        btn_no.setStyleSheet(f"""
            QPushButton {{
                background-color: #64748b;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: #94a3b8;
            }}
        """)
        btn_no.clicked.connect(self.reject)
        button_layout.addWidget(btn_no)
        
        btn_yes = QPushButton("Oui")
        btn_yes.setMinimumWidth(100)
        btn_yes.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.theme_manager.get_color('success')};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: #34d399;
            }}
        """)
        btn_yes.clicked.connect(self.accept)
        button_layout.addWidget(btn_yes)
        
        layout.addLayout(button_layout)
    
    def get_result(self) -> bool:
        """Return True if user clicked Yes, False if No."""
        return self.exec() == QDialog.DialogCode.Accepted


class InfoDialog(StyledDialog):
    """Styled info message dialog - auto-closes after delay."""
    
    def __init__(self, parent=None, title: str = "Information", message: str = ""):
        super().__init__(parent, title)
        self._build_ui(message)
        self.setModal(False)
        
        QTimer.singleShot(2500, self.accept)
    
    def _build_ui(self, message: str):
        """Build dialog UI with info styling."""
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Icon and message
        header_layout = QHBoxLayout()
        
        icon_label = QLabel("ℹ️")
        icon_label.setFont(QFont("Segoe UI", 24))
        icon_label.setStyleSheet(f"color: {self.theme_manager.get_color('info')};")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        header_layout.addWidget(icon_label)
        
        msg_label = QLabel(message)
        msg_label.setWordWrap(True)
        msg_label.setFont(QFont("Segoe UI", 11))
        msg_label.setMinimumHeight(60)
        header_layout.addWidget(msg_label, 1)
        
        layout.addLayout(header_layout)
