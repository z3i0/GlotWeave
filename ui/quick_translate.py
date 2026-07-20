import logging
from PySide6.QtCore import Qt, Signal, QThread, QObject, QTimer
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QComboBox, QApplication, QGraphicsDropShadowEffect,
    QFrame
)
from app.config import LANGUAGES
from ui.icons import get_icon, get_pixmap

logger = logging.getLogger(__name__)


class TranslateWorker(QObject):
    """Runs translation in a background thread."""
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, translation_mgr, text, source_lang, target_lang, provider, api_key, extra):
        super().__init__()
        self.translation_mgr = translation_mgr
        self.text = text
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.provider = provider
        self.api_key = api_key
        self.extra = extra

    def run(self):
        try:
            result = self.translation_mgr.translate(
                text=self.text,
                source_lang=self.source_lang,
                target_lang=self.target_lang,
                provider_name=self.provider,
                api_key=self.api_key,
                extra_settings=self.extra
            )
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class QuickTranslateWindow(QWidget):
    """A modern floating Quick Translate panel."""

    translate_requested = Signal(str, str, str)

    def __init__(self, translation_mgr=None, settings_mgr=None, parent=None):
        super().__init__(parent)
        self.translation_mgr = translation_mgr
        self.settings_mgr = settings_mgr
        self._accent = "#00ADB5"
        self._thread = None
        self._worker = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMinimumWidth(460)
        self.setMaximumWidth(560)

        self._build_ui()
        self._apply_style()
        self._center_on_screen()

        # Esc shortcut
        QShortcut(QKeySequence("Escape"), self, self.hide)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)

        self.card = QWidget(self)
        self.card.setObjectName("QTCard")
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(0, 0, 0, 0)
        card_layout.setSpacing(0)

        # ── Header ──────────────────────────────────────────────
        header = QWidget(self.card)
        header.setObjectName("QTHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(16, 12, 12, 12)

        self.title_icon = QLabel(header)
        self.title_icon.setFixedSize(18, 18)
        self.title_icon.setPixmap(get_pixmap("app_logo", size=18))
        header_layout.addWidget(self.title_icon)

        title = QLabel("Quick Translate", header)
        title.setObjectName("QTTitle")
        header_layout.addWidget(title)
        header_layout.addStretch()

        self.pin_btn = QPushButton(header)
        self.pin_btn.setObjectName("HeaderBtn")
        self.pin_btn.setFixedSize(28, 28)
        self.pin_btn.setCheckable(True)
        self.pin_btn.setIcon(get_icon("pin", color="#888888", size=15))
        self.pin_btn.setToolTip("Pin window on top")
        self.pin_btn.toggled.connect(self._on_pin_toggled)
        header_layout.addWidget(self.pin_btn)

        close_btn = QPushButton(header)
        close_btn.setObjectName("CloseBtn")
        close_btn.setFixedSize(28, 28)
        close_btn.setIcon(get_icon("close", color="#888888", size=15))
        close_btn.clicked.connect(self.hide)
        header_layout.addWidget(close_btn)

        card_layout.addWidget(header)

        # ── Language Row ─────────────────────────────────────────
        lang_row = QWidget(self.card)
        lang_row.setObjectName("LangRow")
        lang_layout = QHBoxLayout(lang_row)
        lang_layout.setContentsMargins(16, 10, 16, 10)
        lang_layout.setSpacing(8)

        self.cmb_src = QComboBox(lang_row)
        self.cmb_src.setObjectName("LangCombo")
        for code, name in LANGUAGES.items():
            self.cmb_src.addItem(name, code)
        lang_layout.addWidget(self.cmb_src, 1)

        self.swap_btn = QPushButton(lang_row)
        self.swap_btn.setObjectName("SwapBtn")
        self.swap_btn.setFixedSize(34, 34)
        self.swap_btn.setIcon(get_icon("swap", color=self._accent, size=16))
        self.swap_btn.setToolTip("Swap languages")
        self.swap_btn.clicked.connect(self._swap_langs)
        lang_layout.addWidget(self.swap_btn)

        self.cmb_tgt = QComboBox(lang_row)
        self.cmb_tgt.setObjectName("LangCombo")
        for code, name in LANGUAGES.items():
            if code != "auto":
                self.cmb_tgt.addItem(name, code)
        idx = self.cmb_tgt.findData("en")
        if idx >= 0:
            self.cmb_tgt.setCurrentIndex(idx)
        lang_layout.addWidget(self.cmb_tgt, 1)

        card_layout.addWidget(lang_row)

        card_layout.addWidget(self._divider())

        # ── Source Input ─────────────────────────────────────────
        src_container = QWidget(self.card)
        src_container.setObjectName("InputContainer")
        src_v = QVBoxLayout(src_container)
        src_v.setContentsMargins(16, 12, 16, 12)
        src_v.setSpacing(6)

        src_lbl = QLabel("SOURCE TEXT", src_container)
        src_lbl.setObjectName("SectionLabel")
        src_v.addWidget(src_lbl)

        self.src_input = QTextEdit(src_container)
        self.src_input.setObjectName("SrcInput")
        self.src_input.setPlaceholderText("Type or paste text here...")
        self.src_input.setMinimumHeight(90)
        self.src_input.setMaximumHeight(130)
        self.src_input.setFont(QFont("Segoe UI", 11))
        self.src_input.textChanged.connect(self._on_src_changed)
        src_v.addWidget(self.src_input)

        self.char_count = QLabel("0 / 5000", src_container)
        self.char_count.setObjectName("CharCount")
        self.char_count.setAlignment(Qt.AlignmentFlag.AlignRight)
        src_v.addWidget(self.char_count)

        card_layout.addWidget(src_container)

        card_layout.addWidget(self._divider())

        # ── Result ───────────────────────────────────────────────
        res_container = QWidget(self.card)
        res_container.setObjectName("ResultContainer")
        res_v = QVBoxLayout(res_container)
        res_v.setContentsMargins(16, 12, 16, 12)
        res_v.setSpacing(6)

        res_header = QHBoxLayout()
        res_lbl = QLabel("TRANSLATION", res_container)
        res_lbl.setObjectName("SectionLabel")
        res_header.addWidget(res_lbl)
        res_header.addStretch()

        self.copy_btn = QPushButton("Copy", res_container)
        self.copy_btn.setObjectName("CopyBtn")
        self.copy_btn.setIcon(get_icon("copy", color=self._accent, size=13))
        self.copy_btn.clicked.connect(self._copy_result)
        res_header.addWidget(self.copy_btn)
        res_v.addLayout(res_header)

        self.result_label = QLabel("", res_container)
        self.result_label.setObjectName("ResultLabel")
        self.result_label.setWordWrap(True)
        self.result_label.setMinimumHeight(80)
        self.result_label.setFont(QFont("Segoe UI", 11))
        self.result_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.result_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        res_v.addWidget(self.result_label)

        card_layout.addWidget(res_container)

        # ── Bottom Action Bar ─────────────────────────────────────
        card_layout.addWidget(self._divider())

        action_bar = QWidget(self.card)
        action_bar.setObjectName("ActionBar")
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(16, 10, 16, 10)
        action_layout.setSpacing(8)

        self.clear_btn = QPushButton("Clear", action_bar)
        self.clear_btn.setObjectName("ClearBtn")
        self.clear_btn.setIcon(get_icon("trash", color="#888888", size=13))
        self.clear_btn.clicked.connect(self._clear_all)
        action_layout.addWidget(self.clear_btn)

        action_layout.addStretch()

        self.status_lbl = QLabel("", action_bar)
        self.status_lbl.setObjectName("StatusLabel")
        action_layout.addWidget(self.status_lbl)

        self.translate_btn = QPushButton("Translate", action_bar)
        self.translate_btn.setObjectName("TranslateBtn")
        self.translate_btn.setIcon(get_icon("zap", color="#12141A", size=14))
        self.translate_btn.setMinimumWidth(120)
        self.translate_btn.clicked.connect(self.do_translate)
        action_layout.addWidget(self.translate_btn)

        card_layout.addWidget(action_bar)

        outer.addWidget(self.card)

        # Drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setColor(__import__('PySide6.QtGui', fromlist=['QColor']).QColor(0, 0, 0, 140))
        shadow.setOffset(0, 8)
        self.card.setGraphicsEffect(shadow)

    def _divider(self) -> QFrame:
        d = QFrame()
        d.setFrameShape(QFrame.Shape.HLine)
        d.setObjectName("Divider")
        return d

    def _apply_style(self) -> None:
        a = self._accent
        a_hover = f"rgba({int(a[1:3], 16)}, {int(a[3:5], 16)}, {int(a[5:7], 16)}, 0.85)" if a.startswith("#") and len(a) == 7 else a
        self.setStyleSheet(f"""
            QWidget#QTCard {{
                background-color: #16181F;
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.08);
            }}
            QWidget#QTHeader {{
                background-color: #121318;
                border-radius: 12px 12px 0 0;
            }}
            QLabel#QTTitle {{
                color: #FFFFFF;
                font-size: 13px;
                font-weight: 600;
                font-family: 'Segoe UI';
            }}
            QPushButton#HeaderBtn {{
                background: transparent;
                border: none;
                border-radius: 4px;
            }}
            QPushButton#HeaderBtn:hover {{
                background: rgba(255, 255, 255, 0.08);
            }}
            QPushButton#HeaderBtn:checked {{
                background: rgba(0, 173, 181, 0.15);
            }}
            QPushButton#CloseBtn {{
                background: transparent;
                border: none;
                border-radius: 4px;
            }}
            QPushButton#CloseBtn:hover {{
                background: rgba(255, 80, 80, 0.2);
            }}
            QFrame#Divider {{
                color: rgba(255, 255, 255, 0.06);
                height: 1px;
            }}
            QWidget#LangRow {{
                background-color: #121318;
            }}
            QComboBox#LangCombo {{
                background-color: #20232C;
                color: #E0E0E0;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
                font-family: 'Segoe UI';
            }}
            QComboBox#LangCombo::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox#LangCombo:focus {{
                border: 1px solid {a};
            }}
            QComboBox QAbstractItemView {{
                background-color: #20232C;
                color: #E0E0E0;
                border: 1px solid rgba(255, 255, 255, 0.1);
                selection-background-color: {a};
                selection-color: #12141A;
            }}
            QPushButton#SwapBtn {{
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
            }}
            QPushButton#SwapBtn:hover {{
                background-color: {a};
                border-color: {a};
            }}
            QWidget#InputContainer, QWidget#ResultContainer {{
                background-color: transparent;
            }}
            QLabel#SectionLabel {{
                color: #777777;
                font-size: 10px;
                font-weight: 600;
                font-family: 'Segoe UI';
                letter-spacing: 0.8px;
            }}
            QTextEdit#SrcInput {{
                background-color: #20232C;
                color: #F0F0F0;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 8px;
                padding: 8px;
                selection-background-color: {a};
            }}
            QTextEdit#SrcInput:focus {{
                border: 1px solid {a};
            }}
            QLabel#ResultLabel {{
                color: #F0F0F0;
                background-color: #20232C;
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 8px;
                padding: 10px;
            }}
            QLabel#CharCount {{
                color: #555555;
                font-size: 10px;
                font-family: 'Segoe UI';
            }}
            QPushButton#CopyBtn {{
                background-color: transparent;
                color: {a};
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 5px;
                padding: 3px 10px;
                font-size: 11px;
                font-family: 'Segoe UI';
            }}
            QPushButton#CopyBtn:hover {{
                background-color: {a};
                color: #12141A;
            }}
            QWidget#ActionBar {{
                background-color: #121318;
                border-radius: 0 0 12px 12px;
            }}
            QPushButton#ClearBtn {{
                background-color: rgba(255, 255, 255, 0.04);
                color: #888888;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                padding: 6px 14px;
                font-size: 12px;
                font-family: 'Segoe UI';
            }}
            QPushButton#ClearBtn:hover {{
                background-color: rgba(255, 80, 80, 0.15);
                color: #FF5555;
                border-color: rgba(255, 80, 80, 0.3);
            }}
            QPushButton#TranslateBtn {{
                background-color: {a};
                color: #12141A;
                border: none;
                border-radius: 6px;
                padding: 7px 18px;
                font-size: 12px;
                font-weight: 600;
                font-family: 'Segoe UI';
            }}
            QPushButton#TranslateBtn:hover {{
                background-color: #00FFF5;
            }}
            QPushButton#TranslateBtn:disabled {{
                background-color: #2D303A;
                color: #555555;
            }}
            QLabel#StatusLabel {{
                color: #888888;
                font-size: 11px;
                font-family: 'Segoe UI';
            }}
        """)

    def set_accent(self, color: str) -> None:
        self._accent = color
        self.title_icon.setPixmap(get_pixmap("zap", color=color, size=18))
        self.swap_btn.setIcon(get_icon("swap", color=color, size=16))
        self.copy_btn.setIcon(get_icon("copy", color=color, size=13))
        self._apply_style()

    def set_settings(self, settings) -> None:
        idx = self.cmb_src.findData(settings.source_lang)
        if idx >= 0:
            self.cmb_src.setCurrentIndex(idx)
        idx = self.cmb_tgt.findData(settings.target_lang)
        if idx >= 0:
            self.cmb_tgt.setCurrentIndex(idx)

    def _center_on_screen(self) -> None:
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            self.move(
                geo.center().x() - self.width() // 2,
                geo.center().y() - self.height() // 2 - 40
            )

    def _on_pin_toggled(self, pinned: bool) -> None:
        if pinned:
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            self.pin_btn.setIcon(get_icon("pin", color=self._accent, size=15))
        else:
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            self.pin_btn.setIcon(get_icon("pin", color="#888888", size=15))
        self.show()

    def _on_src_changed(self) -> None:
        text = self.src_input.toPlainText()
        count = len(text)
        self.char_count.setText(f"{count} / 5000")
        if count > 5000:
            self.src_input.setPlainText(text[:5000])

    def _swap_langs(self) -> None:
        src_data = self.cmb_src.currentData()
        tgt_data = self.cmb_tgt.currentData()
        idx_s = self.cmb_src.findData(tgt_data)
        if idx_s >= 0:
            self.cmb_src.setCurrentIndex(idx_s)
        idx_t = self.cmb_tgt.findData(src_data)
        if idx_t >= 0:
            self.cmb_tgt.setCurrentIndex(idx_t)
        src_text = self.src_input.toPlainText()
        res_text = self.result_label.text()
        if res_text:
            self.src_input.setPlainText(res_text)
            self.result_label.setText(src_text)

    def do_translate(self) -> None:
        text = self.src_input.toPlainText().strip()
        if not text:
            return
        if not self.translation_mgr:
            self.result_label.setText("Translation manager not available.")
            return

        self.translate_btn.setEnabled(False)
        self.translate_btn.setText("Translating...")
        self.status_lbl.setText("Translating...")
        self.result_label.setText("")

        s = self.settings_mgr.settings if self.settings_mgr else None
        source = self.cmb_src.currentData()
        target = self.cmb_tgt.currentData()
        provider = s.provider if s else "google_free"
        api_key = s.api_key if s else ""
        extra = s.to_dict() if s else {}

        self._thread = QThread()
        self._worker = TranslateWorker(
            self.translation_mgr, text, source, target, provider, api_key, extra
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_translated)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.start()

    def _on_translated(self, result: str) -> None:
        self.result_label.setText(result)
        self.translate_btn.setEnabled(True)
        self.translate_btn.setText("Translate")
        self.status_lbl.setText("Done")
        QTimer.singleShot(2000, lambda: self.status_lbl.setText(""))

    def _on_error(self, msg: str) -> None:
        self.result_label.setText(f"Error: {msg}")
        self.translate_btn.setEnabled(True)
        self.translate_btn.setText("Translate")
        self.status_lbl.setText("")

    def _copy_result(self) -> None:
        text = self.result_label.text()
        if text and not text.startswith("Error:"):
            QApplication.clipboard().setText(text)
            self.copy_btn.setText("Copied")
            self.copy_btn.setIcon(get_icon("check", color="#27AE60", size=13))
            QTimer.singleShot(1500, lambda: self.copy_btn.setText("Copy") or self.copy_btn.setIcon(get_icon("copy", color=self._accent, size=13)))

    def _clear_all(self) -> None:
        self.src_input.clear()
        self.result_label.clear()
        self.status_lbl.setText("")
        self.char_count.setText("0 / 5000")

    def toggle_visibility(self) -> None:
        if self.isVisible():
            self.hide()
        else:
            self._center_on_screen()
            self.show()
            self.raise_()
            self.activateWindow()
            self.src_input.setFocus()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() == Qt.MouseButton.LeftButton and hasattr(self, '_drag_pos'):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)
