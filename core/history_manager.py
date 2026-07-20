import json
import os
import logging
import csv
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import List, Dict, Any

from app.config import HISTORY_FILE

logger = logging.getLogger(__name__)


@dataclass
class HistoryItem:
    """Represents a single translation entry."""
    original: str
    translated: str
    source_lang: str
    target_lang: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    favorite: bool = False
    id: str = field(default_factory=lambda: str(datetime.now().timestamp()))

    def to_dict(self) -> Dict[str, Any]:
        """Convert history item to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HistoryItem":
        """Create a HistoryItem instance from a dictionary."""
        return cls(
            original=data.get("original", ""),
            translated=data.get("translated", ""),
            source_lang=data.get("source_lang", ""),
            target_lang=data.get("target_lang", ""),
            timestamp=data.get("timestamp", datetime.now().isoformat()),
            favorite=data.get("favorite", False),
            id=data.get("id", str(datetime.now().timestamp()))
        )


class HistoryManager:
    """Manages the list of translation history items up to 1000 entries."""

    def __init__(self, filepath: str = str(HISTORY_FILE)):
        self.filepath = filepath
        self.history: List[HistoryItem] = []
        self.load()

    def load(self) -> List[HistoryItem]:
        """Load history from the JSON file."""
        try:
            if os.path.exists(self.filepath):
                with open(self.filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.history = [HistoryItem.from_dict(item) for item in data]
                logger.info(f"Loaded {len(self.history)} history records.")
            else:
                self.history = []
        except Exception as e:
            logger.error(f"Failed to load history: {e}")
            self.history = []
        return self.history

    def save(self) -> bool:
        """Save history back to the JSON file."""
        try:
            # Maintain maximum limit of 1000 entries
            if len(self.history) > 1000:
                self.history = self.history[:1000]
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump([item.to_dict() for item in self.history], f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            logger.error(f"Failed to save history: {e}")
            return False

    def add(self, original: str, translated: str, source_lang: str, target_lang: str) -> None:
        """Add a new translation record to history (inserted at the beginning)."""
        item = HistoryItem(
            original=original,
            translated=translated,
            source_lang=source_lang,
            target_lang=target_lang
        )
        self.history.insert(0, item)
        self.save()

    def delete(self, item_id: str) -> bool:
        """Remove a translation record by its ID."""
        initial_len = len(self.history)
        self.history = [item for item in self.history if item.id != item_id]
        if len(self.history) < initial_len:
            self.save()
            return True
        return False

    def toggle_favorite(self, item_id: str) -> bool:
        """Toggle the favorite status of a translation record."""
        for item in self.history:
            if item.id == item_id:
                item.favorite = not item.favorite
                self.save()
                return True
        return False

    def clear(self) -> None:
        """Clear all translation history."""
        self.history = []
        self.save()

    def search(self, query: str) -> List[HistoryItem]:
        """Search translations by original or translated text."""
        if not query:
            return self.history
        query = query.lower()
        return [
            item for item in self.history
            if query in item.original.lower() or query in item.translated.lower()
        ]

    def export_csv(self, filepath: str) -> bool:
        """Export history entries to a CSV file."""
        try:
            with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["Timestamp", "Original", "Translated", "Source", "Target", "Favorite"])
                for item in self.history:
                    writer.writerow([
                        item.timestamp,
                        item.original,
                        item.translated,
                        item.source_lang,
                        item.target_lang,
                        item.favorite
                    ])
            return True
        except Exception as e:
            logger.error(f"Failed to export history to CSV: {e}")
            return False
