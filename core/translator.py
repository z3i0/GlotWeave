import logging
from abc import ABC, abstractmethod
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)


class TranslationError(Exception):
    """Base exception for translation errors."""
    pass


class TranslationProvider(ABC):
    """Abstract interface for all translation engines."""

    @abstractmethod
    def translate(self, text: str, source_lang: str, target_lang: str, api_key: str = "", extra_settings: Optional[dict] = None) -> str:
        """
        Translate the given text.

        :param text: The text to translate.
        :param source_lang: The source language code (e.g. 'en', 'ar', 'auto').
        :param target_lang: The target language code (e.g. 'en', 'ar').
        :param api_key: The API key for providers requiring authentication.
        :param extra_settings: Optional provider-specific configurations.
        :return: The translated text string.
        :raises TranslationError: If translation fails.
        """
        pass


class TranslationManager:
    """Manages translation caching, provider routing, and automatic language detection."""

    def __init__(self):
        self._providers: Dict[str, TranslationProvider] = {}
        self._cache: Dict[Tuple[str, str, str, str], str] = {}  # Cache key: (provider, text, src, target)
        self.detector = None  # Injected later

    def register_provider(self, name: str, provider: TranslationProvider) -> None:
        """Register a translation provider."""
        self._providers[name] = provider
        logger.info(f"Registered translation provider: {name}")

    def set_language_detector(self, detector) -> None:
        """Inject language detector service."""
        self.detector = detector

    def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        provider_name: str,
        api_key: str = "",
        extra_settings: Optional[dict] = None
    ) -> str:
        """
        Translate text using the specified provider with caching and auto detection.
        """
        stripped_text = text.strip()
        if not stripped_text:
            return ""

        # Auto detection if enabled or source_lang is 'auto'
        detected_lang = source_lang
        if source_lang == "auto" and self.detector:
            try:
                detected_lang = self.detector.detect(stripped_text)
                logger.info(f"Auto-detected language for translation: {detected_lang}")
            except Exception as e:
                logger.warning(f"Language detection failed, using fallback source language: {e}")
                detected_lang = "en"

        # If source and target are the same, return as is
        if detected_lang == target_lang:
            return text

        # Cache lookup
        cache_key = (provider_name, stripped_text, detected_lang, target_lang)
        if cache_key in self._cache:
            logger.info("Translation cache hit.")
            return self._cache[cache_key]

        provider = self._providers.get(provider_name)
        if not provider:
            raise TranslationError(f"Provider '{provider_name}' is not registered.")

        # Translate
        try:
            translated = provider.translate(
                stripped_text,
                detected_lang,
                target_lang,
                api_key=api_key,
                extra_settings=extra_settings
            )
            # Retain formatting of original text (leading/trailing whitespace)
            result = text.replace(stripped_text, translated, 1)
            self._cache[cache_key] = result
            return result
        except Exception as e:
            logger.error(f"Translation failed using provider {provider_name}: {e}")
            raise TranslationError(f"Provider {provider_name} error: {e}")

    def clear_cache(self) -> None:
        """Clear the translation cache."""
        self._cache.clear()
        logger.info("Translation cache cleared.")
