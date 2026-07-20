import logging
import requests
from typing import Optional
from core.translator import TranslationProvider, TranslationError

logger = logging.getLogger(__name__)


class GoogleCloudTranslateProvider(TranslationProvider):
    """Google Cloud Translation API v2 Provider."""

    def translate(self, text: str, source_lang: str, target_lang: str, api_key: str = "", extra_settings: Optional[dict] = None) -> str:
        if not api_key:
            raise TranslationError("Google Cloud API Key is missing. Set it in Settings.")

        url = "https://translation.googleapis.com/language/translate/v2"
        params = {"key": api_key}
        payload = {
            "q": text,
            "target": target_lang,
            "format": "text"
        }
        if source_lang != "auto":
            payload["source"] = source_lang

        try:
            response = requests.post(url, params=params, json=payload, timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                translations = data.get("data", {}).get("translations", [])
                if translations:
                    return translations[0].get("translatedText", "")
            else:
                raise TranslationError(f"API Error {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"Google Cloud Translate API failed: {e}")
            raise TranslationError(f"Google Cloud Translate failed: {e}")

        raise TranslationError("Google Cloud Translation API returned empty results.")


class DeepLTranslateProvider(TranslationProvider):
    """DeepL Translation API Provider."""

    def translate(self, text: str, source_lang: str, target_lang: str, api_key: str = "", extra_settings: Optional[dict] = None) -> str:
        if not api_key:
            raise TranslationError("DeepL Auth Key is missing. Set it in Settings.")

        # Default URL is Free, but can be Pro
        base_url = "https://api-free.deepl.com"
        if extra_settings:
            base_url = extra_settings.get("deepl_url", base_url)
        
        url = f"{base_url.rstrip('/')}/v2/translate"
        headers = {
            "Authorization": f"DeepL-Auth-Key {api_key}",
            "Content-Type": "application/json"
        }
        
        # DeepL expects uppercase language codes (e.g., 'EN', 'AR')
        # Also supports 'EN-US' or 'EN-GB' as target languages, let's keep it simple
        sl = None if source_lang == "auto" else source_lang.upper()
        tl = target_lang.upper()

        payload = {
            "text": [text],
            "target_lang": tl
        }
        if sl:
            payload["source_lang"] = sl

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=5.0)
            if response.status_code == 200:
                data = response.json()
                translations = data.get("translations", [])
                if translations:
                    return translations[0].get("text", "")
            else:
                raise TranslationError(f"DeepL API Error {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"DeepL API failed: {e}")
            raise TranslationError(f"DeepL failed: {e}")

        raise TranslationError("DeepL API returned empty results.")


class OpenAITranslateProvider(TranslationProvider):
    """OpenAI API Translation Provider using chat/completions."""

    def translate(self, text: str, source_lang: str, target_lang: str, api_key: str = "", extra_settings: Optional[dict] = None) -> str:
        if not api_key:
            raise TranslationError("OpenAI API Key is missing. Set it in Settings.")

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        # Keep temperature low for direct translation fidelity
        model = "gpt-4o-mini"  # Cost-effective, fast, high performance
        system_prompt = (
            f"You are a professional translator. Translate the user text from '{source_lang}' to '{target_lang}'. "
            f"Do not write any notes, introductory phrases, or conversational explanations. Output only the translated text."
        )

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text}
            ],
            "temperature": 0.0
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=8.0)
            if response.status_code == 200:
                data = response.json()
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "").strip()
            else:
                raise TranslationError(f"OpenAI API Error {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            raise TranslationError(f"OpenAI translation failed: {e}")

        raise TranslationError("OpenAI API returned empty results.")


class GeminiTranslateProvider(TranslationProvider):
    """Gemini API Translation Provider using developers API endpoint."""

    def translate(self, text: str, source_lang: str, target_lang: str, api_key: str = "", extra_settings: Optional[dict] = None) -> str:
        if not api_key:
            raise TranslationError("Gemini API Key is missing. Set it in Settings.")

        # Using gemini-1.5-flash as default (fast and responsive)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        
        prompt = (
            f"Translate the following text from '{source_lang}' to '{target_lang}'. "
            f"Do not add any preamble, footnotes, formatting, or commentary. Output only the translation:\n\n{text}"
        )

        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.1
            }
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=8.0)
            if response.status_code == 200:
                data = response.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "").strip()
            else:
                raise TranslationError(f"Gemini API Error {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"Gemini API call failed: {e}")
            raise TranslationError(f"Gemini translation failed: {e}")

        raise TranslationError("Gemini API returned empty results.")
