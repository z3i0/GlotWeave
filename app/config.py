import os
import sys
from pathlib import Path

# Application metadata
APP_NAME = "GlotWeave"
APP_VERSION = "1.1.0"
DEVELOPER = "Z3AMA"

def get_asset_path(relative_path: str | Path) -> Path:
    """Returns absolute Path to a resource file, works in dev & PyInstaller frozen mode."""
    if getattr(sys, 'frozen', False):
        base_path = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
    else:
        base_path = Path(__file__).resolve().parent.parent
    return base_path / relative_path

# Paths
HOME_DIR = Path.home() / ".glotweave"
HOME_DIR.mkdir(parents=True, exist_ok=True)

SETTINGS_FILE = HOME_DIR / "settings.json"
HISTORY_FILE = HOME_DIR / "history.json"
LOG_FILE = HOME_DIR / "app.log"

# Supported Languages
LANGUAGES = {
    "auto": "Auto Detect",
    "en": "English",
    "ar": "Arabic",
    "fr": "French",
    "es": "Spanish",
    "de": "German",
    "zh": "Chinese",
    "ja": "Japanese",
    "tr": "Turkish",
    "it": "Italian",
    "pt": "Portuguese",
    "ru": "Russian",
    "ko": "Korean",
    "hi": "Hindi",
    "nl": "Dutch",
    "pl": "Polish",
    "uk": "Ukrainian",
    "id": "Indonesian",
    "sv": "Swedish",
    "da": "Danish",
    "fi": "Finnish",
    "el": "Greek",
    "he": "Hebrew",
    "th": "Thai",
    "vi": "Vietnamese",
}

# Translation Providers
PROVIDERS = {
    "google_free": "Google Translate (Free)",
    "google_cloud": "Google Cloud Translation",
    "deepl": "DeepL API",
    "openai": "OpenAI (GPT-4o/GPT-3.5)",
    "gemini": "Gemini API",
    "ollama": "Ollama (Offline LLM)",
}

# Accent colors available (including original green logo color)
ACCENT_COLORS = {
    "green":   "#5CB868",
    "cyan":    "#00ADB5",
    "purple":  "#9B59B6",
    "orange":  "#E67E22",
    "pink":    "#E91E8C",
    "blue":    "#2980B9",
}

# Default settings
DEFAULT_SETTINGS = {
    "auto_start": False,
    "start_minimized": False,
    "live_translation": False,
    "translate_selected": True,
    "clipboard_monitor": False,
    "translate_on_layout_switch": False,
    "continuous_voice": False,
    "voice_silence_duration": 1.0,
    "voice_sensitivity": "medium",
    "voice_start_timeout": 3.0,
    "auto_detect": True,
    "hotkey": "ctrl+shift+f9",
    "voice_hotkey": "ctrl+shift+f10",
    "quick_translate_hotkey": "ctrl+shift+q",
    "source_lang": "auto",
    "target_lang": "en",
    "provider": "google_free",
    "api_key": "",
    "theme": "dark",
    "accent_color": "green",
    "notifications": True,
    "ollama_url": "http://localhost:11434",
    "ollama_model": "llama3",
    "deepl_url": "https://api-free.deepl.com",
    "overlay_duration": 4000,
    "overlay_opacity": 90,
    "live_caption_enabled": False,
    "live_caption_source_lang": "auto",
    "live_caption_target_lang": "ar",
    "live_caption_dual_mode": True,
    "live_caption_hotkey": "ctrl+shift+l",
    "live_caption_audio_source": "system",
    "live_caption_vad_aggressiveness": 2,
    "live_caption_silence_timeout": 0.35,
    "live_caption_max_phrase_duration": 3.0,
    "live_caption_queue_maxsize": 10,
    "live_caption_overlap_duration": 0.3,
    "live_caption_retry_delay": 0.1,
    "live_caption_num_workers": 3,
}
