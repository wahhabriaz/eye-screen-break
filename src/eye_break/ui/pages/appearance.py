from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QSlider, QWidget

from eye_break.services.settings_service import ACCENTS
from eye_break.ui.components import (
    Card,
    Divider,
    Page,
    Segmented,
    SettingRow,
    ToggleSwitch,
    button,
    label,
    section,
)
from eye_break.ui.context import AppContext
from eye_break.ui.overlay import format_clock
from eye_break.ui.themes import ACCENTS as ACCENT_TONES
from eye_break.ui.themes import DISPLAY_FAMILIES, current


class Swatch(QAbstractButton):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name
        self.setCheckable(True)
        self.setFixedSize(28, 28)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName(f"{name.title()} accent")
        self.setToolTip(name.title())

    def paintEvent(self, _e) -> None:  # noqa: N802
        t = current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(ACCENT_TONES[self.name][0 if t.dark else 1])
        if self.isChecked() or self.hasFocus():
            p.setPen(QPen(QColor(t.text if self.isChecked() else t.text_subtle), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QRectF(1, 1, 26, 26))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawEllipse(QRectF(5, 5, 18, 18))


class OverlayPreview(QWidget):
    """A scaled, live rendering of the break overlay on top of a sample desktop."""

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.setMinimumHeight(250)
        self.setAccessibleName("Overlay preview")

    def paintEvent(self, _e) -> None:  # noqa: N802
        s = self.ctx.s
        t = current()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setClipRect(r)
        # sample desktop so the dim strength is visible
        grad = QLinearGradient(r.topLeft(), r.bottomRight())
        grad.setColorAt(0, QColor("#4C7A8C"))
        grad.setColorAt(1, QColor("#C9A27A"))
        p.fillRect(r, grad)
        p.setPen(Qt.PenStyle.NoPen)
        for x, y, w, h in ((0.06, 0.1, 0.5, 0.62), (0.44, 0.3, 0.48, 0.56)):
            win = QRectF(r.left() + r.width() * x, r.top() + r.height() * y, r.width() * w, r.height() * h)
            p.setBrush(QColor("#F4F5F7"))
            p.drawRoundedRect(win, 4, 4)
            p.setBrush(QColor("#D9DDE2"))
            p.drawRoundedRect(QRectF(win.left(), win.top(), win.width(), 12), 4, 4)
            for i in range(4):
                p.setBrush(QColor("#C3C8CF"))
                p.drawRoundedRect(QRectF(win.left() + 12, win.top() + 24 + i * 14, win.width() * (0.7 - i * 0.1), 6), 3, 3)
        p.fillRect(r, QColor(0, 0, 0, round(255 * s.overlay_opacity / 100)))
        # content
        k = (r.height() / 1080) * 2.2 * s.overlay_font_scale / 100
        cx = r.center().x()
        y = r.top() + r.height() * 0.2

        def text(txt: str, px: float, color: str, weight=QFont.Weight.Normal, families=DISPLAY_FAMILIES,
                 spacing: float = 0) -> None:
            nonlocal y
            f = QFont()
            f.setFamilies(families)
            f.setPixelSize(max(6, int(px)))
            f.setWeight(weight)
            if spacing:
                f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
            p.setFont(f)
            p.setPen(QColor(color))
            h = px * 1.6
            p.drawText(QRectF(r.left() + 20, y, r.width() - 40, h), Qt.AlignmentFlag.AlignCenter, txt)
            y += h

        text("TIME FOR AN EYE BREAK", 12 * k, "#8E959D", QFont.Weight.DemiBold, spacing=1.5)
        y += 4 * k
        if s.show_quotes:
            text("“Your work can wait. Your health cannot.”", 30 * k, "#FFFFFF")
        y += 6 * k
        text(format_clock(s.break_seconds), s.countdown_size * k * 0.9, "#FFFFFF", QFont.Weight.Light)
        if s.show_progress:
            w = 280 * k
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#3A4047"))
            p.drawRoundedRect(QRectF(cx - w / 2, y, w, 3), 1.5, 1.5)
            p.setBrush(QColor(t.accent))
            p.drawRoundedRect(QRectF(cx - w / 2, y, w * 0.35, 3), 1.5, 1.5)
            y += 14 * k
        if s.show_instructions:
            text("Look at something about 20 feet (6 metres) away and relax your eyes.", 16 * k, "#C2C8CF")
        p.setClipping(False)
        p.setPen(QPen(QColor(t.border), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, 6, 6)


def slider(value: int, low: int, high: int, step: int, on_change) -> QSlider:
    sl = QSlider(Qt.Orientation.Horizontal)
    sl.setRange(low, high)
    sl.setSingleStep(step)
    sl.setPageStep(step * 5)
    sl.setValue(value)
    sl.setFixedWidth(220)
    sl.valueChanged.connect(on_change)
    return sl


class AppearancePage(Page):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__("Appearance", "Personalise the app and the break overlay.")
        self.ctx = ctx
        s = ctx.s

        theme = Card()
        section(theme, "Theme")
        seg = Segmented([("System", "system"), ("Light", "light"), ("Dark", "dark")], s.theme)
        seg.changed.connect(lambda v: ctx.update(theme=v))
        theme.body.addWidget(SettingRow("Colour scheme", "System follows your Windows light/dark setting.", seg))
        swatches = QWidget()
        row = QHBoxLayout(swatches)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self.swatches: list[Swatch] = []
        for name in ACCENTS:
            sw = Swatch(name)
            sw.setChecked(name == s.accent)
            sw.clicked.connect(lambda _=False, n=name: self._on_accent(n))
            row.addWidget(sw)
            self.swatches.append(sw)
        theme.body.addWidget(SettingRow("Accent colour", "", swatches))
        self.add(theme)

        ov = Card()
        section(ov, "Break overlay", "The preview updates as you adjust the settings.")
        self.preview = OverlayPreview(ctx)
        ov.body.addWidget(self.preview)
        ov.body.addWidget(button("Preview full-screen break", None, "monitor", self._full_preview),
                          0, Qt.AlignmentFlag.AlignLeft)
        ov.body.addWidget(label("Shows a 10-second preview. Press Esc or “Close preview” to dismiss; it is "
                                "not recorded in your statistics.", "hint", wrap=True))
        ov.body.addWidget(Divider())

        self.opacity_value = label(f"{s.overlay_opacity}%", "caption")
        ov.body.addWidget(self._slider_row("Background opacity", "How strongly the screen is dimmed.",
                                           slider(s.overlay_opacity, 50, 100, 5, self._on_opacity),
                                           self.opacity_value))
        self.font_value = label(f"{s.overlay_font_scale}%", "caption")
        ov.body.addWidget(self._slider_row("Text size", "", slider(s.overlay_font_scale, 80, 150, 5, self._on_font),
                                           self.font_value))
        self.count_value = label(f"{s.countdown_size}px", "caption")
        ov.body.addWidget(self._slider_row("Countdown size", "", slider(s.countdown_size, 48, 180, 4, self._on_count),
                                           self.count_value))
        self.fade_value = label(self._fade_text(s.fade_ms), "caption")
        ov.body.addWidget(self._slider_row("Fade animation", "Set to 0 to turn animations off.",
                                           slider(s.fade_ms, 0, 2000, 50, self._on_fade), self.fade_value))
        ov.body.addWidget(Divider())
        for key, title in (("show_quotes", "Show quotation"), ("show_progress", "Show progress indicator"),
                           ("show_instructions", "Show relaxation instruction")):
            tg = ToggleSwitch(getattr(s, key), title)
            tg.toggled.connect(lambda v, k=key: self._set(**{k: v}))
            ov.body.addWidget(SettingRow(title, "", tg))
        mon = Segmented([("All monitors", "all"), ("Primary", "primary"), ("Under cursor", "cursor")],
                        s.overlay_monitor)
        mon.changed.connect(lambda v: self._set(overlay_monitor=v))
        ov.body.addWidget(SettingRow("Show break content on", "Every monitor is always dimmed.", mon))
        self.add(ov)
        self.finish()

    def _slider_row(self, title: str, desc: str, sl: QSlider, value_label) -> SettingRow:
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(sl)
        value_label.setFixedWidth(52)
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(value_label)
        return SettingRow(title, desc, holder)

    @staticmethod
    def _fade_text(ms: int) -> str:
        return "Off" if ms == 0 else f"{ms / 1000:.2f}s"

    def _set(self, **changes) -> None:
        self.ctx.update(**changes)
        self.preview.update()

    def _on_opacity(self, v: int) -> None:
        self.opacity_value.setText(f"{v}%")
        self._set(overlay_opacity=v)

    def _on_font(self, v: int) -> None:
        self.font_value.setText(f"{v}%")
        self._set(overlay_font_scale=v)

    def _on_count(self, v: int) -> None:
        self.count_value.setText(f"{v}px")
        self._set(countdown_size=v)

    def _on_fade(self, v: int) -> None:
        v = round(v / 50) * 50
        self.fade_value.setText(self._fade_text(v))
        self._set(fade_ms=v)

    def _on_accent(self, name: str) -> None:
        for sw in self.swatches:
            sw.setChecked(sw.name == name)
        self._set(accent=name)

    def _full_preview(self) -> None:
        self.ctx.flush()
        self.ctx.manager.preview()

    def on_theme(self) -> None:
        self.preview.update()
        for sw in self.swatches:
            sw.update()
