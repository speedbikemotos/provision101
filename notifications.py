"""Inline notification widget for status feedback."""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QColor
from theme import get_theme_manager, Theme


class NotificationWidget(QWidget):
    """Inline notification widget that appears at the bottom or top of a container."""
    
    closed = pyqtSignal()
    
    def __init__(self, parent=None, message: str = "", notification_type: str = "info", duration: int = 3000):
        super().__init__(parent)
        self.theme_manager = get_theme_manager()
        self.notification_type = notification_type  # "success", "error", "warning", "info"
        self.duration = duration
        self._build_ui(message)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        
        # Auto-dismiss timer
        if duration > 0:
            QTimer.singleShot(duration, self.dismiss)
    
    def _build_ui(self, message: str):
        """Build the notification UI."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)
        
        # Icon/indicator
        icon_label = QLabel(self._get_icon())
        icon_label.setFont(QFont("Segoe UI", 16))
        icon_label.setFixedWidth(30)
        
        # Message
        msg_label = QLabel(message)
        msg_label.setWordWrap(True)
        msg_label.setFont(QFont("Segoe UI", 10))
        
        # Close button
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(24, 24)
        btn_close.setFlat(True)
        btn_close.clicked.connect(self.dismiss)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        
        layout.addWidget(icon_label)
        layout.addWidget(msg_label, 1)
        layout.addWidget(btn_close)
        
        # Apply styling based on type
        self._apply_styling()
    
    def _get_icon(self) -> str:
        """Get icon for notification type."""
        icons = {
            "success": "✓",
            "error": "✕",
            "warning": "⚠",
            "info": "ℹ"
        }
        return icons.get(self.notification_type, "ℹ")
    
    def _apply_styling(self):
        """Apply theme-aware styling."""
        color_map = {
            "success": ("success", "#ffffff"),
            "error": ("error", "#ffffff"),
            "warning": ("warning", "#000000"),
            "info": ("info", "#ffffff")
        }
        
        color_key, text_color = color_map.get(self.notification_type, ("info", "#ffffff"))
        bg_color = self.theme_manager.get_color(color_key)
        
        self.setStyleSheet(f"""
            NotificationWidget {{
                background-color: {bg_color};
                color: {text_color};
                border-radius: 6px;
                border: 1px solid {bg_color};
            }}
            QLabel {{
                color: {text_color};
            }}
            QPushButton {{
                color: {text_color};
                background-color: transparent;
                border: none;
                padding: 0px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background-color: rgba(255, 255, 255, 0.2);
                border-radius: 3px;
            }}
        """)
    
    def dismiss(self):
        """Dismiss the notification."""
        self.closed.emit()
        self.deleteLater()


class NotificationManager:
    """Manages notifications for a parent widget."""
    
    def __init__(self, parent_widget: QWidget):
        self.parent = parent_widget
        self.notifications = []
    
    def show_success(self, message: str, duration: int = 3000):
        """Show success notification."""
        self._show_notification(message, "success", duration)
    
    def show_error(self, message: str, duration: int = 4000):
        """Show error notification."""
        self._show_notification(message, "error", duration)
    
    def show_warning(self, message: str, duration: int = 3500):
        """Show warning notification."""
        self._show_notification(message, "warning", duration)
    
    def show_info(self, message: str, duration: int = 2500):
        """Show info notification."""
        self._show_notification(message, "info", duration)
    
    def _show_notification(self, message: str, notif_type: str, duration: int):
        """Show a notification."""
        # Create notification
        notification = NotificationWidget(
            self.parent,
            message=message,
            notification_type=notif_type,
            duration=duration
        )
        
        # Get parent layout
        if hasattr(self.parent, 'layout') and self.parent.layout():
            parent_layout = self.parent.layout()
            # Add at the end (before stretch if present)
            parent_layout.insertWidget(parent_layout.count() - 1, notification)
        
        self.notifications.append(notification)
        notification.closed.connect(lambda: self.notifications.remove(notification) if notification in self.notifications else None)
