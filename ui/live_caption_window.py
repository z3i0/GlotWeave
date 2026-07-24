import re
import logging
from typing import Optional, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import Qt, QPoint, QTimer, Signal, QEvent, QObject
from PySide6.QtGui import QCursor, QFont, QColor, QTextCursor, QMouseEvent
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QGraphicsDropShadowEffect, QFrame,
    QTextBrowser, QApplication
)

from ui.icons import get_pixmap, get_icon
from services.dictionary_service import DictionaryService

logger = logging.getLogger(__name__)

# Dedicated background executor for instant non-blocking dictionary lookups
_DICT_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="DictLookup")


def _smart_stitch_words(existing_words: List[str], new_words: List[str]) -> List[str]:
    """Intelligently merges new words into existing word list, removing overlapping phrases and preventing duplicates."""
    if not existing_words:
        return list(new_words)
    if not new_words:
        return list(existing_words)

    max_overlap = min(6, len(existing_words), len(new_words))
    best_overlap = 0

    for i in range(1, max_overlap + 1):
        existing_tail = [w.lower() for w in existing_words[-i:]]
        new_head = [w.lower() for w in new_words[:i]]
        if existing_tail == new_head:
            best_overlap = i

    if best_overlap > 0:
        added = new_words[best_overlap:]
        if not added:
            return list(existing_words)
        return existing_words + added

    return existing_words + new_words


class LoadingSkeletonWidget(QWidget):
    """An animated shimmer loading skeleton widget displayed instantly while dictionary data fetches."""
    def __init__(self, parent=None, accent_color: str = "#00ADB5"):
        super().__init__(parent)
        self._accent = accent_color
        self._pulse_alpha = 40
        self._step = 8
        self.setMinimumWidth(180)

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 4, 0, 4)
        v.setSpacing(6)

        self.bar1 = QLabel(self)
        self.bar1.setFixedHeight(12)
        v.addWidget(self.bar1)

        self.bar2 = QLabel(self)
        self.bar2.setFixedHeight(10)
        v.addWidget(self.bar2)

        self._timer = QTimer(self)
        self._timer.setInterval(40)  # ~25 FPS smooth pulse animation
        self._timer.timeout.connect(self._animate_pulse)
        self._animate_pulse()
        self._timer.start()

    def _animate_pulse(self) -> None:
        self._pulse_alpha += self._step
        if self._pulse_alpha >= 130 or self._pulse_alpha <= 30:
            self._step = -self._step
        a = self._pulse_alpha
        self.bar1.setStyleSheet(f"background-color: rgba(0, 173, 181, {a / 255.0:.2f}); border-radius: 4px;")
        self.bar2.setStyleSheet(f"background-color: rgba(255, 255, 255, {a / 320.0:.2f}); border-radius: 4px;")

    def stop_animation(self) -> None:
        self._timer.stop()


class WordMeaningPopup(QWidget):
    """A floating popover card showing dictionary meanings, parts of speech, and synonyms for a hovered word."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.BypassWindowManagerHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._accent = "#00ADB5"
        self.is_pinned = False
        self._build_ui()
        self._apply_style()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)

        self.frame = QFrame(self)
        self.frame.setObjectName("PopupFrame")
        layout = QVBoxLayout(self.frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        # Header: Word + Primary Translation
        header_row = QHBoxLayout()
        header_row.setSpacing(8)

        self.lbl_word = QLabel("Word", self.frame)
        self.lbl_word.setObjectName("PopupWord")
        header_row.addWidget(self.lbl_word)

        self.lbl_trans = QLabel("Translation", self.frame)
        self.lbl_trans.setObjectName("PopupTrans")
        header_row.addWidget(self.lbl_trans)

        header_row.addStretch()
        layout.addLayout(header_row)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("PopupSep")
        layout.addWidget(sep)

        # Content layout for POS and meanings
        self.content_v = QVBoxLayout()
        self.content_v.setSpacing(6)
        layout.addLayout(self.content_v)

        outer.addWidget(self.frame)

        # Drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(16)
        shadow.setColor(QColor(0, 0, 0, 200))
        shadow.setOffset(0, 4)
        self.frame.setGraphicsEffect(shadow)

    def _apply_style(self) -> None:
        a = self._accent
        self.setStyleSheet(f"""
            QFrame#PopupFrame {{
                background-color: rgba(20, 24, 33, 0.96);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 10px;
            }}
            QLabel#PopupWord {{
                color: #FFFFFF;
                font-size: 14px;
                font-weight: 700;
                font-family: 'Segoe UI', Arial;
            }}
            QLabel#PopupTrans {{
                color: {a};
                font-size: 13px;
                font-weight: 600;
                font-family: 'Segoe UI', Arial;
            }}
            QFrame#PopupSep {{
                background-color: rgba(255, 255, 255, 0.08);
                max-height: 1px;
            }}
            QLabel.PosBadge {{
                color: {a};
                font-size: 11px;
                font-weight: 700;
                background-color: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 4px;
                padding: 2px 6px;
            }}
            QLabel.MeaningItem {{
                color: #DDDDDD;
                font-size: 12px;
                font-family: 'Segoe UI', Arial;
            }}
            QLabel.SynonymItem {{
                color: #888888;
                font-size: 11px;
                font-style: italic;
            }}
        """)

    def set_accent(self, accent_color: str) -> None:
        self._accent = accent_color
        self._apply_style()

    def pin(self) -> None:
        """Fixes popover on screen so it remains open when mouse leaves."""
        self.is_pinned = True

    def unpin(self) -> None:
        """Unpins popover so it can be dismissed."""
        self.is_pinned = False

    def hide_if_unpinned(self) -> None:
        """Hides popover if not explicitly pinned by click."""
        if not self.is_pinned:
            self.hide()

    def show_loading_state(self, word: str, global_pos: QPoint, pin: bool = False) -> None:
        """Instantly opens the popover card in 0ms showing the word header and animated loading skeleton."""
        self.lbl_word.setText(word)
        self.lbl_trans.setText("Searching & translating...")

        # Clear existing dynamic content
        while self.content_v.count():
            child = self.content_v.takeAt(0)
            if child is not None and child.widget():
                w = child.widget()
                if w is not None:
                    w.setParent(None)

        skeleton = LoadingSkeletonWidget(self.frame, accent_color=self._accent)
        self.content_v.addWidget(skeleton)

        if pin:
            self.pin()
        else:
            self.unpin()

        self.resize(1, 1)
        self.adjustSize()

        screen = QApplication.primaryScreen().geometry()
        x = global_pos.x() - self.width() // 2
        y = global_pos.y() + 18

        if x < screen.left() + 10:
            x = screen.left() + 10
        elif x + self.width() > screen.right() - 10:
            x = screen.right() - self.width() - 10

        if y + self.height() > screen.bottom() - 10:
            y = global_pos.y() - self.height() - 10

        self.move(x, y)
        self.show()

    def show_dict_data(self, dict_data: Dict[str, Any], global_pos: QPoint, pin: bool = False) -> None:
        """Populates dictionary information, resizes dynamically, and positions popover near mouse cursor."""
        word = dict_data.get("word", "")
        translation = dict_data.get("translation", "")
        pos_entries = dict_data.get("pos_entries", [])

        self.lbl_word.setText(word)
        self.lbl_trans.setText(translation if translation else "")

        # Clear existing dynamic content synchronously
        while self.content_v.count():
            child = self.content_v.takeAt(0)
            if child is not None and child.widget():
                w = child.widget()
                if w is not None:
                    w.setParent(None)

        if pos_entries:
            for entry in pos_entries:
                pos = entry.get("pos", "")
                meanings = entry.get("meanings", [])
                synonyms = entry.get("synonyms", [])

                pos_lbl = QLabel(pos.upper() if pos else "MEANING", self.frame)
                pos_lbl.setProperty("class", "PosBadge")
                self.content_v.addWidget(pos_lbl)

                if meanings:
                    m_str = " • " + "\n • ".join(meanings)
                    m_lbl = QLabel(m_str, self.frame)
                    m_lbl.setProperty("class", "MeaningItem")
                    m_lbl.setWordWrap(True)
                    self.content_v.addWidget(m_lbl)

                if synonyms:
                    syn_str = "Synonyms: " + ", ".join(synonyms)
                    syn_lbl = QLabel(syn_str, self.frame)
                    syn_lbl.setProperty("class", "SynonymItem")
                    syn_lbl.setWordWrap(True)
                    self.content_v.addWidget(syn_lbl)
        else:
            no_def_lbl = QLabel("No additional dictionary definitions found.", self.frame)
            no_def_lbl.setStyleSheet("color: #888888; font-size: 11px;")
            self.content_v.addWidget(no_def_lbl)

        if pin:
            self.pin()
        else:
            self.unpin()

        # Reset geometry and recalculate exact size for new content
        self.resize(1, 1)
        self.adjustSize()

        screen = QApplication.primaryScreen().geometry()
        x = global_pos.x() - self.width() // 2
        y = global_pos.y() + 18

        if x < screen.left() + 10:
            x = screen.left() + 10
        elif x + self.width() > screen.right() - 10:
            x = screen.right() - self.width() - 10

        if y + self.height() > screen.bottom() - 10:
            y = global_pos.y() - self.height() - 10

        self.move(x, y)
        self.show()


class HoverTextBrowser(QTextBrowser):
    """An interactive multi-line text browser that wraps words cleanly, detects hovered words, and clicks to pin."""
    word_hovered = Signal(str, QPoint)
    word_unhovered = Signal()
    word_clicked = Signal(str, QPoint)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setOpenExternalLinks(False)
        self.setOpenLinks(False)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        cursor = self.cursorForPosition(event.position().toPoint())
        cursor.select(QTextCursor.SelectionType.WordUnderCursor)
        w = cursor.selectedText().strip()
        cleaned_w = re.sub(r'^[^\w]+|[^\w]+$', '', w, flags=re.UNICODE)
        if cleaned_w:
            self.word_hovered.emit(cleaned_w, event.globalPosition().toPoint())
        else:
            self.word_unhovered.emit()
        super().mouseMoveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            cursor = self.cursorForPosition(event.position().toPoint())
            cursor.select(QTextCursor.SelectionType.WordUnderCursor)
            w = cursor.selectedText().strip()
            cleaned_w = re.sub(r'^[^\w]+|[^\w]+$', '', w, flags=re.UNICODE)
            if cleaned_w:
                self.word_clicked.emit(cleaned_w, event.globalPosition().toPoint())
            else:
                win = self.window()
                if hasattr(win, "dict_popup") and win.dict_popup.isVisible():
                    win.dict_popup.unpin()
                    win.dict_popup.hide()
        super().mousePressEvent(event)

    def leaveEvent(self, event) -> None:
        self.word_unhovered.emit()
        super().leaveEvent(event)


class LiveCaptionWindow(QWidget):
    """Floating borderless Live Caption overlay with Dual Subtitles and Hover Word Dictionary."""
    settings_requested = Signal()
    translation_toggled = Signal(bool)
    dict_data_ready = Signal(dict, QPoint, bool)

    MAX_CAPTION_WORDS = 24  # Max words limit before auto-clearing for a fresh sentence cycle

    def __init__(self, dictionary_service: DictionaryService, parent=None):
        super().__init__(parent)
        self.dictionary_service = dictionary_service
        
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        
        self._accent = "#00ADB5"
        self._enable_translation = False  # False = Recognize speech only
        self._source_lang = "auto"
        self._target_lang = "ar"
        self._drag_pos = QPoint()
        
        self._cum_orig_words: List[str] = []
        self._cum_trans_words: List[str] = []
        
        self._new_orig_word_count = 0
        self._new_trans_word_count = 0

        # Popover dictionary card
        self.dict_popup = WordMeaningPopup(self)
        self.dict_data_ready.connect(self._on_dict_data_ready)

        self._pending_hover_word = ""
        self._pending_hover_pos = QPoint()
        self._pending_is_click = False

        # Highlight settling timer for newly appearing words
        self._settle_timer = QTimer(self)
        self._settle_timer.setSingleShot(True)
        self._settle_timer.timeout.connect(self._settle_highlight)

        self._build_ui()
        self._apply_style()
        self._position_default()

        # Install global application event filter for outside clicks
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 10, 10, 10)

        # Glassmorphic Frame
        self.frame = QFrame(self)
        self.frame.setObjectName("CaptionFrame")
        layout = QVBoxLayout(self.frame)
        layout.setContentsMargins(14, 8, 14, 12)
        layout.setSpacing(6)

        # Top Bar (Header & Controls)
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        # Drag handle icon
        self.drag_lbl = QLabel(self.frame)
        self.drag_lbl.setPixmap(get_pixmap("app_logo", size=18))
        top_row.addWidget(self.drag_lbl)

        title = QLabel("Live Caption", self.frame)
        title.setObjectName("CaptionTitle")
        top_row.addWidget(title)

        # Status dot / text
        self.status_lbl = QLabel("● Listening", self.frame)
        self.status_lbl.setObjectName("StatusLabel")
        top_row.addWidget(self.status_lbl)

        # Language badge
        self.lang_badge = QLabel("AUTO", self.frame)
        self.lang_badge.setObjectName("LangBadge")
        top_row.addWidget(self.lang_badge)

        top_row.addStretch()

        # Translation Toggle button
        self.btn_translate = QPushButton("Translate", self.frame)
        self.btn_translate.setObjectName("ControlBtn")
        self.btn_translate.setCheckable(True)
        self.btn_translate.setChecked(self._enable_translation)
        self.btn_translate.setToolTip("Toggle Translation into target language")
        self.btn_translate.clicked.connect(self._toggle_translation)
        top_row.addWidget(self.btn_translate)

        # Clear text button
        self.btn_clear = QPushButton(self.frame)
        self.btn_clear.setObjectName("IconBtn")
        self.btn_clear.setFixedSize(24, 24)
        self.btn_clear.setIcon(get_icon("trash", color="#AAAAAA", size=14))
        self.btn_clear.setToolTip("Clear Captions")
        self.btn_clear.clicked.connect(self.clear_captions)
        top_row.addWidget(self.btn_clear)

        # Settings button
        self.btn_settings = QPushButton(self.frame)
        self.btn_settings.setObjectName("IconBtn")
        self.btn_settings.setFixedSize(24, 24)
        self.btn_settings.setIcon(get_icon("settings", color="#AAAAAA", size=14))
        self.btn_settings.setToolTip("Live Caption Settings")
        self.btn_settings.clicked.connect(self.settings_requested.emit)
        top_row.addWidget(self.btn_settings)

        # Close button
        self.btn_close = QPushButton(self.frame)
        self.btn_close.setObjectName("CloseBtn")
        self.btn_close.setFixedSize(24, 24)
        self.btn_close.setIcon(get_icon("close", color="#AAAAAA", size=14))
        self.btn_close.clicked.connect(self.hide)
        top_row.addWidget(self.btn_close)

        layout.addLayout(top_row)

        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("HeaderSep")
        layout.addWidget(sep)

        # Subtitles Container (Multi-line text browsers with word wrapping)
        self.subtitles_box = QVBoxLayout()
        self.subtitles_box.setSpacing(6)
        
        # Row 1: Recognized Original Text Multi-line Browser
        self.orig_browser = HoverTextBrowser(self.frame)
        self.orig_browser.setObjectName("OrigBrowser")
        self.orig_browser.setFrameShape(QFrame.Shape.NoFrame)
        self.orig_browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.orig_browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.orig_browser.setMinimumHeight(48)
        self.orig_browser.setMaximumHeight(76)
        self.orig_browser.word_hovered.connect(self._handle_word_hovered)
        self.orig_browser.word_unhovered.connect(self._handle_word_unhovered)
        self.orig_browser.word_clicked.connect(self._handle_word_clicked)
        
        self.subtitles_box.addWidget(self.orig_browser)

        # Row 2: Translated Text Multi-line Browser
        self.trans_browser = HoverTextBrowser(self.frame)
        self.trans_browser.setObjectName("TransBrowser")
        self.trans_browser.setFrameShape(QFrame.Shape.NoFrame)
        self.trans_browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.trans_browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.trans_browser.setMinimumHeight(44)
        self.trans_browser.setMaximumHeight(64)
        self.trans_browser.setVisible(self._enable_translation)
        self.trans_browser.word_hovered.connect(self._handle_word_hovered)
        self.trans_browser.word_unhovered.connect(self._handle_word_unhovered)
        self.trans_browser.word_clicked.connect(self._handle_word_clicked)

        self.subtitles_box.addWidget(self.trans_browser)

        layout.addLayout(self.subtitles_box)
        outer.addWidget(self.frame)

        # Drop Shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 190))
        shadow.setOffset(0, 6)
        self.frame.setGraphicsEffect(shadow)

        self.resize(720, 165)

    def eventFilter(self, watched, event) -> bool:
        """Event filter catching mouse clicks anywhere outside dictionary popup to unpin and dismiss it."""
        if event.type() == QEvent.Type.MouseButtonPress:
            if self.dict_popup.isVisible():
                global_pos = event.globalPosition().toPoint()
                popup_geo = self.dict_popup.frameGeometry()
                if not popup_geo.contains(global_pos):
                    self.dict_popup.unpin()
                    self.dict_popup.hide()
        return super().eventFilter(watched, event)

    def _apply_style(self) -> None:
        a = self._accent
        orig_font_size = "17px" if not self._enable_translation else "14px"
        orig_font_weight = "600" if not self._enable_translation else "400"
        orig_color = "#FFFFFF" if not self._enable_translation else "#DDDDDD"

        self.setStyleSheet(f"""
            QFrame#CaptionFrame {{
                background-color: rgba(16, 19, 26, 0.94);
                border: 1px solid rgba(255, 255, 255, 0.12);
                border-radius: 12px;
            }}
            QLabel#CaptionTitle {{
                color: #FFFFFF;
                font-size: 12px;
                font-weight: 700;
                font-family: 'Segoe UI', Arial;
            }}
            QLabel#StatusLabel {{
                color: {a};
                font-size: 11px;
                font-weight: 600;
            }}
            QLabel#LangBadge {{
                color: #AAAAAA;
                background-color: rgba(255, 255, 255, 0.06);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 4px;
                padding: 2px 6px;
                font-size: 10px;
                font-weight: 700;
            }}
            QFrame#HeaderSep {{
                background-color: rgba(255, 255, 255, 0.08);
                max-height: 1px;
            }}
            QPushButton#ControlBtn {{
                background-color: rgba(255, 255, 255, 0.06);
                color: #DDDDDD;
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                padding: 3px 10px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton#ControlBtn:checked {{
                background-color: {a};
                color: #12141A;
                border-color: {a};
            }}
            QPushButton#IconBtn {{
                background: transparent;
                border: none;
                border-radius: 4px;
            }}
            QPushButton#IconBtn:hover {{
                background-color: rgba(255, 255, 255, 0.1);
            }}
            QPushButton#CloseBtn {{
                background: transparent;
                border: none;
                border-radius: 4px;
            }}
            QPushButton#CloseBtn:hover {{
                background-color: rgba(255, 70, 70, 0.25);
            }}
            QTextBrowser#OrigBrowser {{
                background: transparent;
                color: {orig_color};
                font-size: {orig_font_size};
                font-weight: {orig_font_weight};
                font-family: 'Segoe UI', Arial, sans-serif;
                border: none;
            }}
            QTextBrowser#TransBrowser {{
                background: transparent;
                color: {a};
                font-size: 16px;
                font-weight: 600;
                font-family: 'Segoe UI', Arial, sans-serif;
                border: none;
            }}
        """)
        self.dict_popup.set_accent(a)

    def set_accent(self, color: str) -> None:
        self._accent = color
        self._apply_style()

    def set_languages(self, source_lang: str, target_lang: str) -> None:
        self._source_lang = source_lang
        self._target_lang = target_lang
        src_display = source_lang.upper() if source_lang != "auto" else "AUTO"
        tgt_display = target_lang.upper()
        if self._enable_translation:
            self.lang_badge.setText(f"{src_display} ➔ {tgt_display}")
        else:
            self.lang_badge.setText(f"{src_display}")

    def set_translation_enabled(self, enabled: bool) -> None:
        self._enable_translation = enabled
        self.btn_translate.setChecked(enabled)
        self.trans_browser.setVisible(enabled)
        self.set_languages(self._source_lang, self._target_lang)
        self._apply_style()

    def _toggle_translation(self) -> None:
        enabled = self.btn_translate.isChecked()
        self.set_translation_enabled(enabled)
        self.translation_toggled.emit(enabled)

    def update_status(self, status: str) -> None:
        self.status_lbl.setText(f"● {status}")

    def update_caption(self, original_text: str, translated_text: str = "") -> None:
        """Appends new speech side-by-side, highlighting ONLY brand new words as they appear."""
        if not original_text or not original_text.strip():
            return

        new_orig_words = original_text.strip().split()
        prev_orig_count = len(self._cum_orig_words)

        # Check if cumulative word count exceeds limit -> auto-clear for fresh sentence cycle
        if len(self._cum_orig_words) + len(new_orig_words) > self.MAX_CAPTION_WORDS:
            self._cum_orig_words = new_orig_words
            self._cum_trans_words = translated_text.strip().split() if translated_text else []
            self._new_orig_word_count = len(new_orig_words)
            self._new_trans_word_count = len(self._cum_trans_words)
        else:
            self._cum_orig_words = _smart_stitch_words(self._cum_orig_words, new_orig_words)
            self._new_orig_word_count = len(self._cum_orig_words) - prev_orig_count
            
            if translated_text and translated_text.strip():
                prev_trans_count = len(self._cum_trans_words)
                new_trans_words = translated_text.strip().split()
                self._cum_trans_words = _smart_stitch_words(self._cum_trans_words, new_trans_words)
                self._new_trans_word_count = len(self._cum_trans_words) - prev_trans_count
            else:
                self._new_trans_word_count = 0

        self._render_caption_html()
        self._settle_timer.start(400)  # Settle new words highlight after 400ms

    def _render_caption_html(self) -> None:
        """Renders HTML formatting where existing words stay solid white and NEW words animate with accent highlight."""
        a = self._accent

        # ── 1. Render Original Speech Text Browser ───────────────────────
        if self._cum_orig_words:
            if self._new_orig_word_count > 0 and self._new_orig_word_count < len(self._cum_orig_words):
                old_words = self._cum_orig_words[:-self._new_orig_word_count]
                new_words = self._cum_orig_words[-self._new_orig_word_count:]
                old_str = " ".join(old_words)
                new_str = " ".join(new_words)
                orig_html = (
                    f"<span>{old_str} </span>"
                    f"<span style='color:{a}; font-weight:700; background-color:rgba(0,173,181,0.22); border-radius:3px;'>{new_str}</span>"
                )
            else:
                orig_html = f"<span>{' '.join(self._cum_orig_words)}</span>"

            self.orig_browser.setHtml(orig_html)
            self.orig_browser.moveCursor(QTextCursor.MoveOperation.End)

        # ── 2. Render Translated Text Browser (if enabled) ────────────────
        if self._enable_translation and self._cum_trans_words:
            if self._new_trans_word_count > 0 and self._new_trans_word_count < len(self._cum_trans_words):
                old_t_words = self._cum_trans_words[:-self._new_trans_word_count]
                new_t_words = self._cum_trans_words[-self._new_trans_word_count:]
                old_t_str = " ".join(old_t_words)
                new_t_str = " ".join(new_t_words)
                trans_html = (
                    f"<span>{old_t_str} </span>"
                    f"<span style='color:#FFFFFF; font-weight:700; background-color:rgba(0,173,181,0.35); border-radius:3px;'>{new_t_str}</span>"
                )
            else:
                trans_html = f"<span>{' '.join(self._cum_trans_words)}</span>"

            self.trans_browser.setHtml(trans_html)
            self.trans_browser.moveCursor(QTextCursor.MoveOperation.End)

    def _settle_highlight(self) -> None:
        """After 400ms, settles newly appeared highlighted words into standard clean text styling."""
        self._new_orig_word_count = 0
        self._new_trans_word_count = 0
        self._render_caption_html()

    def clear_captions(self) -> None:
        self._cum_orig_words.clear()
        self._cum_trans_words.clear()
        self._new_orig_word_count = 0
        self._new_trans_word_count = 0
        self.orig_browser.clear()
        self.trans_browser.clear()
        self.dict_popup.unpin()
        self.dict_popup.hide()

    def _clear_layout(self, layout) -> None:
        self.clear_captions()

    def _handle_word_hovered(self, word: str, global_pos: QPoint) -> None:
        if self._pending_hover_word == word and self.dict_popup.isVisible():
            return
        self._pending_hover_word = word
        self._pending_hover_pos = global_pos
        self._pending_is_click = False
        
        # INSTANT 0ms Show Loading Skeleton Popover!
        self.dict_popup.show_loading_state(word, global_pos, pin=False)
        self._trigger_async_dict_lookup(word, global_pos, pin=False)

    def _handle_word_clicked(self, word: str, global_pos: QPoint) -> None:
        self._pending_hover_word = word
        self._pending_hover_pos = global_pos
        self._pending_is_click = True
        
        # INSTANT 0ms Show Pinned Loading Skeleton Popover!
        self.dict_popup.show_loading_state(word, global_pos, pin=True)
        self._trigger_async_dict_lookup(word, global_pos, pin=True)

    def _handle_word_unhovered(self) -> None:
        self._pending_hover_word = ""
        self.dict_popup.hide_if_unpinned()

    def _trigger_async_dict_lookup(self, word: str, pos: QPoint, pin: bool) -> None:
        """Executes dictionary lookup in background thread to keep UI 100% smooth."""
        def _fetch_job():
            try:
                dict_data = self.dictionary_service.lookup_word(
                    word=word,
                    source_lang=self._source_lang,
                    target_lang=self._target_lang
                )
                if dict_data:
                    self.dict_data_ready.emit(dict_data, pos, pin)
            except Exception as e:
                logger.debug(f"Async dict lookup exception: {e}")

        _DICT_EXECUTOR.submit(_fetch_job)

    def _on_dict_data_ready(self, dict_data: Dict[str, Any], pos: QPoint, pin: bool) -> None:
        """Slot called when async background dictionary lookup finishes."""
        target_word = dict_data.get("word", "")
        # Only update if the user is still hovering/clicking on the same word
        if target_word.lower() == self._pending_hover_word.lower() or self.dict_popup.is_pinned:
            self.dict_popup.show_dict_data(dict_data, pos, pin=pin)

    def _position_default(self) -> None:
        """Center the caption bar near the bottom of primary screen."""
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = screen.height() - self.height() - 80
        self.move(x, y)

    # ── Window Drag & Click Dismiss Handling ─────────────────────
    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.ActivationChange and not self.isActiveWindow():
            if self.dict_popup.isVisible():
                self.dict_popup.unpin()
                self.dict_popup.hide()
        super().changeEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            if self.dict_popup.isVisible():
                global_pos = event.globalPosition().toPoint()
                if not self.dict_popup.frameGeometry().contains(global_pos):
                    self.dict_popup.unpin()
                    self.dict_popup.hide()
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
