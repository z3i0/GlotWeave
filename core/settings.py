import json
import logging
import os
import sys
from dataclasses import dataclass, asdict
from typing import Dict, Any

from app.config import SETTINGS_FILE, DEFAULT_SETTINGS

logger = logging.getLogger(__name__)

# Try importing winreg for Windows Autostart registry integration
IS_WINDOWS = sys.platform == "win32"
if IS_WINDOWS:
    import winreg
else:
    winreg = None


@dataclass
class Settings:
    """Dataclass holding all application configurations."""
    auto_start: bool = bool(DEFAULT_SETTINGS["auto_start"])
    start_minimized: bool = bool(DEFAULT_SETTINGS["start_minimized"])
    live_translation: bool = bool(DEFAULT_SETTINGS["live_translation"])
    translate_selected: bool = bool(DEFAULT_SETTINGS["translate_selected"])
    clipboard_monitor: bool = bool(DEFAULT_SETTINGS["clipboard_monitor"])
    translate_on_layout_switch: bool = bool(DEFAULT_SETTINGS["translate_on_layout_switch"])
    continuous_voice: bool = bool(DEFAULT_SETTINGS["continuous_voice"])
    voice_silence_duration: float = float(DEFAULT_SETTINGS["voice_silence_duration"])
    voice_sensitivity: str = str(DEFAULT_SETTINGS["voice_sensitivity"])
    voice_start_timeout: float = float(DEFAULT_SETTINGS["voice_start_timeout"])
    auto_detect: bool = bool(DEFAULT_SETTINGS["auto_detect"])
    hotkey: str = str(DEFAULT_SETTINGS["hotkey"])
    voice_hotkey: str = str(DEFAULT_SETTINGS["voice_hotkey"])
    quick_translate_hotkey: str = str(DEFAULT_SETTINGS["quick_translate_hotkey"])
    source_lang: str = str(DEFAULT_SETTINGS["source_lang"])
    target_lang: str = str(DEFAULT_SETTINGS["target_lang"])
    provider: str = str(DEFAULT_SETTINGS["provider"])
    api_key: str = str(DEFAULT_SETTINGS["api_key"])
    theme: str = str(DEFAULT_SETTINGS["theme"])
    accent_color: str = str(DEFAULT_SETTINGS["accent_color"])
    notifications: bool = bool(DEFAULT_SETTINGS["notifications"])
    ollama_url: str = str(DEFAULT_SETTINGS["ollama_url"])
    ollama_model: str = str(DEFAULT_SETTINGS["ollama_model"])
    deepl_url: str = str(DEFAULT_SETTINGS["deepl_url"])
    overlay_duration: int = int(DEFAULT_SETTINGS["overlay_duration"])
    overlay_opacity: int = int(DEFAULT_SETTINGS["overlay_opacity"])

    def to_dict(self) -> Dict[str, Any]:
        """Convert settings to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Settings":
        """Create a Settings instance from a dictionary filtering out unknown keys."""
        valid_keys = cls.__dataclass_fields__.keys()
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)


class SettingsManager:
    """Manages application settings loading, saving, and OS integrations."""

    def __init__(self, filepath: str = str(SETTINGS_FILE)):
        self.filepath = filepath
        self.settings = Settings()
        self.load()

    def load(self) -> Settings:
        """Load settings from the JSON configuration file."""
        try:
            if os.path.exists(self.filepath):
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.settings = Settings.from_dict(data)
                logger.info("Settings loaded successfully.")
            else:
                logger.info("Settings file not found. Using defaults.")
                self.settings = Settings()
                self.save()
        except Exception as e:
            logger.error(f"Failed to load settings: {e}. Falling back to defaults.")
            self.settings = Settings()
        return self.settings

    def save(self, settings: Settings | None = None) -> bool:
        """Save settings to the JSON configuration file."""
        if settings:
            self.settings = settings
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(self.settings.to_dict(), f, indent=4, ensure_ascii=False)
            logger.info("Settings saved successfully.")

            # Apply OS level configurations like autostart
            self._apply_autostart()
            return True
        except Exception as e:
            logger.error(f"Failed to save settings: {e}")
            return False

    def _apply_autostart(self) -> None:
        """Add or remove Windows Registry entries for Startup."""
        if not IS_WINDOWS or not winreg:
            return

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "GlotWeave"

        if getattr(sys, 'frozen', False):
            cmd = f'"{sys.executable}" --minimized'
        else:
            main_script = os.path.abspath(sys.argv[0])
            python_exe = sys.executable.replace("python.exe", "pythonw.exe")
            cmd = f'"{python_exe}" "{main_script}" --minimized'

        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
            if self.settings.auto_start:
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
                logger.info("Added GlotWeave registry entry for Autostart.")
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                    logger.info("Removed GlotWeave registry entry for Autostart.")
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            logger.error(f"Failed to update Autostart registry key: {e}")
