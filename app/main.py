import sys
import os
import logging
import threading
import time
from io import BytesIO
from typing import Optional


# Configure absolute path imports
if getattr(sys, 'frozen', False):
    bundle_dir = getattr(sys, '_MEIPASS', os.path.abspath(os.path.dirname(__file__)))
    if bundle_dir not in sys.path:
        sys.path.append(bundle_dir)
else:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# pyrefly: ignore [missing-import]
from PySide6.QtCore import QObject, Signal, Slot, QTimer, Qt
# pyrefly: ignore [missing-import]
from PySide6.QtGui import QIcon, QPixmap, QColor, QPainter, QAction
# pyrefly: ignore [missing-import]
from PySide6.QtWidgets import QApplication, QMessageBox
# pyrefly: ignore [missing-import]
from PySide6.QtNetwork import QLocalServer, QLocalSocket

from app.config import APP_NAME, APP_VERSION, LOG_FILE
from core.settings import SettingsManager, Settings
from core.history_manager import HistoryManager
from core.translator import TranslationManager
from core.keyboard import KeyboardManager
from core.clipboard import ClipboardHelper, ClipboardWatcher
from services.language_detector import LanguageDetector
from services.google_translate import GoogleTranslateFreeProvider
from services.ollama_translate import OllamaTranslateProvider
from services.cloud_providers import (
    GoogleCloudTranslateProvider, DeepLTranslateProvider,
    OpenAITranslateProvider, GeminiTranslateProvider
)
from services.voice_service import VoiceService
from services.update_checker import UpdateChecker
from services.dictionary_service import DictionaryService
from services.live_caption_service import LiveCaptionService

from ui.tray import TrayIconManager
from ui.overlay import TranslationOverlay, VoiceIndicatorOverlay
from ui.settings_window import SettingsWindow
from ui.history_window import HistoryWindow
from ui.quick_translate import QuickTranslateWindow
from ui.live_caption_window import LiveCaptionWindow
from ui.icons import get_icon

# Configure stdout encoding for Windows console (supports Arabic/Unicode logs)
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8")
    ]
)
logger = logging.getLogger("GlotWeave")


class TranslatorApp(QObject):
    """The central application coordinator."""
    show_settings_signal = Signal()
    show_history_signal = Signal()
    _show_overlay_signal = Signal(str)   # internal: safely show overlay from any thread

    def __init__(self):
        super().__init__()
        # 1. Managers & Services
        self.settings_mgr = SettingsManager()
        self.history_mgr = HistoryManager()
        self.detector = LanguageDetector()
        
        self.translation_mgr = TranslationManager()
        self.translation_mgr.set_language_detector(self.detector)
        self._register_providers()

        self.voice_service = VoiceService()
        self.voice_action = None
        self._voice_started_notified = False
        self.update_checker = UpdateChecker()

        # Dictionary & Live Caption Services
        self.dictionary_service = DictionaryService()
        self.live_caption_service = LiveCaptionService(self.translation_mgr)

        # 2. Window / Overlay UIs
        self.overlay = TranslationOverlay()
        self.voice_indicator = VoiceIndicatorOverlay()
        self.voice_indicator.stop_requested.connect(self.trigger_voice_translation)
        self.live_caption_window = LiveCaptionWindow(self.dictionary_service)
        self.quick_translate_window = None
        self.settings_window = None
        self.history_window = None

        # 3. System Tray Icon Setup
        self.tray = TrayIconManager()
        self._setup_tray_icon()

        # 4. Keyboard / Clipboard Watchers
        self.keyboard_mgr = KeyboardManager()
        self.clipboard_watcher = ClipboardWatcher()

        # 5. Connections
        self._connect_signals()

        # 6. Apply Current Settings
        self._apply_settings(self.settings_mgr.settings)
        
        # Check for updates
        self.update_checker.check_for_updates()

    def _register_providers(self) -> None:
        """Register all translation provider instances."""
        self.translation_mgr.register_provider("google_free", GoogleTranslateFreeProvider())
        self.translation_mgr.register_provider("ollama", OllamaTranslateProvider())
        self.translation_mgr.register_provider("google_cloud", GoogleCloudTranslateProvider())
        self.translation_mgr.register_provider("deepl", DeepLTranslateProvider())
        self.translation_mgr.register_provider("openai", OpenAITranslateProvider())
        self.translation_mgr.register_provider("gemini", GeminiTranslateProvider())

    def _setup_tray_icon(self) -> None:
        """Generates a default fallback icon if assets don't exist."""
        # Draw a beautiful clean cyan circle as default icon
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(0, 173, 181))  # Theme Cyan
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(4, 4, 24, 24)
        painter.end()
        
        icon = QIcon(pixmap)
        self.tray.tray_icon.setIcon(icon)
        self.tray.default_icon = icon
        self.tray.show()

    def _connect_signals(self) -> None:
        """Wire up component signals and slots."""
        # Tray events
        self.tray.open_settings_requested.connect(self.show_settings)
        self.tray.open_history_requested.connect(self.show_history)
        self.tray.open_quick_translate_requested.connect(self.show_quick_translate)
        self.tray.act_voice.triggered.connect(self.trigger_voice_translation)
        self.tray.live_caption_toggled.connect(self.toggle_live_caption)
        self.tray.exit_requested.connect(self.quit_app)
        self.tray.pause_toggled.connect(self._on_pause_toggled)

        # Keyboard manager events
        self.keyboard_mgr.hotkey_triggered.connect(self.trigger_hotkey_translation)
        self.keyboard_mgr.voice_hotkey_triggered.connect(self.trigger_voice_translation)
        self.keyboard_mgr.live_caption_hotkey_triggered.connect(self.toggle_live_caption)
        self.keyboard_mgr.layout_switch_triggered.connect(self.trigger_hotkey_translation)
        self.keyboard_mgr.live_translate_triggered.connect(self.trigger_live_translation)

        # Clipboard watcher events
        self.clipboard_watcher.text_changed.connect(self._on_clipboard_watched_text)

        # Voice recognition events
        self.voice_service.recording_started.connect(self._on_voice_started)
        self.voice_service.transcribing_started.connect(self._on_voice_transcribing)
        self.voice_service.recording_finished.connect(self._on_voice_finished)
        self.voice_service.recording_stopped.connect(self._on_voice_stopped)
        self.voice_service.error_occurred.connect(self._on_voice_error)

        # Live Caption service events
        self.live_caption_service.caption_updated.connect(self._on_live_caption_updated)
        self.live_caption_service.status_changed.connect(self.live_caption_window.update_status)
        self.live_caption_service.error_occurred.connect(
            lambda err: self.tray.show_notification("Live Caption Error", err, is_error=True)
        )
        self.live_caption_window.settings_requested.connect(self.show_settings)
        self.live_caption_window.translation_toggled.connect(
            lambda en: setattr(self.live_caption_service, "enable_translation", en)
        )

        # Update checker events
        self.update_checker.update_available.connect(
            lambda version, url: self.tray.show_notification(
                "Update Available", f"Version {version} is available."
            )
        )

        # Internal overlay signal (ensures overlay is shown on main thread)
        self._show_overlay_signal.connect(self._show_overlay_with_duration)

    def _apply_settings(self, s: Settings) -> None:
        """Configure components with user preferences."""
        from app.config import ACCENT_COLORS
        # System Tray notifications toggle
        self.tray.set_notifications_enabled(s.notifications)

        # Apply accent color to overlays and quick translate
        accent = ACCENT_COLORS.get(s.accent_color, "#00ADB5")
        self.overlay.set_accent(accent)
        self.live_caption_window.set_accent(accent)
        if self.quick_translate_window:
            self.quick_translate_window.set_accent(accent)

        # Live Caption configuration
        self.live_caption_window.set_languages(s.live_caption_source_lang, s.live_caption_target_lang)
        self.live_caption_service.update_settings(
            source_lang=s.live_caption_source_lang,
            target_lang=s.live_caption_target_lang,
            audio_source=s.live_caption_audio_source,
            enable_translation=self.live_caption_window._enable_translation,
            vad_aggressiveness=s.live_caption_vad_aggressiveness
        )

        # Update Keyboard monitoring
        self.keyboard_mgr.update_settings(
            hotkey=s.hotkey,
            voice_hotkey=s.voice_hotkey,
            enable_live=s.live_translation and not self.tray._paused,
            enable_layout_switch=s.translate_on_layout_switch and not self.tray._paused,
            caption_hotkey=s.live_caption_hotkey
        )

        # Clipboard Watcher status (Automatic background translation on copy)
        if s.clipboard_monitor and not self.tray._paused:
            self.clipboard_watcher.start()
        else:
            self.clipboard_watcher.stop()

        logger.info("Application settings applied.")

    @Slot()
    @Slot(bool)
    def toggle_live_caption(self, enabled: Optional[bool] = None) -> None:
        """Toggle Live Caption on/off."""
        if enabled is None:
            enabled = not self.live_caption_service.is_running()

        self.tray.act_live_caption.setChecked(enabled)
        s = self.settings_mgr.settings

        if enabled:
            self.live_caption_window.show()
            self.live_caption_service.start_captioning(
                source_lang=s.live_caption_source_lang,
                target_lang=s.live_caption_target_lang,
                audio_source=s.live_caption_audio_source,
                enable_translation=self.live_caption_window._enable_translation,
                provider=s.provider,
                api_key=s.api_key,
                vad_aggressiveness=s.live_caption_vad_aggressiveness,
                silence_timeout=s.live_caption_silence_timeout,
                max_phrase_duration=s.live_caption_max_phrase_duration,
                queue_maxsize=s.live_caption_queue_maxsize,
                overlap_duration=s.live_caption_overlap_duration,
                retry_delay=s.live_caption_retry_delay
            )
            self.tray.show_notification("Live Caption", "Live Caption started.")
        else:
            self.live_caption_service.stop_captioning()
            self.live_caption_window.hide()
            self.tray.show_notification("Live Caption", "Live Caption stopped.")

    @Slot(str, str, str, str)
    def _on_live_caption_updated(self, orig: str, trans: str, src: str, tgt: str) -> None:
        """Slot called when Live Caption receives newly transcribed/translated text."""
        self.live_caption_window.update_caption(orig, trans)

    def _on_pause_toggled(self, paused: bool) -> None:
        """Pause or resume keyboard / clipboard triggers."""
        s = self.settings_mgr.settings
        if paused:
            self.keyboard_mgr.stop()
            self.clipboard_watcher.stop()
            if self.live_caption_service.is_running():
                self.toggle_live_caption(False)
        else:
            self._apply_settings(s)

    @Slot(str)
    def _show_overlay_with_duration(self, text: str) -> None:
        """Show overlay using the configured duration from settings."""
        duration = self.settings_mgr.settings.overlay_duration
        self.overlay.show_translation(text, duration_ms=duration)

    @Slot()
    def show_settings(self, section: str | None = None) -> None:
        if not self.settings_window:
            self.settings_window = SettingsWindow(self.settings_mgr, history_manager=self.history_mgr)
            self.settings_window.setWindowIcon(get_icon("app_logo", size=32))
            self.settings_window.settings_updated.connect(self._apply_settings)
            self.settings_window.settings_updated.connect(
                lambda s: setattr(self, 'settings_window', None) or None
            )
        if section:
            self.settings_window.select_section_by_name(section)
        self.settings_window.show()
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    @Slot()
    def show_history(self) -> None:
        self.show_settings(section="history")

    @Slot()
    def show_quick_translate(self) -> None:
        from app.config import ACCENT_COLORS
        accent = ACCENT_COLORS.get(self.settings_mgr.settings.accent_color, "#5CB868")
        if not self.quick_translate_window:
            self.quick_translate_window = QuickTranslateWindow(
                translation_mgr=self.translation_mgr,
                settings_mgr=self.settings_mgr
            )
            self.quick_translate_window.setWindowIcon(get_icon("app_logo", size=32))
            self.quick_translate_window.set_accent(accent)
        self.quick_translate_window.set_settings(self.settings_mgr.settings)
        self.quick_translate_window.toggle_visibility()

    @Slot()
    def trigger_hotkey_translation(self) -> None:
        """Runs the Grammarly-like select, copy, translate, paste routine in a worker thread."""
        threading.Thread(target=self._hotkey_translation_worker, daemon=True).start()

    def _hotkey_translation_worker(self) -> None:
        """Simulates CTRL+C, translates the text, then replaces it via CTRL+V."""
        # Temporarily disable clipboard watcher to prevent feedback loop
        was_watcher_enabled = self.clipboard_watcher._enabled
        if was_watcher_enabled:
            self.clipboard_watcher.stop()

        # 1. Store original clipboard text to restore later
        original_clipboard = ClipboardHelper.paste()

        # Clear clipboard to detect if new copy succeeds
        ClipboardHelper.copy("")
        time.sleep(0.02)

        # 2. Trigger COPY to capture highlighted text cleanly
        import ctypes
        user32 = ctypes.windll.user32
        # Explicitly release physical modifier keys (Shift, Ctrl, Alt, Win)
        for vk in [0x10, 0x11, 0x12, 0x5B]:
            user32.keybd_event(vk, 0, 2, 0)
        time.sleep(0.05)

        # Send clean Ctrl+C
        user32.keybd_event(0x11, 0, 0, 0)  # Ctrl DOWN
        user32.keybd_event(0x43, 0, 0, 0)  # C DOWN
        time.sleep(0.02)
        user32.keybd_event(0x43, 0, 2, 0)  # C UP
        user32.keybd_event(0x11, 0, 2, 0)  # Ctrl UP
        time.sleep(0.15)  # Wait for OS clipboard update

        copied_text = ClipboardHelper.paste()

        # If nothing was selected, return and restore original clipboard
        if not copied_text:
            logger.info("No text highlighted or copy returned empty.")
            if was_watcher_enabled:
                self.clipboard_watcher.start()
            ClipboardHelper.copy(original_clipboard)
            return

        s = self.settings_mgr.settings
        try:
            # 3. Translate
            translated = self.translation_mgr.translate(
                text=copied_text,
                source_lang=s.source_lang,
                target_lang=s.target_lang,
                provider_name=s.provider,
                api_key=s.api_key,
                extra_settings=s.to_dict()
            )

            # 4. Replace text at cursor
            ClipboardHelper.copy(translated)
            time.sleep(0.05)
            user32.keybd_event(0x11, 0, 0, 0)  # Ctrl DOWN
            user32.keybd_event(0x56, 0, 0, 0)  # V DOWN
            time.sleep(0.02)
            user32.keybd_event(0x56, 0, 2, 0)  # V UP
            user32.keybd_event(0x11, 0, 2, 0)  # Ctrl UP
            time.sleep(0.15)

            # 5. Overlay Display & Logging
            self._show_overlay_signal.emit(translated)
            self.history_mgr.add(copied_text, translated, s.source_lang, s.target_lang)
            logger.info(f"Hotkey translated: '{copied_text}' -> '{translated}'")
            
        except Exception as e:
            logger.error(f"Hotkey translation worker failed: {e}")
            self.tray.show_notification("Translation Error", str(e), is_error=True)
        finally:
            # 6. Restore original clipboard
            ClipboardHelper.copy(original_clipboard)
            time.sleep(0.05)
            # Re-enable clipboard watcher if it was enabled
            if was_watcher_enabled:
                self.clipboard_watcher.start()

    @Slot(str, int)
    def trigger_live_translation(self, text: str, backspace_count: int) -> None:
        """Performs Live Typing translation of a sentence."""
        threading.Thread(
            target=self._live_translation_worker,
            args=(text, backspace_count),
            daemon=True
        ).start()

    def _live_translation_worker(self, text: str, backspace_count: int) -> None:
        """Translates sentence and types the replacement backspace by backspace."""
        s = self.settings_mgr.settings
        try:
            translated = self.translation_mgr.translate(
                text=text,
                source_lang=s.source_lang,
                target_lang=s.target_lang,
                provider_name=s.provider,
                api_key=s.api_key,
                extra_settings=s.to_dict()
            )

            # Temporarily ignore keyboard events during simulation
            self.keyboard_mgr._ignore_events = True

            # Send backspaces to erase the typed sentence
            import keyboard as kb
            for _ in range(backspace_count):
                kb.send("backspace")
                time.sleep(0.005)

            # Write the translated sentence
            kb.write(translated)
            
            # Save to history
            self.history_mgr.add(text, translated, s.source_lang, s.target_lang)
            logger.info(f"Live Typing translated: '{text}' -> '{translated}'")
            
        except Exception as e:
            logger.error(f"Live translation worker failed: {e}")
        finally:
            # Always restore keyboard event listening
            self.keyboard_mgr._ignore_events = False

    @Slot(str)
    def _on_clipboard_watched_text(self, text: str) -> None:
        """Triggered by ClipboardWatcher (Clipboard Watcher feature)."""
        # Automatically translate copied text and display overlay near cursor
        s = self.settings_mgr.settings
        if not s.clipboard_monitor:
            return

        threading.Thread(target=self._clipboard_watcher_worker, args=(text,), daemon=True).start()

    def _clipboard_watcher_worker(self, text: str) -> None:
        s = self.settings_mgr.settings
        try:
            translated = self.translation_mgr.translate(
                text=text,
                source_lang=s.source_lang,
                target_lang=s.target_lang,
                provider_name=s.provider,
                api_key=s.api_key,
                extra_settings=s.to_dict()
            )
            # Display overlay via main thread signal
            self._show_overlay_signal.emit(translated)
            self.history_mgr.add(text, translated, s.source_lang, s.target_lang)
            logger.info(f"Clipboard watcher translated: '{text}' -> '{translated}'")
        except Exception as e:
            logger.error(f"Clipboard watcher translation failed: {e}")



    @Slot()
    def _on_voice_started(self) -> None:
        s = self.settings_mgr.settings
        from app.config import ACCENT_COLORS
        accent = ACCENT_COLORS.get(s.accent_color, "#5CB868")
        self.voice_indicator.set_accent(accent)
        self.voice_indicator.show_listening(s.voice_hotkey.upper())

        if s.continuous_voice:
            if self.voice_action:
                self.voice_action.setText("Stop Continuous Voice (Listening...)")
            if not getattr(self, "_voice_started_notified", False):
                self.tray.show_notification("Continuous Voice Translate", "Continuous listening active... Speak now.")
                self._voice_started_notified = True
        else:
            if self.voice_action:
                self.voice_action.setText("Stop Voice Translate (Listening...)")

    @Slot()
    def _on_voice_transcribing(self) -> None:
        self.voice_indicator.show_transcribing()

    @Slot()
    def _on_voice_stopped(self) -> None:
        self._voice_started_notified = False
        self.voice_indicator.hide_indicator()
        if self.voice_action:
            self.voice_action.setText("Voice Translate (Mic)")

    def _on_voice_finished(self, text: str) -> None:
        self._on_voice_transcribed(text)

    def _on_voice_error(self, msg: str) -> None:
        self.voice_indicator.hide_indicator()
        self.tray.show_notification("Voice Translate Error", msg, is_error=True)

    @Slot()
    def trigger_voice_translation(self) -> None:
        """Trigger voice recording for speech translation (toggle ON/OFF)."""
        s = self.settings_mgr.settings
        if self.voice_service._is_recording:
            logger.info("Toggling voice translation OFF...")
            self.voice_service.stop_recording()
            self.voice_indicator.hide_indicator()
        else:
            logger.info("Toggling voice translation ON...")
            self.voice_service.start_recording(
                language=s.source_lang,
                continuous=s.continuous_voice,
                silence_duration=s.voice_silence_duration,
                start_timeout=s.voice_start_timeout,
                sensitivity=s.voice_sensitivity
            )

    def _on_voice_transcribed(self, text: str) -> None:
        """Translate transcribed speech and output it."""
        s = self.settings_mgr.settings
        # Run translation in thread
        threading.Thread(target=self._voice_translate_worker, args=(text,), daemon=True).start()

    def _voice_translate_worker(self, text: str) -> None:
        s = self.settings_mgr.settings
        try:
            translated = self.translation_mgr.translate(
                text=text,
                source_lang=s.source_lang,
                target_lang=s.target_lang,
                provider_name=s.provider,
                api_key=s.api_key,
                extra_settings=s.to_dict()
            )
            # Temporarily ignore keyboard events during simulation
            self.keyboard_mgr._ignore_events = True

            # Temporarily disable clipboard watcher to prevent feedback loop
            was_watcher_enabled = self.clipboard_watcher._enabled
            if was_watcher_enabled:
                self.clipboard_watcher.stop()

            # Store original clipboard text to restore later
            original_clipboard = ClipboardHelper.paste()

            # Copy translated text and paste it via Ctrl+V
            ClipboardHelper.copy(translated)
            time.sleep(0.05)
            import keyboard as kb
            kb.send("ctrl+v")
            time.sleep(0.15)

            # Restore original clipboard
            ClipboardHelper.copy(original_clipboard)
            
            if was_watcher_enabled:
                self.clipboard_watcher.start()

            self.history_mgr.add(f"[Voice] {text}", translated, s.source_lang, s.target_lang)
            # Emit signal so overlay is shown on the main (GUI) thread
            self._show_overlay_signal.emit(f"Voice: {translated}")
        except Exception as e:
            logger.error(f"Voice translation failed: {e}")
            self.tray.show_notification("Voice Translate Error", str(e), is_error=True)
        finally:
            # Always restore keyboard event listening
            self.keyboard_mgr._ignore_events = False

    @Slot()
    def quit_app(self) -> None:
        """Stop watchers and exit app cleanly."""
        logger.info("Exiting application...")
        self.keyboard_mgr.stop()
        self.clipboard_watcher.stop()
        QApplication.quit()


def main():
    # Setup PySide6 Application
    app = QApplication(sys.argv)
    app.setWindowIcon(get_icon("app_logo", size=64))

    # Single instance guard using QLocalSocket / QLocalServer
    server_name = "GlotWeave_SingleInstance_Lock"
    socket = QLocalSocket()
    socket.connectToServer(server_name)
    if socket.waitForConnected(500):
        socket.disconnectFromServer()
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Icon.Information)
        msg_box.setWindowTitle(APP_NAME)
        msg_box.setText(f"{APP_NAME} is already running!")
        msg_box.setInformativeText("GlotWeave is already active in the system tray background.")
        msg_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg_box.setWindowIcon(get_icon("app_logo", size=64))
        msg_box.exec()
        sys.exit(0)

    # Start QLocalServer for this primary instance
    local_server = QLocalServer()
    QLocalServer.removeServer(server_name)
    local_server.listen(server_name)
    
    # Hide application window from taskbar, only show in tray if requested
    # Or keep it in background
    app.setQuitOnLastWindowClosed(False)

    # Initialize Coordinator
    coordinator = TranslatorApp()

    # If another instance attempts to open, bring up settings window in existing app
    def _on_secondary_instance_launched():
        conn = local_server.nextPendingConnection()
        if conn:
            conn.close()
        coordinator.show_settings()

    local_server.newConnection.connect(_on_secondary_instance_launched)

    # Autostart / Minimized check from CLI or settings
    is_minimized = "--minimized" in sys.argv or coordinator.settings_mgr.settings.start_minimized
    if not is_minimized:
        coordinator.show_settings()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
