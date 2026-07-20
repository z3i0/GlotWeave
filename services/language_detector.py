import re
import logging
import requests

logger = logging.getLogger(__name__)


class LanguageDetector:
    """Detects the source language of text using fast heuristics and online APIs."""

    def __init__(self):
        # Compiled regex for Arabic script characters
        self.arabic_pattern = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")

    def detect(self, text: str) -> str:
        """
        Detect the language of the text. Returns ISO language code (e.g. 'ar', 'en').
        """
        if not text or not text.strip():
            return "en"

        # 1. Fast offline heuristic (Arabic vs English/Others)
        cleaned_text = text.strip()
        arabic_chars = self.arabic_pattern.findall(cleaned_text)
        
        # If there are Arabic characters in the text, evaluate the proportion
        if arabic_chars:
            total_letters = len(re.sub(r"\s+", "", cleaned_text))
            if total_letters > 0 and (len(arabic_chars) / total_letters) > 0.15:
                return "ar"
            
        # 2. Online detection fallback using Google Free Translate single endpoint
        try:
            url = "https://translate.googleapis.com/translate_a/single"
            params = {
                "client": "gtx",
                "dt": "t",
                "sl": "auto",
                "tl": "en",  # Destination doesn't matter for detection
                "q": cleaned_text
            }
            response = requests.get(url, params=params, timeout=2.0)
            if response.status_code == 200:
                data = response.json()
                # The 3rd item (index 2) of the outer array is usually the detected language code.
                if len(data) > 2 and isinstance(data[2], str):
                    detected = data[2]
                    logger.info(f"Google API detected language: {detected}")
                    return detected
        except Exception as e:
            logger.warning(f"Online language detection failed: {e}. Defaulting to English.")

        # Default fallback
        return "en"
