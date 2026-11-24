"""Full-screen break overlay.

One frameless, always-on-top, translucent window per monitor. The black dim layer is
painted with per-pixel alpha in `paintEvent`, so the quote, countdown and buttons stay
fully opaque. (Window-level opacity is only used briefly for the fade animation.)
At >= 50% alpha every pixel of the window captures the mouse, so clicks cannot reach the
applications underneath. Windows' secure desktop (Ctrl+Alt+Del, UAC, lock screen) always
sits above any normal window, so the overlay can never block it.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    Signal,
    QObject,
)
from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QKeyEvent, QPainter, QScreen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from eye_break.ui import icons
from eye_break.ui.themes import DISPLAY_FAMILIES, FONT_FAMILIES

log = logging.getLogger(__name__)

EMERGENCY_HOLD_MS = 3000
TEXT = "#FFFFFF"
TEXT_MUTED = "#C2C8CF"
TEXT_SUBTLE = "#8E959D"


@dataclass
class OverlayOptions:
    opacity: int = 90
    font_scale: int = 100
    countdown_size: int = 96
    show_quote: bool = True
    show_instruction: bool = True
    show_progress: bool = True
    fade_ms: int = 400
    monitor: str = "all"  # all | primary | cursor
    accent: str = "#3CC2AE"


@dataclass
class BreakView:
    duration: float
    quote: str | None = None
    instruction: str | None = None
    mode: str = "gentle"
    can_snooze: bool = True
    snoozes_left: int | None = None  # None = unlimited
    can_skip: bool = True
    skip_needs_confirm: bool = False
    snooze_minutes: int = 5
    preview: bool = False
    heading: str = "TIME FOR AN EYE BREAK"


def format_clock(seconds: float) -> str:
    total = max(0, math.ceil(seconds))
    minutes, secs = divmod(total, 60)
    return f"{minutes:02d}:{secs:02d}"


def _font(families: list[str], px: int, weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    font = QFont()
    font.setFamilies(families)
    font.setPixelSize(max(8, px))
    font.setWeight(weight)
    return font


class ThinProgress(QWidget):
    """A hairline progress indicator, animated smoothly between values."""

    def __init__(self, accent: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._value = 0.0
        self._accent = QColor(accent)
        self.setFixedSize(280, 4)
        self._anim = QPropertyAnimation(self, b"value", self)
        self._anim.setEasingCurve(QEasingCurve.Type.Linear)

    def _get(self) -> float:
        return self._value

    def _set(self, value: float) -> None:
        self._value = max(0.0, min(1.0, value))
        self.update()

    value = Property(float, _get, _set)

    def run(self, start: float, seconds: float) -> None:
        """Animate from `start` to 1.0 over `seconds`."""
        self._anim.stop()
        self._set(start)
        self._anim.setStartValue(start)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(max(1, int(seconds * 1000)))
        self._anim.start()

    def stop(self) -> None:
        self._anim.stop()

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        r = QRectF(self.rect())
        p.setBrush(QColor("#3A4047"))
        p.drawRoundedRect(r, 2, 2)
        p.setBrush(self._accent)
        p.drawRoundedRect(QRectF(0, 0, r.width() * self._value, r.height()), 2, 2)


class BreakContent(QWidget):
    snooze_clicked = Signal()
    skip_clicked = Signal()
    close_clicked = Signal()

    def __init__(self, view: BreakView, options: OverlayOptions, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.view = view
        scale = options.font_scale / 100.0
        self.setMaximumWidth(int(820 * scale))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(0)
        center = Qt.AlignmentFlag.AlignHCenter

        eye = QLabel()
        eye.setPixmap(icons.pixmap("eye", options.accent, int(30 * scale)))
        layout.addWidget(eye, alignment=center)
        layout.addSpacing(int(18 * scale))

        heading = QLabel(view.heading)
        hfont = _font(FONT_FAMILIES, int(12 * scale), QFont.Weight.DemiBold)
        hfont.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.5)
        heading.setFont(hfont)
        heading.setStyleSheet(f"color: {TEXT_SUBTLE};")
        layout.addWidget(heading, alignment=center)

        self.quote = QLabel(f"“{view.quote}”" if view.quote else "")
        self.quote.setWordWrap(True)
        self.quote.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.quote.setFont(_font(DISPLAY_FAMILIES, int(30 * scale), QFont.Weight.Normal))
        self.quote.setStyleSheet(f"color: {TEXT};")
        self.quote.setVisible(bool(view.quote) and options.show_quote)
        layout.addSpacing(int(28 * scale))
        layout.addWidget(self.quote)
        layout.addSpacing(int(30 * scale))

        self.countdown = QLabel(format_clock(view.duration))
        cfont = _font(DISPLAY_FAMILIES, options.countdown_size, QFont.Weight.Light)
        if hasattr(QFont, "Tag"):
            cfont.setFeature(QFont.Tag("tnum"), 1)  # tabular digits: no jitter while counting
        self.countdown.setFont(cfont)
        self.countdown.setStyleSheet(f"color: {TEXT};")
        self.countdown.setAccessibleName("Break time remaining")
        layout.addWidget(self.countdown, alignment=center)
        layout.addSpacing(int(14 * scale))

        self.progress = ThinProgress(options.accent)
        self.progress.setVisible(options.show_progress)
        layout.addWidget(self.progress, alignment=center)
        layout.addSpacing(int(26 * scale))

        self.instruction = QLabel(view.instruction or "")
        self.instruction.setWordWrap(True)
        self.instruction.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.instruction.setFont(_font(FONT_FAMILIES, int(16 * scale)))
        self.instruction.setStyleSheet(f"color: {TEXT_MUTED};")
        self.instruction.setVisible(bool(view.instruction) and options.show_instruction)
        layout.addWidget(self.instruction)
        layout.addSpacing(int(40 * scale))

        self.buttons = QWidget()
        row = QHBoxLayout(self.buttons)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        self.snooze_btn = self._button(self._snooze_label(), "snooze")
        self.skip_btn = self._button("Skip break", "skip")
        self.close_btn = self._button("Close preview", "close")
        self.snooze_btn.clicked.connect(self.snooze_clicked)
        self.skip_btn.clicked.connect(self._on_skip)
        self.close_btn.clicked.connect(self.close_clicked)
        for b in (self.snooze_btn, self.skip_btn, self.close_btn):
            row.addWidget(b)
        layout.addWidget(self.buttons, alignment=center)

        self.confirm = QWidget()
        crow = QHBoxLayout(self.confirm)
        crow.setContentsMargins(0, 0, 0, 0)
        crow.setSpacing(10)
        ask = QLabel("Skip this break?")
        ask.setFont(_font(FONT_FAMILIES, 14))
        ask.setStyleSheet(f"color: {TEXT_MUTED};")
        keep = self._button("Keep resting", None)
        really = self._button("Skip", None)
        keep.clicked.connect(self._cancel_confirm)
        really.clicked.connect(self.skip_clicked)
        crow.addWidget(ask)
        crow.addSpacing(6)
        crow.addWidget(keep)
        crow.addWidget(really)
        self.confirm.hide()
        layout.addWidget(self.confirm, alignment=center)

        self.hint = QLabel("")
        self.hint.setFont(_font(FONT_FAMILIES, 12))
        self.hint.setStyleSheet(f"color: {TEXT_SUBTLE};")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(18)
        layout.addWidget(self.hint, alignment=center)
        self._apply_mode()

    def _snooze_label(self) -> str:
        label = f"Snooze {self.view.snooze_minutes} min"
        if self.view.snoozes_left is not None:
            label += f" ({self.view.snoozes_left} left)"
        return label

    def _button(self, text: str, icon_name: str | None) -> QPushButton:
        btn = QPushButton(text)
        if icon_name:
            btn.setIcon(icons.icon(icon_name, TEXT_MUTED, 16))
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFont(_font(FONT_FAMILIES, 13))
        btn.setStyleSheet(
            "QPushButton { color: #E6E9EC; background: #1E2226; border: 1px solid #3A4047;"
            " border-radius: 6px; padding: 8px 16px; }"
            "QPushButton:hover { background: #2A2F34; border-color: #4A5159; }"
            "QPushButton:focus { border-color: #8E959D; }"
        )
        return btn

    def _apply_mode(self) -> None:
        v = self.view
        self.close_btn.setVisible(v.preview)
        self.snooze_btn.setVisible(not v.preview and v.can_snooze)
        self.skip_btn.setVisible(not v.preview and v.can_skip)
        self.buttons.setVisible(v.preview or v.can_snooze or v.can_skip)
        if v.preview:
            self.hint.setText("Preview — this does not affect your statistics. Press Esc to close.")
        elif v.mode == "strict":
            self.hint.setText("Emergency exit: hold Esc for 3 seconds, or use the tray menu.")
        else:
            self.hint.setText("")
        self.hint.setVisible(bool(self.hint.text()))

    def _on_skip(self) -> None:
        if self.view.skip_needs_confirm:
            self.buttons.hide()
            self.confirm.show()
        else:
            self.skip_clicked.emit()

    def _cancel_confirm(self) -> None:
        self.confirm.hide()
        self.buttons.show()

    def set_remaining(self, remaining: float) -> None:
        self.countdown.setText(format_clock(remaining))

    def start_progress(self, remaining: float) -> None:
        duration = max(self.view.duration, 0.001)
        self.progress.run(1.0 - remaining / duration, remaining)


class DimWindow(QWidget):
    esc_pressed = Signal()
    esc_released = Signal()

    def __init__(self, screen: QScreen, opacity: int) -> None:
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setWindowTitle("Eye Break")
        self.alpha = round(255 * max(50, min(100, opacity)) / 100)
        self.content: BreakContent | None = None
        self.setScreen(screen)
        self.setGeometry(screen.geometry())
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(40, 40, 40, 40)

    def set_content(self, content: BreakContent) -> None:
        self.content = content
        self._layout.addStretch(1)
        self._layout.addWidget(content, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._layout.addStretch(1)

    def paintEvent(self, _event) -> None:  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, self.alpha))

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape and not event.isAutoRepeat():
            self.esc_pressed.emit()
        event.accept()  # swallow keys so they never leak into other handling

    def keyReleaseEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape and not event.isAutoRepeat():
            self.esc_released.emit()
        event.accept()


class OverlayController(QObject):
    snooze_requested = Signal()
    skip_requested = Signal()
    emergency_requested = Signal()
    preview_finished = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.windows: list[DimWindow] = []
        self.view: BreakView | None = None
        self.options = OverlayOptions()
        self._remaining = 0.0
        self._closing: list[DimWindow] = []
        self._hold = QTimer(self)
        self._hold.setSingleShot(True)
        self._hold.setInterval(EMERGENCY_HOLD_MS)
        self._hold.timeout.connect(self._on_hold_complete)
        self._preview_timer = QTimer(self)
        self._preview_timer.setInterval(1000)
        self._preview_timer.timeout.connect(self._preview_tick)
        app = QGuiApplication.instance()
        app.screenAdded.connect(self._on_screens_changed)
        app.screenRemoved.connect(self._on_screens_changed)

    @property
    def active(self) -> bool:
        return self.view is not None

    @property
    def previewing(self) -> bool:
        return self.view is not None and self.view.preview

    def show(self, view: BreakView, options: OverlayOptions) -> None:
        self._discard(self.windows + self._closing)
        self.view, self.options = view, options
        self._remaining = view.duration
        self._build(fade=True)
        if view.preview:
            self._preview_timer.start()

    def set_remaining(self, remaining: float) -> None:
        self._remaining = remaining
        for w in self.windows:
            if w.content:
                w.content.set_remaining(remaining)

    def hide(self, immediate: bool = False) -> None:
        if immediate:
            self.view = None
            self._hold.stop()
            self._preview_timer.stop()
            self._discard(self.windows + self._closing)
            return
        if not self.view:
            return
        self.view = None
        self._hold.stop()
        self._preview_timer.stop()
        closing, self.windows = self.windows, []
        self._closing.extend(closing)
        for w in closing:
            if w.content:
                w.content.progress.stop()
            self._fade(w, 1.0, 0.0, lambda w=w: self._discard([w]))

    def raise_windows(self) -> None:
        """Keep the overlay above windows that may have claimed topmost since it appeared."""
        for w in self.windows:
            w.raise_()

    # ---- internals ---------------------------------------------------------------
    def _content_screens(self) -> list[QScreen]:
        screens = QGuiApplication.screens()
        if self.options.monitor == "primary":
            return [QGuiApplication.primaryScreen()]
        if self.options.monitor == "cursor":
            screen = QGuiApplication.screenAt(QCursor.pos())
            return [screen or QGuiApplication.primaryScreen()]
        return screens

    def _build(self, fade: bool) -> None:
        assert self.view is not None
        content_screens = self._content_screens()
        for screen in QGuiApplication.screens():
            w = DimWindow(screen, self.options.opacity)
            if screen in content_screens:
                content = BreakContent(self.view, self.options)
                content.snooze_clicked.connect(self.snooze_requested)
                content.skip_clicked.connect(self.skip_requested)
                content.close_clicked.connect(self._close_preview)
                content.set_remaining(self._remaining)
                content.start_progress(self._remaining)
                w.set_content(content)
            w.esc_pressed.connect(self._on_esc_pressed)
            w.esc_released.connect(self._hold.stop)
            self.windows.append(w)
            if fade and self.options.fade_ms > 0:
                w.setWindowOpacity(0.0)
            w.show()
            if fade and self.options.fade_ms > 0:
                self._fade(w, 0.0, 1.0)
        primary = next((w for w in self.windows if w.content), None)
        if primary:
            primary.raise_()
            primary.activateWindow()
            primary.setFocus()

    def _fade(self, w: DimWindow, start: float, end: float, done=None) -> None:
        if self.options.fade_ms <= 0:
            w.setWindowOpacity(end)
            if done:
                done()
            return
        anim = QPropertyAnimation(w, b"windowOpacity", w)
        anim.setDuration(self.options.fade_ms)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        if done:
            anim.finished.connect(done)
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def _discard(self, windows: list[DimWindow]) -> None:
        for w in list(windows):
            if w in self._closing:
                self._closing.remove(w)
            if w in self.windows:
                self.windows.remove(w)
            w.hide()
            w.deleteLater()

    def _on_screens_changed(self, *_args) -> None:
        if not self.view:
            return
        log.info("Monitor configuration changed; rebuilding overlay")
        self._discard(self.windows)
        self._build(fade=False)

    def _on_esc_pressed(self) -> None:
        if not self.view:
            return
        if self.view.preview:
            self._close_preview()
        elif self.view.mode == "strict":
            self._hold.start()

    def _on_hold_complete(self) -> None:
        if self.view and not self.view.preview:
            self.emergency_requested.emit()

    def _preview_tick(self) -> None:
        self.set_remaining(self._remaining - 1)
        if self._remaining <= 0:
            self._close_preview()

    def _close_preview(self) -> None:
        if self.previewing:
            self.hide()
            self.preview_finished.emit()
