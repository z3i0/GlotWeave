import logging
from datetime import date
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLineEdit, QListWidget,
    QListWidgetItem, QWidget, QLabel, QPushButton, QMessageBox,
    QFileDialog, QFrame
)
from core.history_manager import HistoryItem, HistoryManager
from core.clipboard import ClipboardHelper
from ui.icons import get_icon, get_pixmap

logger = logging.getLogger(__name__)


class HistoryItemWidget(QWidget):
    """Card widget for a single history record with SVG icons."""
    delete_clicked = Signal(str)
    favorite_clicked = Signal(str)

    def __init__(self, item: HistoryItem, accent: str = "#5CB868", parent=None):
        super().__init__(parent)
        self.item = item
        self._accent = accent

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(6)

        # ── Top row ───────────────────────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(6)

        # Type icon badge
        is_voice = "[Voice]" in item.original
        icon_name = "mic" if is_voice else "file_text"
        badge_text = "Voice" if is_voice else "Text"

        self.type_icon = QLabel(self)
        self.type_icon.setFixedSize(14, 14)
        self.type_icon.setPixmap(get_pixmap(icon_name, color=self._accent, size=14))
        top.addWidget(self.type_icon)

        badge = QLabel(badge_text, self)
        badge.setObjectName("HistoryBadge")
        top.addWidget(badge)

        lang_lbl = QLabel(f" {item.source_lang.upper()} → {item.target_lang.upper()}", self)
        lang_lbl.setObjectName("LangBadge")
        top.addWidget(lang_lbl)

        top.addStretch()

        # Timestamp
        try:
            ts = item.timestamp.replace("T", " ")[:16]
        except Exception:
            ts = ""
        time_lbl = QLabel(ts, self)
        time_lbl.setObjectName("TimestampLabel")
        top.addWidget(time_lbl)

        # Favorite button
        star_icon_name = "star_filled" if item.favorite else "star"
        star_color = "#E9B824" if item.favorite else "#666666"
        self.fav_btn = QPushButton(self)
        self.fav_btn.setObjectName("FavBtn")
        self.fav_btn.setFixedSize(24, 24)
        self.fav_btn.setIcon(get_icon(star_icon_name, color=star_color, size=14))
        self.fav_btn.clicked.connect(lambda: self.favorite_clicked.emit(self.item.id))
        top.addWidget(self.fav_btn)

        # Copy button
        copy_btn = QPushButton(self)
        copy_btn.setObjectName("ActionIconBtn")
        copy_btn.setFixedSize(24, 24)
        copy_btn.setIcon(get_icon("copy", color=self._accent, size=13))
        copy_btn.setToolTip("Copy translation")
        copy_btn.clicked.connect(self._copy_translation)
        top.addWidget(copy_btn)

        # Delete button
        del_btn = QPushButton(self)
        del_btn.setObjectName("DeleteBtn")
        del_btn.setFixedSize(24, 24)
        del_btn.setIcon(get_icon("trash", color="#FF5555", size=13))
        del_btn.clicked.connect(lambda: self.delete_clicked.emit(self.item.id))
        top.addWidget(del_btn)

        layout.addLayout(top)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("CardSep")
        layout.addWidget(sep)

        # Text fields
        orig_text = item.original.replace("[Voice] ", "").replace("[OCR] ", "")
        orig_lbl = QLabel(orig_text, self)
        orig_lbl.setWordWrap(True)
        orig_lbl.setObjectName("OrigLabel")
        orig_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(orig_lbl)

        trans_lbl = QLabel(item.translated, self)
        trans_lbl.setWordWrap(True)
        trans_lbl.setObjectName("TransLabel")
        trans_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(trans_lbl)

        self.setObjectName("HistoryCard")
        self._apply_style()

    def _apply_style(self) -> None:
        a = self._accent
        self.setStyleSheet(f"""
            QWidget#HistoryCard {{
                background-color: #20232C;
                border-radius: 8px;
                border: 1px solid rgba(255, 255, 255, 0.06);
            }}
            QLabel#HistoryBadge {{
                color: {a};
                font-size: 11px;
                font-weight: 600;
                font-family: 'Segoe UI';
            }}
            QLabel#LangBadge {{
                color: #777777;
                font-size: 11px;
                font-family: 'Segoe UI';
            }}
            QLabel#TimestampLabel {{
                color: #555555;
                font-size: 10px;
                font-family: 'Segoe UI';
            }}
            QPushButton#FavBtn, QPushButton#ActionIconBtn, QPushButton#DeleteBtn {{
                background: transparent;
                border: none;
                border-radius: 4px;
            }}
            QPushButton#FavBtn:hover {{ background: rgba(233, 184, 36, 0.15); }}
            QPushButton#ActionIconBtn:hover {{ background: rgba(92, 184, 104, 0.15); }}
            QPushButton#DeleteBtn:hover {{ background: rgba(255, 85, 85, 0.15); }}

            QFrame#CardSep {{ color: rgba(255, 255, 255, 0.05); }}
            QLabel#OrigLabel {{
                color: #888888;
                font-size: 12px;
                font-family: 'Segoe UI';
            }}
            QLabel#TransLabel {{
                color: #F0F0F0;
                font-size: 13px;
                font-weight: 600;
                font-family: 'Segoe UI';
            }}
        """)

    def _copy_translation(self) -> None:
        ClipboardHelper.copy(self.item.translated)


class HistoryPage(QWidget):
    """High-performance embedded History page for the main window."""

    INITIAL_LIMIT = 50  # Load 50 items initially for instant rendering

    def __init__(self, history_manager: HistoryManager, accent: str = "#5CB868", parent=None):
        super().__init__(parent)
        self.history_manager = history_manager
        self._accent = accent
        self._active_filter = "all"
        self._display_limit = self.INITIAL_LIMIT
        self._filtered_items: list[HistoryItem] = []

        self._build_ui()
        self._apply_style()

    def set_accent(self, accent: str) -> None:
        self._accent = accent
        self._apply_style()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        # ── Top Bar: Search & Stats ──────────────────────────────
        top_bar = QHBoxLayout()
        top_bar.setSpacing(10)

        self.search_input = QLineEdit(self)
        self.search_input.setObjectName("SearchInput")
        self.search_input.setPlaceholderText("Search translations...")
        self.search_input.textChanged.connect(self._on_search_changed)
        top_bar.addWidget(self.search_input, 1)

        # Stats badges
        self._stat_total = self._stat_badge("0", "Total")
        self._stat_today = self._stat_badge("0", "Today")
        self._stat_favs = self._stat_badge("0", "Saved")
        top_bar.addWidget(self._stat_total)
        top_bar.addWidget(self._stat_today)
        top_bar.addWidget(self._stat_favs)

        layout.addLayout(top_bar)

        # ── Filter Tabs ──────────────────────────────────────────
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self._filter_btns: dict[str, QPushButton] = {}
        for key, label in [("all", "All"), ("favorites", "Favorites"),
                            ("voice", "Voice"), ("text", "Text")]:
            btn = QPushButton(label, self)
            btn.setObjectName("FilterBtn")
            btn.setCheckable(True)
            btn.setChecked(key == "all")
            btn.clicked.connect(lambda checked, k=key: self._set_filter(k))
            self._filter_btns[key] = btn
            filter_row.addWidget(btn)

        filter_row.addStretch()

        self.export_btn = QPushButton("Export CSV", self)
        self.export_btn.setObjectName("FooterBtn")
        self.export_btn.setIcon(get_icon("export", color=self._accent, size=13))
        self.export_btn.clicked.connect(self._export_history)
        filter_row.addWidget(self.export_btn)

        self.clear_btn = QPushButton("Clear All", self)
        self.clear_btn.setObjectName("DangerBtn")
        self.clear_btn.setIcon(get_icon("trash", color="#FF5555", size=13))
        self.clear_btn.clicked.connect(self._clear_history)
        filter_row.addWidget(self.clear_btn)

        layout.addLayout(filter_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("HistSep")
        layout.addWidget(sep)

        # ── Fast List Widget ─────────────────────────────────────
        self.list_widget = QListWidget(self)
        self.list_widget.setObjectName("HistList")
        self.list_widget.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.list_widget.setSpacing(4)
        layout.addWidget(self.list_widget)

        # Load More Button (hidden unless needed)
        self.load_more_btn = QPushButton("Load More...", self)
        self.load_more_btn.setObjectName("LoadMoreBtn")
        self.load_more_btn.hide()
        self.load_more_btn.clicked.connect(self._load_more)
        layout.addWidget(self.load_more_btn, alignment=Qt.AlignmentFlag.AlignCenter)

    def _stat_badge(self, value: str, label: str) -> QWidget:
        w = QWidget(self)
        w.setObjectName("StatBadge")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(0)
        val_lbl = QLabel(value, w)
        val_lbl.setObjectName("StatValue")
        val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_lbl = QLabel(label, w)
        lbl_lbl.setObjectName("StatLabel")
        lbl_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(val_lbl)
        lay.addWidget(lbl_lbl)
        return w

    def _on_search_changed(self) -> None:
        self._display_limit = self.INITIAL_LIMIT
        self.load_history()

    def _set_filter(self, key: str) -> None:
        self._active_filter = key
        self._display_limit = self.INITIAL_LIMIT
        for k, btn in self._filter_btns.items():
            btn.setChecked(k == key)
        self.load_history()

    def _apply_style(self) -> None:
        a = self._accent
        self.setStyleSheet(f"""
            QWidget#StatBadge {{
                background-color: rgba(255, 255, 255, 0.04);
                border-radius: 6px;
                border: 1px solid rgba(255, 255, 255, 0.06);
                min-width: 60px;
            }}
            QLabel#StatValue {{
                color: {a};
                font-size: 15px;
                font-weight: 700;
                font-family: 'Segoe UI';
            }}
            QLabel#StatLabel {{
                color: #666666;
                font-size: 10px;
                font-family: 'Segoe UI';
            }}
            QLineEdit#SearchInput {{
                background-color: #20232C;
                color: #E0E0E0;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                padding: 7px 10px;
                font-size: 12px;
                font-family: 'Segoe UI';
            }}
            QLineEdit#SearchInput:focus {{ border: 1px solid {a}; }}

            QPushButton#FilterBtn {{
                background-color: rgba(255, 255, 255, 0.04);
                color: #888888;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 5px;
                padding: 4px 10px;
                font-size: 11px;
                font-family: 'Segoe UI';
            }}
            QPushButton#FilterBtn:checked {{
                background-color: {a};
                color: #12141A;
                border-color: {a};
                font-weight: 600;
            }}
            QPushButton#FilterBtn:hover:!checked {{
                background-color: rgba(255, 255, 255, 0.08);
                color: #E0E0E0;
            }}

            QFrame#HistSep {{ color: rgba(255, 255, 255, 0.06); }}

            QListWidget#HistList {{
                background-color: transparent;
                border: none;
            }}

            QPushButton#FooterBtn {{
                background-color: rgba(255, 255, 255, 0.04);
                color: {a};
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                padding: 5px 12px;
                font-size: 11px;
                font-family: 'Segoe UI';
            }}
            QPushButton#FooterBtn:hover {{ background-color: {a}; color: #12141A; }}
            QPushButton#DangerBtn {{
                background-color: rgba(255, 85, 85, 0.1);
                color: #FF5555;
                border: 1px solid rgba(255, 85, 85, 0.3);
                border-radius: 6px;
                padding: 5px 12px;
                font-size: 11px;
                font-family: 'Segoe UI';
            }}
            QPushButton#DangerBtn:hover {{ background-color: #FF5555; color: #FFFFFF; }}
            QPushButton#LoadMoreBtn {{
                background-color: rgba(255, 255, 255, 0.05);
                color: {a};
                border: 1px solid {a};
                border-radius: 6px;
                padding: 6px 18px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton#LoadMoreBtn:hover {{ background-color: {a}; color: #12141A; }}
        """)

    def load_history(self) -> None:
        """High-performance history loader with chunk limits."""
        self.list_widget.clear()
        query = self.search_input.text()
        all_items = self.history_manager.search(query)

        if self._active_filter == "favorites":
            items = [i for i in all_items if i.favorite]
        elif self._active_filter == "voice":
            items = [i for i in all_items if "[Voice]" in i.original]
        elif self._active_filter == "text":
            items = [i for i in all_items if "[Voice]" not in i.original]
        else:
            items = all_items

        self._filtered_items = items

        # Display chunked limit for fast rendering
        visible_items = items[:self._display_limit]
        for item in visible_items:
            list_item = QListWidgetItem(self.list_widget)
            widget = HistoryItemWidget(item, self._accent, self)
            widget.delete_clicked.connect(self._delete_item)
            widget.favorite_clicked.connect(self._toggle_favorite)
            list_item.setSizeHint(widget.sizeHint())
            self.list_widget.addItem(list_item)
            self.list_widget.setItemWidget(list_item, widget)

        if len(items) > self._display_limit:
            self.load_more_btn.show()
            self.load_more_btn.setText(f"Load More ({len(items) - self._display_limit} remaining)...")
        else:
            self.load_more_btn.hide()

        self._update_stats()

    def _load_more(self) -> None:
        self._display_limit += 50
        self.load_history()

    def _update_stats(self) -> None:
        all_items = self.history_manager.search("")
        total = len(all_items)
        today_str = date.today().isoformat()
        today = sum(1 for i in all_items if i.timestamp.startswith(today_str))
        favs = sum(1 for i in all_items if i.favorite)

        for card, val in ((self._stat_total, total), (self._stat_today, today), (self._stat_favs, favs)):
            lbl = card.findChild(QLabel, "StatValue")
            if lbl is not None:
                lbl.setText(str(val))

    def _delete_item(self, item_id: str) -> None:
        if self.history_manager.delete(item_id):
            self.load_history()

    def _toggle_favorite(self, item_id: str) -> None:
        if self.history_manager.toggle_favorite(item_id):
            self.load_history()

    def _clear_history(self) -> None:
        reply = QMessageBox.question(
            self, "Clear History", "Clear all translation history?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.history_manager.clear()
            self.load_history()

    def _export_history(self) -> None:
        filepath, _ = QFileDialog.getSaveFileName(self, "Export History", "", "CSV Files (*.csv)")
        if filepath:
            if self.history_manager.export_csv(filepath):
                QMessageBox.information(self, "Export", "History exported successfully.")
            else:
                QMessageBox.critical(self, "Export Failed", "Could not export history.")


class HistoryWindow(QDialog):
    """Standalone Dialog wrapper for HistoryPage."""

    def __init__(self, history_manager: HistoryManager, accent: str = "#5CB868", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Translation History")
        self.resize(580, 640)
        self.setMinimumSize(480, 500)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.history_page = HistoryPage(history_manager, accent=accent, parent=self)
        layout.addWidget(self.history_page)

    def load_history(self) -> None:
        self.history_page.load_history()
