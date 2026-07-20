import logging
import requests
from typing import Optional
from core.translator import TranslationProvider, TranslationError

logger = logging.getLogger(__name__)


class OllamaTranslateProvider(TranslationProvider):
    """Offline translation provider using a local Ollama server."""

    def translate(self, text: str, source_lang: str, target_lang: str, api_key: str = "", extra_settings: Optional[dict] = None) -> str:
        # Resolve config from settings
        url = "http://localhost:11434"
        model = "llama3"
        
        if extra_settings:
            url = extra_settings.get("ollama_url", url)
            model = extra_settings.get("ollama_model", model)

        # Build prompt instructing the local LLM to do direct translation
        # Prompt needs to be strict so the LLM doesn't output conversational text
        prompt = (
            f"You are a professional translator. Translate the following text from "
            f"'{source_lang}' to '{target_lang}'. Do not add any explanations, introductory text, "
            f"markdown code blocks, or formatting. Output only the raw translation itself:\n\n{text}"
        )

        try:
            endpoint = f"{url.rstrip('/')}/api/generate"
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.0  # Make results deterministic
                }
            }
            # Give a longer timeout since LLM generation takes a bit more time
            response = requests.post(endpoint, json=payload, timeout=10.0)
            if response.status_code == 200:
                data = response.json()
                translated = data.get("response", "").strip()
                if translated:
                    return translated
            else:
                raise TranslationError(f"Ollama returned HTTP status {response.status_code}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to connect to local Ollama server at {url}: {e}")
            raise TranslationError(f"Ollama server connection error. Ensure Ollama is running: {e}")
        except Exception as e:
            logger.error(f"Unexpected Ollama translation failure: {e}")
            raise TranslationError(f"Ollama error: {e}")

        raise TranslationError("Ollama failed to return a translation response.")
