"""Modern theme system for Cisco IP Phone Provisioning Tool with light and dark modes."""

from enum import Enum
from typing import Dict


class Theme(Enum):
    """Available themes."""
    LIGHT = "light"
    DARK = "dark"


class ThemeManager:
    """Centralized theme management with light/dark mode support."""

    # Light Theme Colors
    LIGHT_COLORS = {
        # Primary & Status Colors
        "primary": "#3b82f6",           # Blue
        "success": "#10b981",           # Green
        "warning": "#f59e0b",           # Amber
        "error": "#ef4444",             # Red
        
        # Background & Surfaces
        "background": "#f8fafc",        # Slate 50
        "surface": "#ffffff",           # White
        "surface_alt": "#f1f5f9",       # Slate 100
        "surface_variant": "#e2e8f0",  # Slate 200
        
        # Text Colors
        "text_primary": "#0f172a",      # Slate 900
        "text_secondary": "#475569",    # Slate 600
        "text_muted": "#78829f",        # Slate 500
        
        # Borders & Dividers
        "border": "#cbd5e1",            # Slate 300
        "border_subtle": "#e2e8f0",    # Slate 200
        
        # Component States
        "disabled_bg": "#e2e8f0",       # Slate 200
        "disabled_text": "#94a3b8",     # Slate 400
        "hover_overlay": "#f1f5f9",     # Slate 100
    }
    
    # Dark Theme Colors
    DARK_COLORS = {
        # Primary & Status Colors
        "primary": "#3b82f6",           # Blue (same)
        "success": "#10b981",           # Green (same)
        "warning": "#f59e0b",           # Amber (same)
        "error": "#ef4444",             # Red (same)
        
        # Background & Surfaces
        "background": "#0f172a",        # Slate 900
        "surface": "#1e293b",           # Slate 800
        "surface_alt": "#334155",       # Slate 700
        "surface_variant": "#475569",   # Slate 600
        
        # Text Colors
        "text_primary": "#f8fafc",      # Slate 50
        "text_secondary": "#cbd5e1",    # Slate 300
        "text_muted": "#94a3b8",        # Slate 400
        
        # Borders & Dividers
        "border": "#475569",            # Slate 600
        "border_subtle": "#334155",     # Slate 700
        
        # Component States
        "disabled_bg": "#334155",       # Slate 700
        "disabled_text": "#64748b",     # Slate 500
        "hover_overlay": "#1e293b",     # Slate 800
    }

    def __init__(self, theme: Theme = Theme.DARK):
        """Initialize theme manager with default dark theme."""
        self.current_theme = theme
        self.colors = self._get_colors()

    def _get_colors(self) -> Dict[str, str]:
        """Get colors for current theme."""
        if self.current_theme == Theme.LIGHT:
            return self.LIGHT_COLORS.copy()
        return self.DARK_COLORS.copy()

    def switch_theme(self, theme: Theme) -> Dict[str, str]:
        """Switch to a different theme and return new colors."""
        self.current_theme = theme
        self.colors = self._get_colors()
        return self.colors

    def get_color(self, name: str, default: str = "#000000") -> str:
        """Get a color by name."""
        return self.colors.get(name, default)

    def get_stylesheet(self) -> str:
        """Get complete QSS stylesheet for current theme."""
        c = self.colors
        
        return f"""
            * {{
                color: {c['text_primary']};
            }}
            
            QWidget {{
                background: {c['background']};
                color: {c['text_primary']};
            }}
            
            QMainWindow {{
                background: {c['background']};
            }}
            
            QTabWidget::pane {{
                border: 1px solid {c['border']};
            }}
            
            QTabBar::tab {{
                background: {c['surface']};
                color: {c['text_primary']};
                padding: 8px 16px;
                border: 1px solid {c['border']};
                margin-right: 2px;
                font-weight: 500;
            }}
            
            QTabBar::tab:selected {{
                background: {c['surface_alt']};
                border-bottom: 3px solid {c['primary']};
            }}
            
            QTabBar::tab:hover {{
                background: {c['hover_overlay']};
            }}
            
            QGroupBox {{
                color: {c['text_primary']};
                border: 2px solid {c['border']};
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 12px;
                font-weight: 600;
            }}
            
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 3px 0 3px;
            }}
            
            QLineEdit {{
                background: {c['surface']};
                color: {c['text_primary']};
                border: 1px solid {c['border']};
                border-radius: 6px;
                padding: 6px 10px;
                selection-background-color: {c['primary']};
                selection-color: white;
            }}
            
            QLineEdit:focus {{
                border: 2px solid {c['primary']};
                background: {c['surface_alt']};
            }}
            
            QLineEdit:disabled {{
                background: {c['disabled_bg']};
                color: {c['disabled_text']};
                border: 1px solid {c['border_subtle']};
            }}
            
            QSpinBox {{
                background: {c['surface']};
                color: {c['text_primary']};
                border: 1px solid {c['border']};
                border-radius: 6px;
                padding: 6px 10px;
            }}
            
            QSpinBox:focus {{
                border: 2px solid {c['primary']};
                background: {c['surface_alt']};
            }}
            
            QSpinBox::up-button, QSpinBox::down-button {{
                border: none;
                width: 20px;
                background: {c['surface_variant']};
            }}
            
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
                background: {c['primary']};
            }}
            
            QComboBox {{
                background: {c['surface']};
                color: {c['text_primary']};
                border: 1px solid {c['border']};
                border-radius: 6px;
                padding: 6px 10px;
                selection-background-color: {c['primary']};
            }}
            
            QComboBox:focus {{
                border: 2px solid {c['primary']};
                background: {c['surface_alt']};
            }}
            
            QComboBox::drop-down {{
                border: none;
                width: 20px;
                background: {c['surface_variant']};
            }}
            
            QComboBox::down-arrow {{
                color: {c['text_secondary']};
            }}
            
            QComboBox QAbstractItemView {{
                background: {c['surface']};
                color: {c['text_primary']};
                border: 1px solid {c['border']};
                selection-background-color: {c['primary']};
                selection-color: white;
            }}
            
            QCheckBox {{
                color: {c['text_primary']};
                spacing: 8px;
            }}
            
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid {c['border']};
                background: {c['surface']};
            }}
            
            QCheckBox::indicator:checked {{
                background: {c['primary']};
                border: 1px solid {c['primary']};
            }}
            
            QCheckBox::indicator:focus {{
                border: 2px solid {c['primary']};
            }}
            
            QPushButton {{
                background: {c['surface_variant']};
                color: {c['text_primary']};
                border: 1px solid {c['border']};
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: 600;
                outline: none;
            }}
            
            QPushButton:hover {{
                background: {c['border']};
            }}
            
            QPushButton:pressed {{
                background: {c['primary']};
                color: white;
            }}
            
            QPushButton:disabled {{
                background: {c['disabled_bg']};
                color: {c['disabled_text']};
                border: 1px solid {c['border_subtle']};
            }}
            
            QPushButton#btn_connect, QPushButton#btn_deployer {{
                background: {c['success']};
                color: white;
                border: 1px solid {c['success']};
                font-weight: 700;
            }}
            
            QPushButton#btn_connect:hover, QPushButton#btn_deployer:hover {{
                background: #34d399;
            }}
            
            QPushButton#btn_connect:pressed, QPushButton#btn_deployer:pressed {{
                background: #059669;
            }}
            
            QPushButton#btn_disconnect {{
                background: {c['error']};
                color: white;
                border: 1px solid {c['error']};
                font-weight: 700;
            }}
            
            QPushButton#btn_disconnect:hover {{
                background: #f87171;
            }}
            
            QPushButton#btn_disconnect:pressed {{
                background: #dc2626;
            }}
            
            QPushButton#btn_test_connect {{
                background: {c['warning']};
                color: white;
                border: 1px solid {c['warning']};
                font-weight: 700;
            }}
            
            QPushButton#btn_test_connect:hover {{
                background: #fbbf24;
            }}
            
            QPushButton#btn_test_connect:pressed {{
                background: #d97706;
            }}
            
            QLabel {{
                color: {c['text_primary']};
            }}
            
            QLabel#lbl_status_dot {{
                font-size: 22px;
                font-weight: 700;
                min-width: 28px;
            }}
            
            QLabel#lbl_status_text {{
                font-weight: 600;
                color: {c['text_secondary']};
            }}
            
            QLabel#lbl_ntp_status {{
                font-weight: 700;
                font-size: 12px;
            }}
            
            QLabel#section_title {{
                font-size: 14px;
                font-weight: 700;
                color: {c['text_primary']};
                padding-bottom: 4px;
                border-bottom: 2px solid {c['primary']};
            }}
            
            QLabel#status_label {{
                font-size: 11px;
                font-weight: 600;
                padding: 4px 8px;
                border-radius: 4px;
            }}
            
            QLabel#status_success {{
                background: {c['success']};
                color: white;
            }}
            
            QLabel#status_error {{
                background: {c['error']};
                color: white;
            }}
            
            QLabel#status_warning {{
                background: {c['warning']};
                color: white;
            }}
            
            QTableWidget {{
                background: {c['surface']};
                color: {c['text_primary']};
                border: 1px solid {c['border']};
                border-radius: 6px;
                gridline-color: {c['border_subtle']};
            }}
            
            QTableWidget::item {{
                padding: 6px;
                border-bottom: 1px solid {c['border_subtle']};
            }}
            
            QTableWidget::item:selected {{
                background: {c['primary']};
                color: white;
            }}
            
            QTableWidget::item:alternate {{
                background: {c['surface_alt']};
            }}
            
            QHeaderView::section {{
                background: {c['surface_variant']};
                color: {c['text_primary']};
                padding: 8px;
                border: none;
                border-right: 1px solid {c['border']};
                font-weight: 700;
            }}
            
            QHeaderView::section:last {{
                border-right: none;
            }}
            
            QProgressBar {{
                background: {c['surface_alt']};
                border: 1px solid {c['border']};
                border-radius: 8px;
                text-align: center;
                height: 24px;
                color: {c['text_primary']};
            }}
            
            QProgressBar::chunk {{
                background: {c['primary']};
                border-radius: 6px;
            }}
            
            QScrollBar:vertical {{
                background: {c['background']};
                width: 12px;
                border: none;
            }}
            
            QScrollBar::handle:vertical {{
                background: {c['border']};
                border-radius: 6px;
                min-height: 20px;
            }}
            
            QScrollBar::handle:vertical:hover {{
                background: {c['text_secondary']};
            }}
            
            QScrollBar::sub-line:vertical, QScrollBar::add-line:vertical {{
                border: none;
                background: none;
            }}
            
            QScrollBar:horizontal {{
                background: {c['background']};
                height: 12px;
                border: none;
            }}
            
            QScrollBar::handle:horizontal {{
                background: {c['border']};
                border-radius: 6px;
                min-width: 20px;
            }}
            
            QScrollBar::handle:horizontal:hover {{
                background: {c['text_secondary']};
            }}
            
            QScrollBar::sub-line:horizontal, QScrollBar::add-line:horizontal {{
                border: none;
                background: none;
            }}
            
            QScrollArea {{
                border: none;
                background: {c['background']};
            }}
            
            QPlainTextEdit {{
                background: {c['surface']};
                color: {c['text_primary']};
                border: 1px solid {c['border']};
                border-radius: 6px;
                padding: 8px;
                selection-background-color: {c['primary']};
                selection-color: white;
            }}
            
            QPlainTextEdit:focus {{
                border: 2px solid {c['primary']};
            }}
            
            QTextEdit {{
                background: {c['surface']};
                color: {c['text_primary']};
                border: 1px solid {c['border']};
                border-radius: 6px;
                padding: 8px;
                selection-background-color: {c['primary']};
                selection-color: white;
            }}
            
            QTextEdit:focus {{
                border: 2px solid {c['primary']};
            }}
            
            QFrame {{
                color: {c['text_primary']};
                border: none;
            }}
            
            QSplitter::handle {{
                background: {c['border']};
                width: 1px;
                height: 1px;
            }}
            
            QSplitter::handle:hover {{
                background: {c['primary']};
            }}
            
            QMessageBox {{
                background: {c['background']};
            }}
            
            QMessageBox QLabel {{
                color: {c['text_primary']};
            }}
            
            QMessageBox QPushButton {{
                min-width: 60px;
            }}
        """

    def get_status_color(self, status: str) -> str:
        """Get color for status label (success, error, warning)."""
        if status.lower() in ["success", "ok", "connecté"]:
            return self.colors.get("success", "#10b981")
        elif status.lower() in ["error", "failed", "ko", "non connecté"]:
            return self.colors.get("error", "#ef4444")
        elif status.lower() in ["warning", "pending"]:
            return self.colors.get("warning", "#f59e0b")
        return self.colors.get("text_secondary", "#475569")


# Global theme manager instance
_theme_manager: ThemeManager | None = None


def get_theme_manager() -> ThemeManager:
    """Get or create global theme manager."""
    global _theme_manager
    if _theme_manager is None:
        _theme_manager = ThemeManager(Theme.DARK)
    return _theme_manager


def switch_global_theme(theme: Theme) -> str:
    """Switch global theme and return new stylesheet."""
    manager = get_theme_manager()
    manager.switch_theme(theme)
    return manager.get_stylesheet()


class ProgressDisplay:
    """Helper class for displaying progress with percentage, time, and status."""
    
    def __init__(self, total_items: int = 100):
        self.total_items = max(1, total_items)
        self.current_item = 0
        self.start_time = None
        self.status_message = ""
    
    def update(self, current: int, status: str = "") -> str:
        """Update progress and return formatted display string."""
        from datetime import datetime
        
        self.current_item = current
        self.status_message = status
        
        if self.start_time is None:
            from datetime import datetime
            self.start_time = datetime.now()
        
        percentage = int((current / self.total_items) * 100)
        
        # Calculate elapsed time
        elapsed = datetime.now() - self.start_time
        elapsed_sec = int(elapsed.total_seconds())
        elapsed_str = f"{elapsed_sec}s" if elapsed_sec < 60 else f"{elapsed_sec // 60}m{elapsed_sec % 60}s"
        
        # Estimate remaining time
        if current > 0:
            rate = current / elapsed.total_seconds() if elapsed.total_seconds() > 0 else 0
            remaining_sec = int((self.total_items - current) / rate) if rate > 0 else 0
            remaining_str = f"{remaining_sec}s" if remaining_sec < 60 else f"{remaining_sec // 60}m"
        else:
            remaining_str = "Calcul..."
        
        # Format display
        display = f"{percentage}% • Temps: {elapsed_str} • Reste: {remaining_str}"
        if status:
            display += f" • {status}"
        
        return display
