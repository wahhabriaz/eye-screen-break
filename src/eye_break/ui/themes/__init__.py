"""Design tokens, theme resolution and the generated application stylesheet."""

from __future__ import annotations

from dataclasses import dataclass, replace

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QFont, QGuiApplication

FONT_FAMILIES = ["Segoe UI Variable Text", "Segoe UI", "Inter", "Arial"]
DISPLAY_FAMILIES = ["Segoe UI Variable Display", "Segoe UI", "Inter", "Arial"]

# accent: (dark-mode tone, light-mode tone)
ACCENTS: dict[str, tuple[str, str]] = {
    "teal": ("#3CC2AE", "#0E8577"),
    "green": ("#62C483", "#227A45"),
    "blue": ("#6EA8F2", "#2563C9"),
    "violet": ("#A592F2", "#6A4FD6"),
    "amber": ("#E6B661", "#A3660A"),
    "rose": ("#EF8DA3", "#C23B5E"),
}

# spacing scale (px)
SPACE = {"xs": 4, "sm": 8, "md": 12, "lg": 16, "xl": 24, "xxl": 32}
RADIUS = 8
RADIUS_SM = 6


@dataclass(frozen=True)
class Tokens:
    dark: bool
    bg: str
    sidebar: str
    surface: str
    surface_alt: str
    hover: str
    border: str
    border_strong: str
    text: str
    text_muted: str
    text_subtle: str
    accent: str
    accent_text: str
    accent_soft: str
    danger: str
    warning: str
    success: str


DARK = Tokens(
    dark=True, bg="#0F1214", sidebar="#0B0D0F", surface="#161A1D", surface_alt="#1C2125",
    hover="#22282D", border="#252B30", border_strong="#343B42", text="#E8EBEE",
    text_muted="#A0A8B1", text_subtle="#6F7882", accent="#3CC2AE", accent_text="#06130F",
    accent_soft="#173430", danger="#F0787A", warning="#E6B661", success="#62C483",
)
LIGHT = Tokens(
    dark=False, bg="#F7F8F9", sidebar="#EFF1F3", surface="#FFFFFF", surface_alt="#F3F5F7",
    hover="#E9ECEF", border="#E2E5E9", border_strong="#CDD2D8", text="#14181B",
    text_muted="#58616B", text_subtle="#89919A", accent="#0E8577", accent_text="#FFFFFF",
    accent_soft="#E1F2EF", danger="#C93B3E", warning="#A3660A", success="#227A45",
)

_current: Tokens = DARK


def current() -> Tokens:
    return _current


def _mix(a: str, b: str, t: float) -> str:
    ca = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02X}" for x, y in zip(ca, cb))


def resolve(theme: str, accent: str) -> Tokens:
    if theme == "system":
        scheme = QGuiApplication.styleHints().colorScheme()
        dark = scheme != Qt.ColorScheme.Light
    else:
        dark = theme == "dark"
    base = DARK if dark else LIGHT
    tone = ACCENTS.get(accent, ACCENTS["teal"])[0 if dark else 1]
    return replace(base, accent=tone, accent_soft=_mix(base.surface, tone, 0.16 if dark else 0.12))


class ThemeManager(QObject):
    changed = Signal(object)

    def __init__(self, theme: str, accent: str) -> None:
        super().__init__()
        self.theme, self.accent = theme, accent
        QGuiApplication.styleHints().colorSchemeChanged.connect(self._on_system_change)

    def apply(self, theme: str | None = None, accent: str | None = None) -> Tokens:
        global _current
        self.theme = theme or self.theme
        self.accent = accent or self.accent
        _current = resolve(self.theme, self.accent)
        app = QGuiApplication.instance()
        if app is not None and hasattr(app, "setStyleSheet"):
            font = QFont()
            font.setFamilies(FONT_FAMILIES)
            font.setPixelSize(13)
            app.setFont(font)
            app.setStyleSheet(stylesheet(_current))
        self.changed.emit(_current)
        return _current

    def _on_system_change(self, *_args) -> None:
        if self.theme == "system":
            self.apply()


def stylesheet(t: Tokens) -> str:
    # Base font comes from QApplication.setFont (see ThemeManager.apply) rather than a `*` rule, so
    # widgets that set explicit fonts (the overlay) are not overridden by the stylesheet.
    return f"""
* {{ color: {t.text}; outline: 0; }}
QMainWindow, QWidget#Root {{ background: {t.bg}; }}
QWidget#Page, QScrollArea, QScrollArea > QWidget > QWidget {{ background: {t.bg}; border: none; }}
QFrame#Sidebar {{ background: {t.sidebar}; border-right: 1px solid {t.border}; }}
QLabel {{ background: transparent; }}
QLabel[role="brand"] {{ font-size: 14px; font-weight: 600; }}
QLabel[role="pageTitle"] {{ font-size: 20px; font-weight: 600; }}
QLabel[role="pageSubtitle"] {{ color: {t.text_muted}; font-size: 13px; }}
QLabel[role="section"] {{ font-size: 14px; font-weight: 600; }}
QLabel[role="caption"] {{ color: {t.text_muted}; font-size: 12px; }}
QLabel[role="overline"] {{ color: {t.text_subtle}; font-size: 11px; font-weight: 600; letter-spacing: 1px; }}
QLabel[role="metric"] {{ font-size: 22px; font-weight: 600; }}
QLabel[role="hint"] {{ color: {t.text_subtle}; font-size: 12px; }}
QLabel[role="error"] {{ color: {t.danger}; font-size: 12px; }}
QLabel[role="pill"] {{ background: {t.accent_soft}; color: {t.accent}; border-radius: 10px;
    padding: 2px 10px; font-size: 12px; font-weight: 600; }}
QLabel[role="pill"][tone="muted"] {{ background: {t.surface_alt}; color: {t.text_muted}; }}
QLabel[role="pill"][tone="warning"] {{ background: {_mix(t.surface, t.warning, 0.16)}; color: {t.warning}; }}

QFrame#Card {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: {RADIUS}px; }}
QFrame#Divider {{ background: {t.border}; max-height: 1px; min-height: 1px; border: none; }}

QPushButton#NavButton {{ text-align: left; padding: 7px 10px; border: none; border-radius: {RADIUS_SM}px;
    color: {t.text_muted}; background: transparent; font-size: 13px; }}
QPushButton#NavButton:hover {{ background: {t.hover}; color: {t.text}; }}
QPushButton#NavButton:checked {{ background: {t.surface_alt}; color: {t.text}; font-weight: 600; }}

QPushButton {{ background: {t.surface}; border: 1px solid {t.border_strong}; border-radius: {RADIUS_SM}px;
    padding: 6px 14px; min-height: 20px; }}
QPushButton:hover {{ background: {t.hover}; }}
QPushButton:pressed {{ background: {t.surface_alt}; }}
QPushButton:disabled {{ color: {t.text_subtle}; border-color: {t.border}; }}
QPushButton[variant="primary"] {{ background: {t.accent}; color: {t.accent_text}; border: 1px solid {t.accent};
    font-weight: 600; }}
QPushButton[variant="primary"]:hover {{ background: {_mix(t.accent, '#FFFFFF' if t.dark else '#000000', 0.1)}; }}
QPushButton[variant="ghost"] {{ background: transparent; border: 1px solid transparent; color: {t.text_muted}; }}
QPushButton[variant="ghost"]:hover {{ background: {t.hover}; color: {t.text}; }}
QPushButton[variant="danger"] {{ color: {t.danger}; }}
QPushButton[variant="segment"] {{ background: transparent; border: none; border-radius: 5px; padding: 5px 12px;
    color: {t.text_muted}; }}
QPushButton[variant="segment"]:hover {{ color: {t.text}; }}
QPushButton[variant="segment"]:checked {{ background: {t.surface}; color: {t.text};
    border: 1px solid {t.border_strong}; }}
QFrame#Segmented {{ background: {t.surface_alt}; border: 1px solid {t.border}; border-radius: {RADIUS_SM + 1}px; }}

QLineEdit, QSpinBox, QComboBox, QPlainTextEdit {{ background: {t.surface_alt}; border: 1px solid {t.border};
    border-radius: {RADIUS_SM}px; padding: 5px 8px; selection-background-color: {t.accent};
    selection-color: {t.accent_text}; min-height: 20px; }}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{ border-color: {t.accent}; }}
QLineEdit[invalid="true"], QSpinBox[invalid="true"] {{ border-color: {t.danger}; }}
QSpinBox::up-button, QSpinBox::down-button {{ width: 0; border: none; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: none; width: 0; height: 0; border-left: 4px solid transparent;
    border-right: 4px solid transparent; border-top: 5px solid {t.text_muted}; margin-right: 8px; }}
QComboBox QAbstractItemView {{ background: {t.surface}; border: 1px solid {t.border_strong}; padding: 4px;
    selection-background-color: {t.hover}; selection-color: {t.text}; outline: 0; }}

QSlider::groove:horizontal {{ height: 4px; background: {t.border_strong}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {t.accent}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {'#FFFFFF' if t.dark else t.surface}; border: 1px solid {t.border_strong};
    width: 16px; height: 16px; margin: -7px 0; border-radius: 8px; }}

QListWidget {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: {RADIUS}px; padding: 4px; }}
QListWidget::item {{ padding: 8px 10px; border-radius: {RADIUS_SM}px; }}
QListWidget::item:selected {{ background: {t.hover}; color: {t.text}; }}
QListWidget::item:hover {{ background: {t.surface_alt}; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t.border_strong}; border-radius: 3px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; background: none; }}
QScrollBar:horizontal {{ height: 0; }}

QToolTip {{ background: {t.surface_alt}; color: {t.text}; border: 1px solid {t.border_strong}; padding: 4px 8px; }}
QMenu {{ background: {t.surface}; border: 1px solid {t.border_strong}; border-radius: {RADIUS}px; padding: 5px; }}
QMenu::item {{ padding: 6px 28px 6px 12px; border-radius: 5px; }}
QMenu::item:selected {{ background: {t.hover}; }}
QMenu::item:disabled {{ color: {t.text_subtle}; }}
QMenu::separator {{ height: 1px; background: {t.border}; margin: 4px 6px; }}
QMenu::indicator {{ width: 0; }}
QMessageBox, QDialog {{ background: {t.surface}; }}
QCheckBox, QRadioButton {{ spacing: 8px; }}
QRadioButton::indicator {{ width: 14px; height: 14px; border-radius: 8px; border: 1px solid {t.border_strong};
    background: {t.surface_alt}; }}
QRadioButton::indicator:hover {{ border-color: {t.accent}; }}
QRadioButton::indicator:checked {{ border: 5px solid {t.accent}; width: 6px; height: 6px;
    background: {'#FFFFFF' if t.dark else t.surface}; }}
"""
