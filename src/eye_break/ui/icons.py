"""Original line icons (24px grid, 1.75 stroke) rendered from inline SVG, plus the app logo."""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer

_PATHS: dict[str, str] = {
    "eye": '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "overview": '<rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/>'
                '<rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/>',
    "schedule": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "appearance": '<circle cx="12" cy="12" r="9"/><path d="M12 3a9 9 0 0 0 0 18z" fill="currentColor"/>',
    "statistics": '<path d="M4 20V10"/><path d="M10 20V4"/><path d="M16 20v-7"/><path d="M22 20H2"/>',
    "quotes": '<path d="M7 7h4v4c0 3-1.5 5-4 6"/><path d="M15 7h4v4c0 3-1.5 5-4 6"/>',
    "settings": '<path d="M4 6h10"/><path d="M18 6h2"/><circle cx="16" cy="6" r="2"/><path d="M4 12h4"/>'
                '<path d="M12 12h8"/><circle cx="10" cy="12" r="2"/><path d="M4 18h12"/><path d="M20 18h0"/>'
                '<circle cx="18" cy="18" r="2"/>',
    "about": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6"/><path d="M12 7.5v.01"/>',
    "play": '<path d="M7 5l12 7-12 7z"/>',
    "pause": '<path d="M8 5v14"/><path d="M16 5v14"/>',
    "coffee": '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><path d="M4 4l16 16"/>',
    "restart": '<path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/>',
    "snooze": '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
    "skip": '<path d="M5 5l10 7-10 7z"/><path d="M19 5v14"/>',
    "plus": '<path d="M12 5v14"/><path d="M5 12h14"/>',
    "trash": '<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7l1 13h10l1-13"/>',
    "download": '<path d="M12 4v11"/><path d="M7 10l5 5 5-5"/><path d="M5 20h14"/>',
    "meeting": '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="M16 10l5-3v10l-5-3"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "close": '<path d="M6 6l12 12"/><path d="M18 6L6 18"/>',
    "shield": '<path d="M12 3l8 3v6c0 4.5-3.4 8-8 9-4.6-1-8-4.5-8-9V6z"/>',
    "monitor": '<rect x="3" y="4" width="18" height="12" rx="1.5"/><path d="M8 20h8"/><path d="M12 16v4"/>',
    "bell": '<path d="M6 16V11a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 21h4"/>',
    "power": '<path d="M12 3v9"/><path d="M6.3 6.3a8 8 0 1 0 11.4 0"/>',
}


@lru_cache(maxsize=256)
def pixmap(name: str, color: str, size: int = 18, ratio: float = 2.0) -> QPixmap:
    body = _PATHS[name].replace("currentColor", color)
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
        f'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
    )
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    px = QPixmap(int(size * ratio), int(size * ratio))
    px.fill(Qt.GlobalColor.transparent)
    painter = QPainter(px)
    renderer.render(painter)
    painter.end()
    px.setDevicePixelRatio(ratio)
    return px


def icon(name: str, color: str, size: int = 18) -> QIcon:
    return QIcon(pixmap(name, color, size))


def logo_pixmap(size: int, background: str = "#0F766E", paused: bool = False) -> QPixmap:
    """The Eye Break mark: a calm eye inside a rounded square."""
    px = QPixmap(size, size)
    px.fill(Qt.GlobalColor.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    bg = QColor("#5B6470" if paused else background)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(bg)
    radius = size * 0.24
    p.drawRoundedRect(QRectF(0, 0, size, size), radius, radius)
    s = size / 24.0
    pen = QPen(QColor("#FFFFFF"), max(1.2, 1.9 * s))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath(QPointF(4 * s, 12 * s))
    path.quadTo(QPointF(12 * s, 3.5 * s), QPointF(20 * s, 12 * s))
    path.quadTo(QPointF(12 * s, 20.5 * s), QPointF(4 * s, 12 * s))
    p.drawPath(path)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#FFFFFF"))
    r = 2.6 * s
    p.drawEllipse(QPointF(12 * s, 12 * s), r, r)
    p.end()
    return px


def app_icon(paused: bool = False) -> QIcon:
    result = QIcon()
    for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        result.addPixmap(logo_pixmap(size, paused=paused))
    return result
