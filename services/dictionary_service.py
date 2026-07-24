import logging
import requests
import re
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class DictionaryService:
    """
    Fetches word definitions, parts of speech (noun, verb, etc.), and multiple translation 
    meanings for individual words using translation dictionary endpoints with caching.
    """

    def __init__(self):
        self._cache: Dict[tuple[str, str, str], Dict[str, Any]] = {}

    def lookup_word(self, word: str, source_lang: str = "auto", target_lang: str = "ar") -> Optional[Dict[str, Any]]:
        """
        Looks up a single word and returns structured dictionary details.
        
        :param word: The target word to look up.
        :param source_lang: Language of the word (e.g., 'en', 'auto').
        :param target_lang: Language for definitions/translations (e.g., 'ar', 'en').
        :return: Dictionary object containing POS, meanings, and synonyms.
        """
        cleaned_word = re.sub(r'^[^\w]+|[^\w]+$', '', word, flags=re.UNICODE)
        if not cleaned_word or len(cleaned_word) < 1:
            return None

        cache_key = (cleaned_word.lower(), source_lang, target_lang)
        if cache_key in self._cache:
            return self._cache[cache_key]

        sl = "auto" if source_lang == "auto" else source_lang
        tl = target_lang

        try:
            url = "https://translate.googleapis.com/translate_a/single"
            params = {
                "client": "gtx",
                "sl": sl,
                "tl": tl,
                "dt": ["t", "bd", "at", "md"],
                "q": cleaned_word
            }
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            response = requests.get(url, params=params, headers=headers, timeout=3.5)
            
            if response.status_code == 200:
                data = response.json()
                parsed = self._parse_google_dict_response(cleaned_word, data, target_lang)
                if parsed:
                    self._cache[cache_key] = parsed
                    return parsed
        except Exception as e:
            logger.warning(f"Dictionary lookup failed for '{cleaned_word}': {e}")

        # Fallback response if web dict endpoint fails or returns empty POS list
        fallback = {
            "word": cleaned_word,
            "translation": "",
            "pos_entries": []
        }
        return fallback

    def _parse_google_dict_response(self, word: str, data: Any, target_lang: str) -> Dict[str, Any]:
        """Parses Google Translate API single endpoint dictionary JSON structure."""
        primary_translation = ""
        pos_entries: List[Dict[str, Any]] = []

        # 1. Primary translation segment
        if data and len(data) > 0 and data[0]:
            seg_list = []
            for seg in data[0]:
                if seg and len(seg) > 0 and seg[0]:
                    seg_list.append(seg[0])
            primary_translation = "".join(seg_list).strip()

        # 2. Dictionary details (POS, meanings, synonyms) in data[1]
        if len(data) > 1 and data[1]:
            for group in data[1]:
                if not group or len(group) < 2:
                    continue
                
                pos_name = str(group[0]).strip()  # e.g., "noun", "verb", "adjective"
                meanings_list = group[1] if isinstance(group[1], list) else []
                
                meanings = []
                for m in meanings_list:
                    if isinstance(m, str) and m.strip():
                        meanings.append(m.strip())
                
                # Check for synonyms if available in data[1][i][2] or nested
                synonyms = []
                if len(group) > 2 and isinstance(group[2], list):
                    for syn_entry in group[2]:
                        if isinstance(syn_entry, list) and len(syn_entry) > 0:
                            if isinstance(syn_entry[0], list):
                                synonyms.extend([s for s in syn_entry[0] if isinstance(s, str)])
                            elif isinstance(syn_entry[0], str):
                                synonyms.append(syn_entry[0])

                if meanings:
                    pos_entries.append({
                        "pos": pos_name,
                        "meanings": meanings[:6],  # limit to top 6 meanings per POS
                        "synonyms": synonyms[:8]   # limit to top 8 synonyms
                    })

        # 3. Alternative translations in data[5] if pos_entries was empty
        if not pos_entries and len(data) > 5 and data[5]:
            alt_meanings = []
            for item in data[5]:
                if item and len(item) > 2 and item[2]:
                    for sub in item[2]:
                        if len(sub) > 0 and sub[0]:
                            alt_meanings.append(sub[0])
            if alt_meanings:
                pos_entries.append({
                    "pos": "meanings",
                    "meanings": alt_meanings[:6],
                    "synonyms": []
                })

        return {
            "word": word,
            "translation": primary_translation,
            "pos_entries": pos_entries
        }
