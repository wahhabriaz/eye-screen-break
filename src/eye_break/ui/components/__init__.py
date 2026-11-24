"""Reusable, theme-aware building blocks for every page."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPointF,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from eye_break.ui import icons
from eye_break.ui.themes import DISPLAY_FAMILIES, SPACE, current


def label(text: str, role: str | None = None, wrap: bool = False) -> QLabel:
    lbl = QLabel(text)
    if role:
        lbl.setProperty("role", role)
    lbl.setWordWrap(wrap)
    return lbl


def repolish(widget: QWidget) -> None:
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def button(text: str, variant: str | None = None, icon_name: str | None = None,
           on_click: Callable[[], None] | None = None) -> QPushButton:
    btn = QPushButton(text)
    if variant:
        btn.setProperty("variant", variant)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if icon_name:
        btn.setProperty("iconName", icon_name)
        refresh_icon(btn)
    if on_click:
        btn.clicked.connect(lambda _=False: on_click())
    return btn


def refresh_icon(btn: QPushButton) -> None:
    name = btn.property("iconName")
    if not name:
        return
    t = current()
    color = t.accent_text if btn.property("variant") == "primary" else t.text_muted
    btn.setIcon(icons.icon(name, color, 16))
    btn.setIconSize(QSize(16, 16))


class Card(QFrame):
    def __init__(self, parent: QWidget | None = None, padding: int = SPACE["xl"]) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(padding, padding - 4, padding, padding - 4)
        self.body.setSpacing(SPACE["md"])


class Divider(QFrame):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Divider")


class Page(QScrollArea):
    """Scrollable page with a title, subtitle and vertical content column."""

    def __init__(self, title: str, subtitle: str = "") -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        inner = QWidget()
        inner.setObjectName("Page")
        self.setWidget(inner)
        self.column = QVBoxLayout(inner)
        self.column.setContentsMargins(SPACE["xxl"], 28, SPACE["xxl"], SPACE["xxl"])
        self.column.setSpacing(SPACE["lg"])
        header = QVBoxLayout()
        header.setSpacing(2)
        header.addWidget(label(title, "pageTitle"))
        if subtitle:
            header.addWidget(label(subtitle, "pageSubtitle", wrap=True))
        self.column.addLayout(header)
        self.column.addSpacing(SPACE["sm"])

    def add(self, widget: QWidget) -> QWidget:
        self.column.addWidget(widget)
        return widget

    def finish(self) -> None:
        self.column.addStretch(1)

    def on_theme(self) -> None:
        """Pages override to refresh painted elements after a theme change."""


class SettingRow(QWidget):
    """Label + optional description on the left, a control on the right."""

    def __init__(self, title: str, description: str = "", control: QWidget | None = None) -> None:
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 4, 0, 4)
        row.setSpacing(SPACE["lg"])
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(label(title))
        self.description = label(description, "caption", wrap=True)
        self.description.setVisible(bool(description))
        text.addWidget(self.description)
        row.addLayout(text, 1)
        if control is not None:
            row.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
        self.control = control


def section(card: Card, title: str, caption: str = "") -> None:
    card.body.addWidget(label(title, "section"))
    if caption:
        card.body.addWidget(label(caption, "caption", wrap=True))


class ToggleSwitch(QAbstractButton):
    """An animated on/off switch (accessible: checkable, keyboard-operable)."""

    def __init__(self, checked: bool = False, accessible_name: str = "") -> None:
        super().__init__()
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFixedSize(38, 22)
        if accessible_name:
            self.setAccessibleName(accessible_name)
        self._pos = 1.0 if checked else 0.0
        self._anim = QPropertyAnimation(self, b"knob", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)

    def _get(self) -> float:
        return self._pos

    def _set(self, v: float) -> None:
        self._pos = v
        self.update()

    knob = Property(float, _get, _set)

    def setChecked(self, checked: bool) -> None:  # noqa: N802
        super().setChecked(checked)
        self._pos = 1.0 if checked else 0.0
        self.update()

    def _animate(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(38, 22)

    def paintEvent(self, _e) -> None:  # noqa: N802
        t = current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        off, on = QColor(t.border_strong), QColor(t.accent)
        track = QColor(
            round(off.red() + (on.red() - off.red()) * self._pos),
            round(off.green() + (on.green() - off.green()) * self._pos),
            round(off.blue() + (on.blue() - off.blue()) * self._pos),
        )
        if not self.isEnabled():
            track.setAlpha(110)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 6
        x = r.left() + 3 + (r.width() - d - 6) * self._pos
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QRectF(x, r.top() + 3, d, d))
        if self.hasFocus():
            p.setPen(QPen(QColor(t.accent), 1.5))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 11, 11)


class Segmented(QFrame):
    """Compact segmented control. Emits the selected option's value."""

    changed = Signal(object)

    def __init__(self, options: Sequence[tuple[str, object]], value: object = None) -> None:
        super().__init__()
        self.setObjectName("Segmented")
        row = QHBoxLayout(self)
        row.setContentsMargins(3, 3, 3, 3)
        row.setSpacing(2)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.values: list[object] = []
        for index, (text, val) in enumerate(options):
            b = QPushButton(text)
            b.setProperty("variant", "segment")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.group.addButton(b, index)
            row.addWidget(b)
            self.values.append(val)
        self.group.idClicked.connect(lambda i: self.changed.emit(self.values[i]))
        self.set_value(value)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)

    def set_value(self, value: object) -> None:
        for index, val in enumerate(self.values):
            self.group.button(index).setChecked(val == value)
        if value not in self.values:
            checked = self.group.checkedButton()
            if checked:
                self.group.setExclusive(False)
                checked.setChecked(False)
                self.group.setExclusive(True)

    def value(self) -> object:
        checked = self.group.checkedId()
        return self.values[checked] if checked >= 0 else None


class ProgressRing(QWidget):
    """Circular progress with centred primary text and a caption."""

    def __init__(self, diameter: int = 220) -> None:
        super().__init__()
        self.setFixedSize(diameter, diameter)
        self.progress = 0.0
        self.text = "00:00"
        self.caption = ""
        self.muted = False
        self.setAccessibleName("Time until next break")

    def set(self, progress: float, text: str, caption: str, muted: bool = False) -> None:
        changed = (round(progress, 3), text, caption, muted) != (round(self.progress, 3), self.text,
                                                                  self.caption, self.muted)
        self.progress, self.text, self.caption, self.muted = progress, text, caption, muted
        if changed:
            self.setAccessibleDescription(f"{text} {caption}")
            self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        t = current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        width = 8.0
        r = QRectF(width, width, self.width() - 2 * width, self.height() - 2 * width)
        pen = QPen(QColor(t.surface_alt if t.dark else t.hover), width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawEllipse(r)
        if self.progress > 0:
            pen.setColor(QColor(t.text_subtle if self.muted else t.accent))
            p.setPen(pen)
            p.drawArc(r, 90 * 16, int(-360 * 16 * min(1.0, self.progress)))
        font = QFont()
        font.setFamilies(DISPLAY_FAMILIES)
        font.setPixelSize(int(self.height() * 0.2))
        font.setWeight(QFont.Weight.Light)
        if hasattr(QFont, "Tag"):
            font.setFeature(QFont.Tag("tnum"), 1)
        p.setFont(font)
        p.setPen(QColor(t.text_muted if self.muted else t.text))
        text_rect = QRectF(0, self.height() * 0.30, self.width(), self.height() * 0.30)
        p.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self.text)
        cap = QFont()
        cap.setPixelSize(12)
        p.setFont(cap)
        p.setPen(QColor(t.text_muted))
        p.drawText(QRectF(0, self.height() * 0.60, self.width(), 20), Qt.AlignmentFlag.AlignCenter, self.caption)


class StatTile(QFrame):
    def __init__(self, title: str, value: str = "—", caption: str = "") -> None:
        super().__init__()
        self.setObjectName("Card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(SPACE["lg"], SPACE["md"] + 2, SPACE["lg"], SPACE["md"] + 2)
        lay.setSpacing(4)
        lay.addWidget(label(title.upper(), "overline"))
        self.value = label(value, "metric")
        lay.addWidget(self.value)
        self.caption = label(caption, "caption")
        self.caption.setVisible(bool(caption))
        lay.addWidget(self.caption)
        lay.addStretch(1)
        self.setAccessibleName(title)

    def set(self, value: str, caption: str | None = None) -> None:
        self.value.setText(value)
        self.setAccessibleDescription(value)
        if caption is not None:
            self.caption.setText(caption)
            self.caption.setVisible(bool(caption))


def tile_grid(tiles: Sequence[QWidget], columns: int) -> QWidget:
    holder = QWidget()
    grid = QGridLayout(holder)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setSpacing(SPACE["md"])
    for index, tile in enumerate(tiles):
        grid.addWidget(tile, index // columns, index % columns)
    for col in range(columns):
        grid.setColumnStretch(col, 1)
    return holder


class BarChart(QWidget):
    """Minimal bar chart; supports stacked series. Values: list of per-day tuples."""

    def __init__(self, series_names: Sequence[str], formatter: Callable[[float], str] = lambda v: f"{v:.0f}") -> None:
        super().__init__()
        self.series_names = list(series_names)
        self.formatter = formatter
        self.labels: list[str] = []
        self.values: list[tuple[float, ...]] = []
        self.colors: list[str] = []
        self.setMinimumHeight(170)
        self.setMouseTracking(True)
        self._hover = -1

    def set_data(self, labels: list[str], values: list[tuple[float, ...]], colors: list[str]) -> None:
        self.labels, self.values, self.colors = labels, values, colors
        self.setAccessibleDescription(
            ", ".join(f"{lbl}: {' / '.join(self.formatter(v) for v in vals)}" for lbl, vals in zip(labels, values))
        )
        self.update()

    def _geometry(self) -> tuple[QRectF, float]:
        area = QRectF(44, 10, self.width() - 52, self.height() - 34)
        n = max(1, len(self.values))
        return area, area.width() / n

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        area, slot = self._geometry()
        index = int((e.position().x() - area.left()) // slot) if slot else -1
        index = index if 0 <= index < len(self.values) else -1
        if index != self._hover:
            self._hover = index
            if index >= 0:
                parts = [f"{n}: {self.formatter(v)}" for n, v in zip(self.series_names, self.values[index])]
                self.setToolTip(f"{self.labels[index]}\n" + "\n".join(parts))
            else:
                self.setToolTip("")
            self.update()

    def leaveEvent(self, _e) -> None:  # noqa: N802
        self._hover = -1
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        t = current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        area, slot = self._geometry()
        totals = [sum(v) for v in self.values] or [0]
        peak = max(totals) or 1.0
        small = QFont()
        small.setPixelSize(11)
        p.setFont(small)
        # gridlines
        for frac in (0.0, 0.5, 1.0):
            y = area.bottom() - area.height() * frac
            p.setPen(QPen(QColor(t.border), 1))
            p.drawLine(QPointF(area.left(), y), QPointF(area.right(), y))
            p.setPen(QColor(t.text_subtle))
            p.drawText(QRectF(0, y - 8, 38, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       self.formatter(peak * frac) if frac else "0")
        if not self.values:
            return
        bar_w = max(2.0, min(28.0, slot * 0.6))
        step = max(1, len(self.labels) // 8)
        for i, vals in enumerate(self.values):
            x = area.left() + slot * i + (slot - bar_w) / 2
            y = area.bottom()
            if i == self._hover:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(t.hover))
                p.drawRoundedRect(QRectF(area.left() + slot * i + 1, area.top(), slot - 2, area.height()), 4, 4)
            for value, color in zip(vals, self.colors):
                h = area.height() * value / peak
                if h <= 0:
                    continue
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(color))
                p.drawRoundedRect(QRectF(x, y - h, bar_w, h), 2.5, 2.5)
                y -= h
            if i % step == 0 or i == len(self.labels) - 1:
                p.setPen(QColor(t.text_subtle))
                p.drawText(QRectF(area.left() + slot * i - 20, area.bottom() + 6, slot + 40, 16),
                           Qt.AlignmentFlag.AlignHCenter, self.labels[i])


def legend(items: Sequence[tuple[str, str]]) -> QWidget:
    holder = QWidget()
    row = QHBoxLayout(holder)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(SPACE["lg"])
    for text, color in items:
        dot = QLabel()
        dot.setFixedSize(8, 8)
        dot.setStyleSheet(f"background: {color}; border-radius: 4px;")
        row.addWidget(dot)
        row.addSpacing(-SPACE["sm"])
        row.addWidget(label(text, "caption"))
    row.addStretch(1)
    return holder


def format_duration(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    if minutes:
        return f"{minutes}m {secs:02d}s" if minutes < 10 and secs else f"{minutes}m"
    return f"{secs}s"


def format_rate(rate: float | None) -> str:
    return "—" if rate is None else f"{rate * 100:.0f}%"
