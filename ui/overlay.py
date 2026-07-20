from PySide6.QtCore import Qt, QTimer, QPoint, Signal
from PySide6.QtGui import QCursor, QFont, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGraphicsDropShadowEffect, QPushButton, QApplication
)
from ui.icons import get_pixmap, get_icon


class TranslationOverlay(QWidget):
    """A floating, borderless, semi-transparent widget displaying translations near the cursor."""

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
        self._copy_target = ""

        self._build_ui()
        self._apply_style()

        # Auto-hide timer
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)

        # Main card frame
        self.frame = QWidget(self)
        self.frame.setObjectName("OverlayFrame")
        frame_layout = QVBoxLayout(self.frame)
        frame_layout.setContentsMargins(14, 10, 14, 10)
        frame_layout.setSpacing(6)

        # Top row: vector globe icon + close button
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.icon_lbl = QLabel(self.frame)
        self.icon_lbl.setFixedSize(18, 18)
        self.icon_lbl.setPixmap(get_pixmap("app_logo", size=18))
        top_row.addWidget(self.icon_lbl)

        title_lbl = QLabel("GlotWeave", self.frame)
        title_lbl.setObjectName("HeaderTitle")
        top_row.addWidget(title_lbl)

        top_row.addStretch()

        self.close_btn = QPushButton(self.frame)
        self.close_btn.setObjectName("CloseBtn")
        self.close_btn.setFixedSize(22, 22)
        self.close_btn.setIcon(get_icon("close", color="#888888", size=14))
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.clicked.connect(self.hide)
        top_row.addWidget(self.close_btn)

        frame_layout.addLayout(top_row)

        # Translation text label
        self.label = QLabel(self.frame)
        self.label.setWordWrap(True)
        self.label.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
        self.label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.label.setMaximumWidth(380)
        self.label.setObjectName("TranslationLabel")
        frame_layout.addWidget(self.label)

        # Bottom row: copy button
        bottom_row = QHBoxLayout()
        bottom_row.addStretch()

        self.copy_btn = QPushButton("Copy", self.frame)
        self.copy_btn.setObjectName("CopyBtn")
        self.copy_btn.setIcon(get_icon("copy", color=self._accent, size=13))
        self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_btn.clicked.connect(self._copy_text)
        bottom_row.addWidget(self.copy_btn)

        frame_layout.addLayout(bottom_row)

        outer.addWidget(self.frame)

        # Soft glow drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 180))
        shadow.setOffset(0, 6)
        self.frame.setGraphicsEffect(shadow)

    def _apply_style(self) -> None:
        a = self._accent
        self.setStyleSheet(f"""
            QWidget#OverlayFrame {{
                background-color: rgba(18, 20, 26, 0.95);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 10px;
            }}
            QLabel#HeaderTitle {{
                color: #888888;
                font-size: 11px;
                font-weight: 600;
                font-family: 'Segoe UI';
                letter-spacing: 0.5px;
            }}
            QLabel#TranslationLabel {{
                color: #FFFFFF;
                font-size: 13px;
                line-height: 1.5;
            }}
            QPushButton#CloseBtn {{
                background: transparent;
                border: none;
                border-radius: 4px;
            }}
            QPushButton#CloseBtn:hover {{
                background: rgba(255, 80, 80, 0.2);
            }}
            QPushButton#CopyBtn {{
                background-color: rgba(255, 255, 255, 0.05);
                color: {a};
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 6px;
                padding: 4px 12px;
                font-size: 11px;
                font-family: 'Segoe UI';
                font-weight: 600;
            }}
            QPushButton#CopyBtn:hover {{
                background-color: {a};
                color: #12141A;
                border-color: {a};
            }}
        """)

    def set_accent(self, color: str) -> None:
        """Update the accent color."""
        self._accent = color
        self.icon_lbl.setPixmap(get_pixmap("globe", color=color, size=16))
        self.copy_btn.setIcon(get_icon("copy", color=color, size=13))
        self._apply_style()

    def show_translation(self, text: str, duration_ms: int = 4000) -> None:
        """Display translation text near cursor position."""
        self.label.setText(text)
        self._copy_target = text
        self.copy_btn.setText("Copy")
        self.copy_btn.setIcon(get_icon("copy", color=self._accent, size=13))
        self.adjustSize()

        cursor_pos = QCursor.pos()
        screen = self.screen()
        if screen:
            screen_geo = screen.geometry()
            x = cursor_pos.x() + 16
            y = cursor_pos.y() + 16
            if x + self.width() > screen_geo.right():
                x = cursor_pos.x() - self.width() - 16
            if y + self.height() > screen_geo.bottom():
                y = cursor_pos.y() - self.height() - 16
            self.move(QPoint(max(0, x), max(0, y)))

        self.show()
        if duration_ms > 0:
            self.timer.start(duration_ms)

    def _copy_text(self) -> None:
        if self._copy_target:
            QApplication.clipboard().setText(self._copy_target)
            self.copy_btn.setText("Copied")
            self.copy_btn.setIcon(get_icon("check", color="#27AE60", size=13))
            QTimer.singleShot(1600, lambda: self.copy_btn.setText("Copy") or self.copy_btn.setIcon(get_icon("copy", color=self._accent, size=13)))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if event.buttons() == Qt.MouseButton.LeftButton and hasattr(self, '_drag_pos'):
            self.move(event.globalPosition().toPoint() - self._drag_pos)
        super().mouseMoveEvent(event)


class VoiceIndicatorOverlay(QWidget):
    """A small, elegant floating HUD indicator widget showing voice translation status."""

    stop_requested = Signal()

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
        self._accent = "#5CB868"
        self._pulse_state = False

        self._build_ui()
        self._apply_style()

        # Pulsing dot timer for dynamic listening animation
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._toggle_pulse)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 6, 6, 6)

        self.frame = QWidget(self)
        self.frame.setObjectName("VoiceIndicatorFrame")
        layout = QHBoxLayout(self.frame)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(8)

        # SVG Vector Icon Label (Microphone / Zap)
        self.icon_lbl = QLabel(self.frame)
        self.icon_lbl.setFixedSize(16, 16)
        self.icon_lbl.setPixmap(get_pixmap("mic", color="#FF4B4B", size=16))
        layout.addWidget(self.icon_lbl)

        # Pulsing Red / Accent Dot
        self.dot = QLabel(self.frame)
        self.dot.setFixedSize(10, 10)
        self.dot.setObjectName("PulseDot")
        layout.addWidget(self.dot)

        # Text label
        self.status_lbl = QLabel("Listening...", self.frame)
        self.status_lbl.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.status_lbl.setObjectName("VoiceStatusLbl")
        layout.addWidget(self.status_lbl)

        # Stop/Close Button (X)
        self.stop_btn = QPushButton(self.frame)
        self.stop_btn.setObjectName("StopVoiceBtn")
        self.stop_btn.setFixedSize(20, 20)
        self.stop_btn.setIcon(get_icon("close", color="#AAAAAA", size=12))
        self.stop_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_btn.setToolTip("Stop Voice Translation")
        self.stop_btn.clicked.connect(self.stop_requested.emit)
        layout.addWidget(self.stop_btn)

        outer.addWidget(self.frame)

        # Drop Shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 4)
        self.frame.setGraphicsEffect(shadow)

    def _apply_style(self) -> None:
        a = self._accent
        dot_bg = "#FF4B4B" if self._pulse_state else "#FF8888"
        self.setStyleSheet(f"""
            QWidget#VoiceIndicatorFrame {{
                background-color: rgba(18, 20, 26, 0.92);
                border: 1px solid {a};
                border-radius: 20px;
            }}
            QLabel#PulseDot {{
                background-color: {dot_bg};
                border-radius: 5px;
            }}
            QLabel#VoiceStatusLbl {{
                color: #FFFFFF;
                font-size: 12px;
                font-family: 'Segoe UI';
            }}
            QPushButton#StopVoiceBtn {{
                background: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 10px;
            }}
            QPushButton#StopVoiceBtn:hover {{
                background: rgba(255, 80, 80, 0.4);
            }}
        """)

    def _toggle_pulse(self) -> None:
        self._pulse_state = not self._pulse_state
        self._apply_style()

    def set_accent(self, color: str) -> None:
        self._accent = color
        self._apply_style()

    def show_listening(self, hotkey_str: str = "Ctrl+Shift+F10") -> None:
        """Show the indicator in Listening state with vector mic icon."""
        self.icon_lbl.setPixmap(get_pixmap("mic", color="#FF4B4B", size=16))
        self.status_lbl.setText(f"Listening... ({hotkey_str} to stop)")
        self._pulse_state = True
        self._apply_style()
        self._pulse_timer.start(500)
        self.adjustSize()
        self._position_top_center()
        self.show()

    def show_transcribing(self) -> None:
        """Show the indicator in Transcribing state with vector zap icon."""
        self.icon_lbl.setPixmap(get_pixmap("zap", color=self._accent, size=16))
        self.status_lbl.setText("Transcribing...")
        self._pulse_timer.stop()
        self._pulse_state = False
        self._apply_style()
        self.adjustSize()
        self._position_top_center()
        self.show()

    def hide_indicator(self) -> None:
        """Hide indicator and stop timers."""
        self._pulse_timer.stop()
        self.hide()

    def _position_top_center(self) -> None:
        """Position badge horizontally centered at the top of the primary screen."""
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.geometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + 40
            self.move(QPoint(x, y))
