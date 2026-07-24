import logging
import time
# pyrefly: ignore [missing-import]
from PySide6.QtCore import QObject, Signal, Slot
import keyboard

logger = logging.getLogger(__name__)


class KeyboardManager(QObject):
    """Manages global keyboard hooks, hotkeys, and live typing buffers."""
    hotkey_triggered = Signal()
    voice_hotkey_triggered = Signal()
    live_caption_hotkey_triggered = Signal()
    layout_switch_triggered = Signal()
    live_translate_triggered = Signal(str, int)  # (sentence_to_translate, characters_to_delete)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_running = False
        self._hotkey_hook = None
        self._live_typing_hook = None
        self._current_hotkey = "ctrl+shift+f9"
        self._current_voice_hotkey = "ctrl+shift+f10"
        self._current_caption_hotkey = "ctrl+shift+l"
        self._ignore_events = False
        self._enable_layout_switch = False
        
        # Buffer to keep track of typed characters for live translation
        self._typed_buffer = []
        self._word_characters = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'\"-"
        
        # Special keys that reset the buffer because they change cursor position
        self._reset_keys = {
            "delete", "left", "right", "up", "down",
            "home", "end", "page up", "page down", "escape", "tab"
        }

    def start(self, hotkey: str, voice_hotkey: str, enable_live: bool, enable_layout_switch: bool = False, caption_hotkey: str = "ctrl+shift+l") -> None:
        """Start global keyboard listeners."""
        self.stop()
        self._current_hotkey = hotkey.lower()
        self._current_voice_hotkey = voice_hotkey.lower()
        self._current_caption_hotkey = caption_hotkey.lower()
        self._enable_layout_switch = enable_layout_switch
        self._is_running = True

        try:
            keyboard.add_hotkey(self._current_hotkey, self._on_hotkey, suppress=False)
            logger.info(f"Registered global hotkey: {self._current_hotkey}")
        except Exception as e:
            logger.error(f"Failed to register global hotkey '{self._current_hotkey}': {e}")

        try:
            keyboard.add_hotkey(self._current_voice_hotkey, self._on_voice_hotkey, suppress=False)
            logger.info(f"Registered global voice hotkey: {self._current_voice_hotkey}")
        except Exception as e:
            logger.error(f"Failed to register global voice hotkey '{self._current_voice_hotkey}': {e}")

        try:
            keyboard.add_hotkey(self._current_caption_hotkey, self._on_caption_hotkey, suppress=False)
            logger.info(f"Registered global caption hotkey: {self._current_caption_hotkey}")
        except Exception as e:
            logger.error(f"Failed to register global caption hotkey '{self._current_caption_hotkey}': {e}")

        if enable_layout_switch:
            for hk in ["alt+shift", "shift+alt", "windows+space"]:
                try:
                    keyboard.add_hotkey(hk, self._on_layout_switch_hotkey, suppress=False)
                except Exception as e:
                    logger.debug(f"Failed to register layout switch hotkey '{hk}': {e}")
            logger.info("Registered keyboard layout switch listeners (Alt+Shift / Win+Space).")

        if enable_live:
            self._start_live_typing()

    def stop(self) -> None:
        """Stop all keyboard hooks."""
        self._is_running = False
        try:
            keyboard.unhook_all()
            logger.info("Unregistered all keyboard hooks.")
        except Exception as e:
            logger.error(f"Error unhooking keyboard: {e}")
        self._typed_buffer.clear()

    def update_settings(self, hotkey: str, voice_hotkey: str, enable_live: bool, enable_layout_switch: bool = False, caption_hotkey: str = "ctrl+shift+l") -> None:
        """Update hotkey and live typing status dynamically."""
        self.start(hotkey, voice_hotkey, enable_live, enable_layout_switch, caption_hotkey)

    def _on_layout_switch_hotkey(self) -> None:
        """Callback when keyboard layout switch is triggered by user."""
        if not self._is_running or self._ignore_events or not self._enable_layout_switch:
            return
        logger.info("Keyboard layout switch hotkey triggered.")
        self.layout_switch_triggered.emit()

    def _on_hotkey(self) -> None:
        """Callback when hotkey is triggered."""
        if not self._is_running or self._ignore_events:
            return
        logger.info("Global hotkey triggered.")
        self.hotkey_triggered.emit()

    def _on_voice_hotkey(self) -> None:
        """Callback when voice hotkey is triggered."""
        if not self._is_running or self._ignore_events:
            return
        logger.info("Global voice hotkey triggered.")
        self.voice_hotkey_triggered.emit()

    def _on_caption_hotkey(self) -> None:
        """Callback when Live Caption hotkey is triggered."""
        if not self._is_running or self._ignore_events:
            return
        logger.info("Global Live Caption hotkey triggered.")
        self.live_caption_hotkey_triggered.emit()

    def _start_live_typing(self) -> None:
        """Setup keyboard hook for live typing."""
        try:
            self._live_typing_hook = keyboard.on_press(self._on_key_press)
            logger.info("Live typing hook active.")
        except Exception as e:
            logger.error(f"Failed to activate live typing hook: {e}")

    def _on_key_press(self, event: keyboard.KeyboardEvent) -> None:
        """Process individual key presses for live translation buffer."""
        if not self._is_running or self._ignore_events or not event.name:
            return

        name = event.name.lower()
        
        if name in self._reset_keys:
            self._typed_buffer.clear()
            return

        if name == "backspace":
            if self._typed_buffer:
                self._typed_buffer.pop()
            return

        # Ignore modifier keys alone and reset buffer on layout change keys (alt/shift/win)
        if name in {"ctrl", "shift", "alt", "windows", "left ctrl", "right ctrl", "left shift", "right shift", "left alt", "right alt", "left windows", "right windows"}:
            if "alt" in name or "shift" in name or "windows" in name:
                self._typed_buffer.clear()
            return

        # If it's a character or trigger, record it
        char = None
        if len(name) == 1:
            char = event.name
            self._typed_buffer.append(char)
        elif name == "space":
            char = " "
            self._typed_buffer.append(char)
            # Check for double space (two consecutive spaces)
            if len(self._typed_buffer) >= 2 and self._typed_buffer[-2] == " ":
                self._trigger_immediate_live_translation()
                return
        elif name == "enter":
            char = "\n"
            self._typed_buffer.append(char)

    def _trigger_immediate_live_translation(self) -> None:
        """Trigger translation immediately (e.g. on double space)."""
        if not self._is_running or not self._typed_buffer:
            return

        full_text = "".join(self._typed_buffer)
        sentence = full_text.strip()
        
        # Require at least 2 characters to avoid translating single letters/spaces
        if len(sentence) < 2:
            self._typed_buffer.clear()
            return

        backspace_count = len(self._typed_buffer)
        logger.info(f"Live typing double-space matched: '{sentence}' (deleting {backspace_count} chars)")
        
        self.live_translate_triggered.emit(sentence, backspace_count)
        self._typed_buffer.clear()
