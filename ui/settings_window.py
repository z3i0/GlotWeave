import logging
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QComboBox,
    QLineEdit, QPushButton, QFormLayout, QFileDialog, QMessageBox,
    QScrollArea, QWidget, QStackedWidget, QFrame, QGridLayout
)
from core.settings import Settings, SettingsManager
from core.history_manager import HistoryManager
from app.config import LANGUAGES, PROVIDERS, ACCENT_COLORS, APP_NAME, APP_VERSION, DEVELOPER, get_asset_path
from ui.icons import get_icon, get_pixmap
from ui.history_window import HistoryPage

logger = logging.getLogger(__name__)


def _lighten_color(hex_color: str, factor: float = 0.18) -> str:
    try:
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        r = min(255, int(r + (255 - r) * factor))
        g = min(255, int(g + (255 - g) * factor))
        b = min(255, int(b + (255 - b) * factor))
        return f"#{r:02X}{g:02X}{b:02X}"
    except Exception:
        return hex_color


class HotkeyLineEdit(QLineEdit):
    recording_finished = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self._is_recording = False
        self._prev_text = ""

    def is_recording(self) -> bool:
        return self._is_recording

    def start_recording(self) -> None:
        self._is_recording = True
        self._prev_text = self.text()
        self.setText("Press shortcut keys...")
        self.setFocus()

    def stop_recording(self) -> None:
        if self._is_recording:
            self._is_recording = False
            self.clearFocus()
            self.recording_finished.emit()

    def cancel_recording(self) -> None:
        if self._is_recording:
            self.setText(self._prev_text)
            self.stop_recording()

    def keyPressEvent(self, event) -> None:
        if not self._is_recording:
            super().keyPressEvent(event)
            return
        event.accept()
        key = event.key()
        modifiers = event.modifiers()
        if key == Qt.Key.Key_Escape:
            self.cancel_recording()
            return
        parts = []
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            parts.append("ctrl")
        if modifiers & Qt.KeyboardModifier.ShiftModifier:
            parts.append("shift")
        if modifiers & Qt.KeyboardModifier.AltModifier:
            parts.append("alt")
        if modifiers & Qt.KeyboardModifier.MetaModifier:
            parts.append("windows")
        is_modifier = key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta)
        if not is_modifier:
            key_str = QKeySequence(key).toString().lower()
            if key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
                key_str = "enter"
            elif key == Qt.Key.Key_Backspace:
                key_str = "backspace"
            elif key == Qt.Key.Key_Delete:
                key_str = "delete"
            elif key == Qt.Key.Key_PageUp:
                key_str = "page up"
            elif key == Qt.Key.Key_PageDown:
                key_str = "page down"
            if key_str:
                parts.append(key_str)
                self.setText("+".join(parts))
                self.stop_recording()
        else:
            self.setText("+".join(parts) + "+..." if parts else "Press shortcut keys...")

    def focusOutEvent(self, event) -> None:
        if self._is_recording:
            self.cancel_recording()
        super().focusOutEvent(event)


class ColorSwatch(QPushButton):
    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self.color = color
        self.setFixedSize(28, 28)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style(False)

    def _update_style(self, checked: bool) -> None:
        border = "2px solid #FFFFFF" if checked else "1px solid rgba(255,255,255,0.15)"
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {self.color};
                border-radius: 14px;
                border: {border};
            }}
        """)

    def setChecked(self, checked: bool) -> None:
        super().setChecked(checked)
        self._update_style(checked)


class SidebarItem(QWidget):
    clicked = Signal()

    def __init__(self, icon_name: str, label: str, accent: str = "#00ADB5", parent=None):
        super().__init__(parent)
        self.icon_name = icon_name
        self.label_text = label
        self._accent = accent
        self._selected = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(10)

        # Left accent indicator bar
        self.indicator = QWidget(self)
        self.indicator.setFixedSize(3, 18)
        self.indicator.setObjectName("NavIndicator")
        layout.addWidget(self.indicator)

        self.icon_lbl = QLabel(self)
        self.icon_lbl.setFixedSize(18, 18)
        layout.addWidget(self.icon_lbl)

        self.text_lbl = QLabel(label, self)
        self.text_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
        layout.addWidget(self.text_lbl)
        layout.addStretch()

        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_icon()
        self._set_selected(False)

    def set_accent(self, accent: str) -> None:
        self._accent = accent
        self._update_icon()
        self._set_selected(self._selected)

    def _update_icon(self) -> None:
        color = self._accent if self._selected else "#888888"
        self.icon_lbl.setPixmap(get_pixmap(self.icon_name, color=color, size=18))

    def _set_selected(self, sel: bool) -> None:
        self._selected = sel
        self._update_icon()
        a = self._accent
        if sel:
            self.indicator.setStyleSheet(f"background-color: {a}; border-radius: 2px;")
            self.setStyleSheet(f"""
                QWidget {{ background-color: rgba(255, 255, 255, 0.05); border-radius: 6px; }}
                QLabel {{ color: {a}; font-weight: 600; }}
            """)
        else:
            self.indicator.setStyleSheet("background-color: transparent;")
            self.setStyleSheet("""
                QWidget { background-color: transparent; border-radius: 6px; }
                QLabel { color: #888888; }
                QWidget:hover { background-color: rgba(255, 255, 255, 0.03); }
                QLabel:hover { color: #CCCCCC; }
            """)

    def select(self):
        self._set_selected(True)

    def deselect(self):
        self._set_selected(False)

    def mousePressEvent(self, event) -> None:
        self.clicked.emit()
        super().mousePressEvent(event)


class SettingsWindow(QDialog):
    """Modern Settings Window with clean SVG icons and sidebar navigation."""
    settings_updated = Signal(Settings)

    _SECTIONS = [
        ("settings", "General"),
        ("languages", "Translation"),
        ("mic", "Voice"),
        ("api", "Providers"),
        ("palette", "Appearance"),
        ("history", "History"),
        ("keyboard", "Shortcuts"),
        ("info", "About"),
    ]

    def __init__(self, settings_manager: SettingsManager, history_manager: HistoryManager | None = None, parent=None):
        super().__init__(parent)
        self.settings_manager = settings_manager
        self.history_manager = history_manager
        self.settings = self.settings_manager.settings
        self._accent = ACCENT_COLORS.get(self.settings.accent_color, "#00ADB5")
        self._sidebar_items: list[SidebarItem] = []
        self._color_swatches: dict[str, ColorSwatch] = {}

        self.setWindowTitle(f"{APP_NAME} Settings")
        self.resize(740, 580)
        self.setMinimumSize(680, 520)

        self._build_ui()
        self._apply_style()
        self.load_settings()
        self._select_section(0)

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sidebar ──────────────────────────────────────────────
        self.sidebar = QWidget(self)
        self.sidebar.setObjectName("Sidebar")
        self.sidebar.setFixedWidth(200)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(12, 16, 12, 16)
        sidebar_layout.setSpacing(4)

        # App Brand Header
        brand_row = QHBoxLayout()
        brand_row.setSpacing(8)
        self.brand_icon = QLabel(self.sidebar)
        self.brand_icon.setFixedSize(24, 24)
        self.brand_icon.setPixmap(get_pixmap("app_logo", size=24))
        brand_row.addWidget(self.brand_icon)

        app_title = QLabel(APP_NAME, self.sidebar)
        app_title.setObjectName("AppTitle")
        brand_row.addWidget(app_title)
        brand_row.addStretch()

        ver_lbl = QLabel(f"v{APP_VERSION}", self.sidebar)
        ver_lbl.setObjectName("VersionLabel")
        brand_row.addWidget(ver_lbl)

        sidebar_layout.addLayout(brand_row)
        sidebar_layout.addSpacing(16)

        for icon_name, label in self._SECTIONS:
            item = SidebarItem(icon_name, label, accent=self._accent, parent=self.sidebar)
            item.clicked.connect(lambda i=len(self._sidebar_items): self._select_section(i))
            self._sidebar_items.append(item)
            sidebar_layout.addWidget(item)

        sidebar_layout.addStretch()

        self.btn_save = QPushButton("Save Changes", self.sidebar)
        self.btn_save.setObjectName("SaveBtn")
        self.btn_save.setIcon(get_icon("check", color="#12141A", size=15))
        self.btn_save.clicked.connect(self.save_settings)
        sidebar_layout.addWidget(self.btn_save)

        root.addWidget(self.sidebar)

        # ── Content Wrapper ──────────────────────────────────────
        content_wrapper = QWidget(self)
        content_wrapper.setObjectName("ContentWrapper")
        content_v = QVBoxLayout(content_wrapper)
        content_v.setContentsMargins(0, 0, 0, 0)
        content_v.setSpacing(0)

        # Title bar
        self.title_bar = QWidget(content_wrapper)
        self.title_bar.setObjectName("TitleBar")
        self.title_bar.setFixedHeight(52)
        title_bar_layout = QHBoxLayout(self.title_bar)
        title_bar_layout.setContentsMargins(24, 0, 16, 0)

        self.page_title = QLabel("General", self.title_bar)
        self.page_title.setObjectName("PageTitle")
        title_bar_layout.addWidget(self.page_title)
        title_bar_layout.addStretch()
        content_v.addWidget(self.title_bar)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("TitleSep")
        content_v.addWidget(sep)

        # Stacked pages
        self.stack = QStackedWidget(content_wrapper)
        self.stack.setObjectName("ContentStack")

        self._page_general = self._make_scroll(self._build_general_page())
        self._page_translation = self._make_scroll(self._build_translation_page())
        self._page_voice = self._make_scroll(self._build_voice_page())
        self._page_providers = self._make_scroll(self._build_providers_page())
        self._page_appearance = self._make_scroll(self._build_appearance_page())
        self._page_history: QWidget
        if self.history_manager is not None:
            self.history_page = HistoryPage(self.history_manager, accent=self._accent, parent=self)
            self._page_history = self.history_page
        else:
            self._page_history = QWidget()
        self._page_shortcuts = self._make_scroll(self._build_shortcuts_page())
        self._page_about = self._make_scroll(self._build_about_page())

        for p in [self._page_general, self._page_translation, self._page_voice,
                  self._page_providers, self._page_appearance, self._page_history,
                  self._page_shortcuts, self._page_about]:
            self.stack.addWidget(p)

        content_v.addWidget(self.stack)

        # Bottom Bar
        bottom = QWidget(content_wrapper)
        bottom.setObjectName("BottomBar")
        bottom.setFixedHeight(48)
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(24, 0, 16, 0)

        imp_btn = QPushButton("Import", bottom)
        imp_btn.setObjectName("SecondaryBtn")
        imp_btn.setIcon(get_icon("export", color="#888888", size=14))
        imp_btn.clicked.connect(self._import_settings)
        bottom_layout.addWidget(imp_btn)

        exp_btn = QPushButton("Export", bottom)
        exp_btn.setObjectName("SecondaryBtn")
        exp_btn.setIcon(get_icon("export", color="#888888", size=14))
        exp_btn.clicked.connect(self._export_settings)
        bottom_layout.addWidget(exp_btn)

        bottom_layout.addStretch()

        cancel_btn = QPushButton("Cancel", bottom)
        cancel_btn.setObjectName("CancelBtn")
        cancel_btn.clicked.connect(self.reject)
        bottom_layout.addWidget(cancel_btn)

        content_v.addWidget(bottom)
        root.addWidget(content_wrapper)

    def _make_scroll(self, widget: QWidget) -> QScrollArea:
        area = QScrollArea()
        area.setWidget(widget)
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.Shape.NoFrame)
        area.setObjectName("ScrollArea")
        return area

    def _select_section(self, index: int) -> None:
        for i, item in enumerate(self._sidebar_items):
            if i == index:
                item.select()
            else:
                item.deselect()
        self.stack.setCurrentIndex(index)
        self.page_title.setText(self._SECTIONS[index][1])
        if self._SECTIONS[index][0] == "history" and hasattr(self, "history_page") and self.history_page:
            self.history_page.load_history()

    def select_section_by_name(self, name: str) -> None:
        """Select sidebar tab section by its internal key (e.g. 'history')."""
        for i, (key, _) in enumerate(self._SECTIONS):
            if key == name:
                self._select_section(i)
                break

    def _section_title(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("SectionTitle")
        return lbl

    def _build_general_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(8)

        layout.addWidget(self._section_title("STARTUP"))
        self.chk_auto_start = QCheckBox("Launch GlotWeave on Windows startup")
        self.chk_start_min = QCheckBox("Start minimized to system tray")
        layout.addWidget(self.chk_auto_start)
        layout.addWidget(self.chk_start_min)

        layout.addSpacing(16)
        layout.addWidget(self._section_title("NOTIFICATIONS"))
        self.chk_notifications = QCheckBox("Enable Windows system notifications")
        layout.addWidget(self.chk_notifications)

        layout.addStretch()
        return w

    def _build_translation_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        layout.addWidget(self._section_title("TRANSLATION MODES"))
        self.chk_live_trans = QCheckBox("Live Typing — translate as you type")
        self.chk_selected_trans = QCheckBox("Translate highlighted text on Hotkey press")
        self.chk_selected_trans.setToolTip("When enabled, pressing the translation hotkey copies the selected text and replaces it with translation.")
        self.chk_clipboard_monitor = QCheckBox("Auto-translate copied text in background (Clipboard Monitor)")
        self.chk_clipboard_monitor.setToolTip("When enabled, any text copied to the clipboard is automatically translated in the background overlay.")
        self.chk_layout_switch = QCheckBox("Translate on keyboard layout change (Alt+Shift / Win+Space)")
        self.chk_auto_detect = QCheckBox("Auto-detect source language")
        layout.addWidget(self.chk_live_trans)
        layout.addWidget(self.chk_selected_trans)
        layout.addWidget(self.chk_clipboard_monitor)
        layout.addWidget(self.chk_layout_switch)
        layout.addWidget(self.chk_auto_detect)

        layout.addSpacing(16)
        layout.addWidget(self._section_title("LANGUAGES"))

        form = QFormLayout()
        form.setSpacing(10)

        self.cmb_src_lang = QComboBox()
        for code, name in LANGUAGES.items():
            self.cmb_src_lang.addItem(name, code)
        form.addRow("Source Language:", self.cmb_src_lang)

        self.cmb_tgt_lang = QComboBox()
        for code, name in LANGUAGES.items():
            if code != "auto":
                self.cmb_tgt_lang.addItem(name, code)
        form.addRow("Target Language:", self.cmb_tgt_lang)

        layout.addLayout(form)

        layout.addSpacing(16)
        layout.addWidget(self._section_title("TRANSLATION HOTKEY"))

        hk_row = QHBoxLayout()
        self.txt_hotkey = HotkeyLineEdit()
        self.txt_hotkey.setPlaceholderText("e.g. ctrl+shift+f9")
        self.txt_hotkey.recording_finished.connect(self._on_recording_finished)
        self.btn_record = QPushButton("Record")
        self.btn_record.setObjectName("RecordBtn")
        self.btn_record.setFixedWidth(90)
        self.btn_record.clicked.connect(self._toggle_recording)
        hk_row.addWidget(self.txt_hotkey)
        hk_row.addWidget(self.btn_record)
        layout.addLayout(hk_row)

        layout.addStretch()
        return w

    def _build_voice_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        layout.addWidget(self._section_title("VOICE HOTKEY"))
        hk_row = QHBoxLayout()
        self.txt_voice_hotkey = HotkeyLineEdit()
        self.txt_voice_hotkey.setPlaceholderText("e.g. ctrl+shift+f10")
        self.txt_voice_hotkey.recording_finished.connect(self._on_recording_finished_voice)
        self.btn_record_voice = QPushButton("Record")
        self.btn_record_voice.setObjectName("RecordBtn")
        self.btn_record_voice.setFixedWidth(90)
        self.btn_record_voice.clicked.connect(self._toggle_recording_voice)
        hk_row.addWidget(self.txt_voice_hotkey)
        hk_row.addWidget(self.btn_record_voice)
        layout.addLayout(hk_row)

        layout.addSpacing(12)
        layout.addWidget(self._section_title("RECORDING PARAMETERS"))

        form = QFormLayout()
        form.setSpacing(10)

        self.cmb_voice_sensitivity = QComboBox()
        self.cmb_voice_sensitivity.addItem("High — Quiet Room", "high")
        self.cmb_voice_sensitivity.addItem("Medium — Default", "medium")
        self.cmb_voice_sensitivity.addItem("Low — Noisy Room", "low")
        form.addRow("Sensitivity:", self.cmb_voice_sensitivity)

        self.cmb_voice_silence = QComboBox()
        for val, label in [(1.0, "1.0s — Fast"), (1.5, "1.5s"), (2.0, "2.0s — Default"),
                           (2.5, "2.5s"), (3.0, "3.0s"), (4.0, "4.0s — Slow")]:
            self.cmb_voice_silence.addItem(label, val)
        form.addRow("Silence Pause:", self.cmb_voice_silence)

        self.cmb_voice_timeout = QComboBox()
        for val, label in [(3.0, "3s"), (5.0, "5s — Default"), (8.0, "8s"), (10.0, "10s")]:
            self.cmb_voice_timeout.addItem(label, val)
        form.addRow("Start Timeout:", self.cmb_voice_timeout)

        layout.addLayout(form)

        layout.addSpacing(8)
        self.chk_continuous_voice = QCheckBox("Enable continuous voice monitoring")
        layout.addWidget(self.chk_continuous_voice)

        layout.addStretch()
        return w

    def _build_providers_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        layout.addWidget(self._section_title("TRANSLATION PROVIDER"))

        form = QFormLayout()
        form.setSpacing(10)

        self.cmb_provider = QComboBox()
        for code, name in PROVIDERS.items():
            self.cmb_provider.addItem(name, code)
        self.cmb_provider.currentIndexChanged.connect(self._on_provider_changed)
        form.addRow("Provider:", self.cmb_provider)

        self.txt_api_key = QLineEdit()
        self.txt_api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_api_key.setPlaceholderText("Paste your API key here")
        form.addRow("API Key:", self.txt_api_key)

        layout.addLayout(form)

        layout.addSpacing(12)
        layout.addWidget(self._section_title("OLLAMA (OFFLINE LLM)"))

        form2 = QFormLayout()
        form2.setSpacing(10)
        self.txt_ollama_url = QLineEdit()
        self.txt_ollama_model = QLineEdit()
        form2.addRow("Endpoint:", self.txt_ollama_url)
        form2.addRow("Model:", self.txt_ollama_model)
        layout.addLayout(form2)

        layout.addSpacing(12)
        layout.addWidget(self._section_title("DEEPL API"))
        form3 = QFormLayout()
        form3.setSpacing(10)
        self.txt_deepl_url = QLineEdit()
        form3.addRow("Endpoint:", self.txt_deepl_url)
        layout.addLayout(form3)

        layout.addStretch()
        return w

    def _build_appearance_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        layout.addWidget(self._section_title("ACCENT COLOR"))

        swatch_row = QHBoxLayout()
        swatch_row.setSpacing(10)
        self._swatch_group: list[ColorSwatch] = []

        for key, hex_color in ACCENT_COLORS.items():
            swatch = ColorSwatch(hex_color)
            swatch.clicked.connect(lambda checked, k=key, s=swatch: self._on_color_selected(k, s))
            swatch.setToolTip(key.capitalize())
            self._color_swatches[key] = swatch
            self._swatch_group.append(swatch)
            swatch_row.addWidget(swatch)
        swatch_row.addStretch()
        layout.addLayout(swatch_row)

        layout.addSpacing(16)
        layout.addWidget(self._section_title("OVERLAY DISPLAY"))

        form = QFormLayout()
        form.setSpacing(10)

        self.cmb_overlay_duration = QComboBox()
        for ms, label in [(2000, "2 seconds"), (4000, "4 seconds — Default"),
                           (6000, "6 seconds"), (8000, "8 seconds"), (0, "Persistent (manual close)")]:
            self.cmb_overlay_duration.addItem(label, ms)
        form.addRow("Display Duration:", self.cmb_overlay_duration)

        layout.addLayout(form)
        layout.addStretch()
        return w

    def _on_color_selected(self, key: str, selected_swatch: ColorSwatch) -> None:
        for s in self._swatch_group:
            s.setChecked(s is selected_swatch)
        self._selected_accent = key
        self._accent = ACCENT_COLORS.get(key, "#00ADB5")
        self.brand_icon.setPixmap(get_pixmap("globe", color=self._accent, size=22))
        for item in self._sidebar_items:
            item.set_accent(self._accent)
        self._apply_style()

    def _build_shortcuts_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)

        layout.addWidget(self._section_title("KEYBOARD SHORTCUTS"))

        shortcuts = [
            ("Translate Selected Text", "Ctrl+Shift+F9"),
            ("Voice Translate", "Ctrl+Shift+F10"),
            ("Quick Translate Panel", "Ctrl+Shift+Q"),
            ("Dismiss Overlay", "Click window or Esc"),
            ("Copy Overlay Result", "Click Copy button"),
            ("Pause / Resume Monitoring", "Tray menu → Pause"),
        ]

        grid = QGridLayout()
        grid.setSpacing(10)
        grid.setColumnMinimumWidth(0, 220)

        for row, (action, keys) in enumerate(shortcuts):
            action_lbl = QLabel(action)
            action_lbl.setObjectName("ShortcutAction")
            keys_lbl = QLabel(keys)
            keys_lbl.setObjectName("ShortcutKey")
            grid.addWidget(action_lbl, row, 0)
            grid.addWidget(keys_lbl, row, 1)

        layout.addLayout(grid)
        layout.addStretch()
        return w

    def _build_about_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        # Centered Hero Card
        hero_card = QWidget(w)
        hero_card.setObjectName("AboutHeroCard")
        hero_layout = QVBoxLayout(hero_card)
        hero_layout.setContentsMargins(32, 28, 32, 28)
        hero_layout.setSpacing(10)
        hero_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        logo = QLabel(hero_card)
        logo.setFixedSize(72, 72)
        logo.setPixmap(get_pixmap("app_logo", size=72))
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(logo, alignment=Qt.AlignmentFlag.AlignCenter)

        name_lbl = QLabel(APP_NAME, hero_card)
        name_lbl.setObjectName("AboutAppName")
        name_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(name_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        ver_lbl = QLabel(f"Version {APP_VERSION}", hero_card)
        ver_lbl.setObjectName("AboutVersion")
        ver_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(ver_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        dev_lbl = QLabel(f"Developed by {DEVELOPER}", hero_card)
        dev_lbl.setObjectName("AboutDev")
        dev_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(dev_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        hero_layout.addSpacing(6)

        desc = QLabel(
            "GlotWeave is a lightweight, high-performance desktop translation assistant.\n"
            "Translate selected text, continuous voice input, or quick panel entries.",
            hero_card
        )
        desc.setObjectName("AboutDesc")
        desc.setWordWrap(True)
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hero_layout.addWidget(desc, alignment=Qt.AlignmentFlag.AlignCenter)

        hero_layout.addSpacing(14)

        check_btn = QPushButton("Check for Updates", hero_card)
        check_btn.setObjectName("AboutBtn")
        check_btn.setIcon(get_icon("search", color=self._accent, size=14))
        check_btn.clicked.connect(lambda: QMessageBox.information(
            self, "Updates", "You are running the latest version of GlotWeave."
        ))
        hero_layout.addWidget(check_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(hero_card, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
        return w

    def _apply_style(self) -> None:
        a = self._accent
        a_hover = _lighten_color(a, 0.18)
        check_icon_path = get_asset_path("assets/check_dark.png").as_posix()
        self.setStyleSheet(f"""
            QDialog {{ background-color: #16181F; }}

            /* Sidebar */
            QWidget#Sidebar {{
                background-color: #121318;
                border-right: 1px solid rgba(255, 255, 255, 0.06);
            }}
            QLabel#AppTitle {{
                color: #FFFFFF;
                font-size: 14px;
                font-weight: 700;
                font-family: 'Segoe UI';
            }}
            QLabel#VersionLabel {{
                color: #555555;
                font-size: 10px;
                font-family: 'Segoe UI';
            }}
            QPushButton#SaveBtn {{
                background-color: {a};
                color: #12141A;
                border: none;
                border-radius: 6px;
                padding: 9px;
                font-size: 12px;
                font-weight: 600;
                font-family: 'Segoe UI';
            }}
            QPushButton#SaveBtn:hover {{ background-color: {a_hover}; }}

            /* Content Area */
            QWidget#ContentWrapper {{ background-color: #16181F; }}
            QWidget#TitleBar {{ background-color: #16181F; }}
            QFrame#TitleSep {{ color: rgba(255, 255, 255, 0.06); }}
            QLabel#PageTitle {{
                color: #FFFFFF;
                font-size: 15px;
                font-weight: 600;
                font-family: 'Segoe UI';
            }}
            QPushButton#TitleCloseBtn {{
                background: transparent;
                border: none;
                border-radius: 4px;
            }}
            QPushButton#TitleCloseBtn:hover {{ background: rgba(255, 80, 80, 0.2); }}

            QScrollArea#ScrollArea {{ background: transparent; border: none; }}
            QWidget#ContentStack {{ background: transparent; }}

            /* Section headers */
            QLabel#SectionTitle {{
                color: {a};
                font-size: 10px;
                font-weight: 700;
                font-family: 'Segoe UI';
                letter-spacing: 1px;
                padding-bottom: 2px;
            }}

            /* Controls */
            QLabel {{
                color: #CCCCCC;
                font-size: 12px;
                font-family: 'Segoe UI';
            }}
            QCheckBox {{
                color: #CCCCCC;
                font-size: 12px;
                font-family: 'Segoe UI';
                spacing: 10px;
                padding: 5px 0;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid rgba(255, 255, 255, 0.2);
                background-color: #20232C;
            }}
            QCheckBox::indicator:hover {{
                border: 1px solid {a};
                background-color: #262A36;
            }}
            QCheckBox::indicator:checked {{
                background-color: {a};
                border: 1px solid {a};
                image: url("{check_icon_path}");
            }}
            QComboBox, QLineEdit {{
                background-color: #20232C;
                color: #E0E0E0;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 12px;
                font-family: 'Segoe UI';
            }}
            QComboBox:focus, QLineEdit:focus {{
                border: 1px solid {a};
            }}
            QComboBox::drop-down {{
                border: none;
                width: 20px;
            }}
            QComboBox QAbstractItemView {{
                background-color: #20232C;
                color: #E0E0E0;
                border: 1px solid rgba(255, 255, 255, 0.1);
                selection-background-color: {a};
                selection-color: #12141A;
            }}
            QPushButton#RecordBtn {{
                background-color: rgba(255, 255, 255, 0.05);
                color: {a};
                border: 1px solid {a};
                border-radius: 6px;
                padding: 6px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton#RecordBtn:hover {{ background-color: {a}; color: #12141A; }}

            /* Bottom bar */
            QWidget#BottomBar {{
                background-color: #121318;
                border-top: 1px solid rgba(255, 255, 255, 0.06);
            }}
            QPushButton#SecondaryBtn {{
                background-color: rgba(255, 255, 255, 0.04);
                color: #888888;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                padding: 5px 14px;
                font-size: 11px;
            }}
            QPushButton#SecondaryBtn:hover {{ background-color: rgba(255, 255, 255, 0.08); color: #E0E0E0; }}
            QPushButton#CancelBtn {{
                background-color: transparent;
                color: #888888;
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 6px;
                padding: 5px 16px;
                font-size: 12px;
            }}
            QPushButton#CancelBtn:hover {{ color: #FFFFFF; border-color: rgba(255, 255, 255, 0.2); }}

            /* Shortcuts */
            QLabel#ShortcutAction {{ color: #CCCCCC; font-size: 12px; }}
            QLabel#ShortcutKey {{
                color: {a};
                font-family: 'Consolas', monospace;
                font-size: 11px;
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 4px;
                padding: 3px 8px;
            }}

            /* About */
            QWidget#AboutHeroCard {{
                background-color: #20232C;
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.08);
            }}
            QLabel#AboutAppName {{
                color: #FFFFFF;
                font-size: 20px;
                font-weight: 700;
                font-family: 'Segoe UI';
            }}
            QLabel#AboutVersion {{ color: {a}; font-size: 12px; }}
            QLabel#AboutDev {{ color: #888888; font-size: 12px; }}
            QLabel#AboutDesc {{
                color: #777777;
                font-size: 12px;
                line-height: 1.5;
                padding: 0 16px;
            }}
            QPushButton#AboutBtn {{
                background-color: rgba(255, 255, 255, 0.05);
                color: {a};
                border: 1px solid {a};
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 12px;
                font-weight: 600;
            }}
            QPushButton#AboutBtn:hover {{ background-color: {a}; color: #12141A; }}
        """)

    def _on_provider_changed(self) -> None:
        provider = self.cmb_provider.currentData()
        self.txt_api_key.setEnabled(provider != "google_free" and provider != "ollama")
        self.txt_ollama_url.setEnabled(provider == "ollama")
        self.txt_ollama_model.setEnabled(provider == "ollama")

    def _toggle_recording(self) -> None:
        if self.txt_hotkey.is_recording():
            self.txt_hotkey.stop_recording()
        else:
            self.txt_hotkey.start_recording()
            self.btn_record.setText("Stop")

    def _on_recording_finished(self) -> None:
        self.btn_record.setText("Record")

    def _toggle_recording_voice(self) -> None:
        if self.txt_voice_hotkey.is_recording():
            self.txt_voice_hotkey.stop_recording()
        else:
            self.txt_voice_hotkey.start_recording()
            self.btn_record_voice.setText("Stop")

    def _on_recording_finished_voice(self) -> None:
        self.btn_record_voice.setText("Record")

    def load_settings(self) -> None:
        s = self.settings
        self.chk_auto_start.setChecked(s.auto_start)
        self.chk_start_min.setChecked(s.start_minimized)
        self.chk_notifications.setChecked(s.notifications)
        self.chk_live_trans.setChecked(s.live_translation)
        self.chk_selected_trans.setChecked(s.translate_selected)
        self.chk_clipboard_monitor.setChecked(s.clipboard_monitor)
        self.chk_layout_switch.setChecked(s.translate_on_layout_switch)
        self.chk_continuous_voice.setChecked(s.continuous_voice)
        self.chk_auto_detect.setChecked(s.auto_detect)

        self.cmb_src_lang.setCurrentIndex(self.cmb_src_lang.findData(s.source_lang))
        self.cmb_tgt_lang.setCurrentIndex(self.cmb_tgt_lang.findData(s.target_lang))
        self.cmb_provider.setCurrentIndex(self.cmb_provider.findData(s.provider))

        self.txt_hotkey.setText(s.hotkey)
        self.txt_voice_hotkey.setText(s.voice_hotkey)
        self.txt_api_key.setText(s.api_key)
        self.txt_ollama_url.setText(s.ollama_url)
        self.txt_ollama_model.setText(s.ollama_model)
        self.txt_deepl_url.setText(s.deepl_url)

        self.cmb_voice_sensitivity.setCurrentIndex(self.cmb_voice_sensitivity.findData(s.voice_sensitivity))
        self.cmb_voice_silence.setCurrentIndex(self.cmb_voice_silence.findData(s.voice_silence_duration))
        self.cmb_voice_timeout.setCurrentIndex(self.cmb_voice_timeout.findData(s.voice_start_timeout))
        self.cmb_overlay_duration.setCurrentIndex(self.cmb_overlay_duration.findData(s.overlay_duration))

        self._selected_accent = s.accent_color
        for key, swatch in self._color_swatches.items():
            swatch.setChecked(key == s.accent_color)

        self._on_provider_changed()

    def save_settings(self) -> None:
        hotkey = self.txt_hotkey.text().strip().lower()
        voice_hotkey = self.txt_voice_hotkey.text().strip().lower()
        if not hotkey:
            QMessageBox.warning(self, "Validation", "Translation hotkey cannot be empty.")
            return
        if not voice_hotkey:
            QMessageBox.warning(self, "Validation", "Voice hotkey cannot be empty.")
            return

        accent = getattr(self, "_selected_accent", self.settings.accent_color)

        s = Settings(
            auto_start=self.chk_auto_start.isChecked(),
            start_minimized=self.chk_start_min.isChecked(),
            notifications=self.chk_notifications.isChecked(),
            live_translation=self.chk_live_trans.isChecked(),
            translate_selected=self.chk_selected_trans.isChecked(),
            clipboard_monitor=self.chk_clipboard_monitor.isChecked(),
            translate_on_layout_switch=self.chk_layout_switch.isChecked(),
            continuous_voice=self.chk_continuous_voice.isChecked(),
            voice_silence_duration=float(self.cmb_voice_silence.currentData()),
            voice_sensitivity=self.cmb_voice_sensitivity.currentData(),
            voice_start_timeout=float(self.cmb_voice_timeout.currentData()),
            auto_detect=self.chk_auto_detect.isChecked(),
            source_lang=self.cmb_src_lang.currentData(),
            target_lang=self.cmb_tgt_lang.currentData(),
            provider=self.cmb_provider.currentData(),
            hotkey=hotkey,
            voice_hotkey=voice_hotkey,
            quick_translate_hotkey=self.settings.quick_translate_hotkey,
            api_key=self.txt_api_key.text().strip(),
            ollama_url=self.txt_ollama_url.text().strip(),
            ollama_model=self.txt_ollama_model.text().strip(),
            deepl_url=self.txt_deepl_url.text().strip(),
            accent_color=accent,
            overlay_duration=self.cmb_overlay_duration.currentData(),
            overlay_opacity=self.settings.overlay_opacity,
            theme=self.settings.theme,
        )

        if self.settings_manager.save(s):
            self.settings_updated.emit(s)
            self.accept()
        else:
            QMessageBox.critical(self, "Save Error", "Failed to save settings.")

    def _import_settings(self) -> None:
        filepath, _ = QFileDialog.getOpenFileName(self, "Import Settings", "", "JSON Files (*.json)")
        if filepath:
            try:
                import json
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.settings = Settings.from_dict(data)
                self.load_settings()
                QMessageBox.information(self, "Success", "Settings imported successfully.")
            except Exception as e:
                QMessageBox.critical(self, "Import Error", f"Failed to import: {e}")

    def _export_settings(self) -> None:
        filepath, _ = QFileDialog.getSaveFileName(self, "Export Settings", "", "JSON Files (*.json)")
        if filepath:
            try:
                import json
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(self.settings.to_dict(), f, indent=4)
                QMessageBox.information(self, "Success", "Settings exported successfully.")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to export: {e}")
