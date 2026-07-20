import logging
import pyperclip
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

logger = logging.getLogger(__name__)


class ClipboardHelper:
    """Helper class to safely interact with system clipboard."""

    @staticmethod
    def copy(text: str) -> bool:
        """Copy text to system clipboard."""
        try:
            pyperclip.copy(text)
            return True
        except Exception as e:
            logger.error(f"Clipboard copy failed: {e}")
            return False

    @staticmethod
    def paste() -> str:
        """Paste text from system clipboard."""
        try:
            return pyperclip.paste()
        except Exception as e:
            logger.error(f"Clipboard paste failed: {e}")
            return ""


class ClipboardWatcher(QObject):
    """Watches clipboard for changes and emits signal on new text (clipboard watcher)."""
    text_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.last_text = ""
        self._enabled = False

    def start(self) -> None:
        """Start monitoring clipboard."""
        if self._enabled:
            return
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.dataChanged.connect(self._on_clipboard_changed)
            self._enabled = True
            self.last_text = clipboard.text()
            logger.info("Clipboard watcher started.")

    def stop(self) -> None:
        """Stop monitoring clipboard."""
        if not self._enabled:
            return
        clipboard = QApplication.clipboard()
        if clipboard:
            try:
                clipboard.dataChanged.disconnect(self._on_clipboard_changed)
            except RuntimeError:
                pass  # Already disconnected
            self._enabled = False
            logger.info("Clipboard watcher stopped.")

    def _on_clipboard_changed(self) -> None:
        """Callback when clipboard data changes."""
        clipboard = QApplication.clipboard()
        if clipboard:
            try:
                text = clipboard.text()
                if text and text != self.last_text:
                    self.last_text = text
                    self.text_changed.emit(text)
            except Exception as e:
                logger.error(f"Failed to read clipboard during change event: {e}")
