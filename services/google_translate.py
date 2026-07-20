import logging
import requests
from typing import Optional
from core.translator import TranslationProvider, TranslationError

logger = logging.getLogger(__name__)


class GoogleTranslateFreeProvider(TranslationProvider):
    """Google Translate Free API provider utilizing public endpoint with a googletrans library fallback."""

    def translate(self, text: str, source_lang: str, target_lang: str, api_key: str = "", extra_settings: Optional[dict] = None) -> str:
        # Normalize auto language code for Google Translate API
        sl = "auto" if source_lang == "auto" else source_lang
        tl = target_lang

        # 1. Primary Method: Web API endpoint (fast, stable, and requires no API key)
        try:
            url = "https://translate.googleapis.com/translate_a/single"
            params = {
                "client": "gtx",
                "dt": "t",
                "sl": sl,
                "tl": tl,
                "q": text
            }
            # Timeout set to 3 seconds for instant translation feel
            response = requests.get(url, params=params, timeout=3.0)
            if response.status_code == 200:
                data = response.json()
                # Google returns a list of translation segments
                translated_segments = []
                if data and len(data) > 0 and data[0]:
                    for segment in data[0]:
                        if segment and len(segment) > 0:
                            translated_segments.append(segment[0])
                
                if translated_segments:
                    return "".join(translated_segments)
            logger.warning(f"Google Free web endpoint returned status {response.status_code}")
        except Exception as e:
            logger.warning(f"Google Free web endpoint failed: {e}. Trying googletrans fallback.")

        # 2. Fallback: googletrans library
        try:
            from googletrans import Translator
            translator = Translator()
            result = translator.translate(text, src=sl, dest=tl)
            if result and result.text:
                return result.text
        except Exception as e:
            logger.error(f"Googletrans fallback library also failed: {e}")
            raise TranslationError(f"Google Free translation failed: {e}")

        raise TranslationError("Google Free translation provider failed to return a result.")
