from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

from eye_break import APP_NAME, __version__
from eye_break.ui import icons
from eye_break.ui.components import Card, Page, label, section
from eye_break.ui.context import AppContext
from eye_break.utils.paths import data_dir


class AboutPage(Page):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__("About")
        hero = Card()
        row = QHBoxLayout()
        row.setSpacing(18)
        logo = QLabel()
        px = icons.logo_pixmap(128)
        px.setDevicePixelRatio(2.0)
        logo.setPixmap(px)
        row.addWidget(logo, 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(4)
        text.addWidget(label(APP_NAME, "pageTitle"))
        text.addWidget(label(f"Version {__version__}", "caption"))
        text.addWidget(label("A calm, offline assistant that reminds you to rest your eyes and take regular "
                             "breaks from the screen.", "pageSubtitle", wrap=True))
        row.addLayout(text, 1)
        hero.body.addLayout(row)
        self.add(hero)

        guide = Card()
        section(guide, "How it works")
        for line in (
            "Eye Break counts active computer time. When the interval is reached, the screen dims and a short "
            "break begins; when the countdown ends, the overlay disappears on its own.",
            "Idle time, locked screens and sleep are never counted as work.",
            "Use the tray icon for quick actions: take a break, snooze, pause or start meeting mode.",
        ):
            guide.body.addWidget(label(f"•  {line}", "caption", wrap=True))
        self.add(guide)

        safety = Card()
        section(safety, "Emergency exit (strict mode)")
        safety.body.addWidget(label(
            "Strict mode hides skip and snooze, but you can always end a break: hold Esc for 3 seconds while the "
            "overlay has focus (click it first if needed), or choose “End break now” in the tray menu. "
            "Eye Break never blocks Ctrl+Alt+Del, Task Manager, accessibility tools or other system functions.",
            "caption", wrap=True))
        self.add(safety)

        health = Card()
        section(health, "A note on health")
        health.body.addWidget(label(
            "Eye Break encourages healthy screen habits. It is not a medical device and does not diagnose, treat or "
            "prevent any condition. If you have persistent eye discomfort, please talk to an eye-care professional.",
            "caption", wrap=True))
        self.add(health)

        priv = Card()
        section(priv, "Privacy and licences")
        priv.body.addWidget(label(
            "No accounts, telemetry, analytics or network requests. Data is stored only in "
            f"{data_dir()}.", "caption", wrap=True))
        priv.body.addWidget(label(
            "Eye Break is released under the MIT licence. Built with Qt for Python (PySide6), used under the "
            "GNU LGPL v3. Icons, sounds and quotations are original to this project.", "caption", wrap=True))
        self.add(priv)
        self.finish()
