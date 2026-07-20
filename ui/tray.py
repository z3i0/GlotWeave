import logging
from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon, QAction
from PySide6.QtWidgets import QSystemTrayIcon, QMenu
from ui.icons import get_icon

logger = logging.getLogger(__name__)


class TrayIconManager(QObject):
    """Manages the System Tray icon, notification bubbles, and context menus."""
    open_settings_requested = Signal()
    open_history_requested = Signal()
    open_quick_translate_requested = Signal()
    exit_requested = Signal()
    pause_toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tray_icon = QSystemTrayIcon(self)

        self.default_icon = get_icon("app_logo", size=22)
        self.paused_icon = get_icon("pause", color="#E67E22", size=22)
        self.tray_icon.setIcon(self.default_icon)

        self._paused = False
        self._notifications_enabled = True

        self._build_context_menu()
        self.tray_icon.activated.connect(self._on_tray_activated)

    def set_icon(self, icon_path: str) -> None:
        try:
            icon = QIcon(icon_path)
            if not icon.isNull():
                self.default_icon = icon
                if not self._paused:
                    self.tray_icon.setIcon(self.default_icon)
        except Exception as e:
            logger.error(f"Failed to set custom tray icon: {e}")

    def show(self) -> None:
        self.tray_icon.show()
        logger.info("System Tray Icon visible.")

    def set_notifications_enabled(self, enabled: bool) -> None:
        self._notifications_enabled = enabled

    def show_notification(self, title: str, message: str, is_error: bool = False) -> None:
        if not self._notifications_enabled:
            return
        icon = QSystemTrayIcon.MessageIcon.Warning if is_error else QSystemTrayIcon.MessageIcon.Information
        self.tray_icon.showMessage(title, message, icon, 3000)

    def _build_context_menu(self) -> None:
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background-color: #141619;
                color: #E0E0E0;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 6px;
                font-family: 'Segoe UI';
                font-size: 12px;
            }
            QMenu::item {
                padding: 6px 16px 6px 10px;
                border-radius: 4px;
            }
            QMenu::item:selected {
                background-color: #5CB868;
                color: #12141A;
                font-weight: 600;
            }
            QMenu::separator {
                height: 1px;
                background-color: rgba(255, 255, 255, 0.06);
                margin: 4px 8px;
            }
        """)

        # App title header
        header_action = QAction("GlotWeave", self)
        header_action.setIcon(get_icon("app_logo", size=18))
        header_action.setEnabled(False)
        menu.addAction(header_action)
        menu.addSeparator()

        # Settings
        self.act_settings = QAction("Settings", self)
        self.act_settings.setIcon(get_icon("settings", color="#AAAAAA", size=16))
        self.act_settings.triggered.connect(self.open_settings_requested.emit)
        menu.addAction(self.act_settings)

        # Quick Translate
        self.act_quick_translate = QAction("Quick Translate", self)
        self.act_quick_translate.setIcon(get_icon("zap", color="#AAAAAA", size=16))
        self.act_quick_translate.triggered.connect(self.open_quick_translate_requested.emit)
        menu.addAction(self.act_quick_translate)

        # History
        self.act_history = QAction("Translation History", self)
        self.act_history.setIcon(get_icon("history", color="#AAAAAA", size=16))
        self.act_history.triggered.connect(self.open_history_requested.emit)
        menu.addAction(self.act_history)

        menu.addSeparator()

        # Voice Translate action
        self.act_voice = QAction("Voice Translate", self)
        self.act_voice.setIcon(get_icon("mic", color="#AAAAAA", size=16))
        menu.addAction(self.act_voice)

        menu.addSeparator()

        # Pause/Resume
        self.act_pause = QAction("Pause Translation", self)
        self.act_pause.setIcon(get_icon("pause", color="#AAAAAA", size=16))
        self.act_pause.triggered.connect(self._toggle_pause)
        menu.addAction(self.act_pause)

        menu.addSeparator()

        # Exit
        self.act_exit = QAction("Exit", self)
        self.act_exit.setIcon(get_icon("power", color="#FF5555", size=16))
        self.act_exit.triggered.connect(self.exit_requested.emit)
        menu.addAction(self.act_exit)

        self.tray_icon.setContextMenu(menu)

    def _toggle_pause(self) -> None:
        self._paused = not self._paused
        self.pause_toggled.emit(self._paused)
        if self._paused:
            self.act_pause.setText("Resume Translation")
            self.act_pause.setIcon(get_icon("play", color="#5CB868", size=16))
            self.tray_icon.setIcon(self.paused_icon)
            self.show_notification("GlotWeave", "Translation suspended.")
            logger.info("Translation monitoring paused by user.")
        else:
            self.act_pause.setText("Pause Translation")
            self.act_pause.setIcon(get_icon("pause", color="#AAAAAA", size=16))
            self.tray_icon.setIcon(self.default_icon)
            self.show_notification("GlotWeave", "Translation resumed.")
            logger.info("Translation monitoring resumed by user.")

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.open_settings_requested.emit()
        elif reason == QSystemTrayIcon.ActivationReason.MiddleClick:
            self.open_quick_translate_requested.emit()
