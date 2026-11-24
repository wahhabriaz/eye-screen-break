from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from eye_break import APP_NAME
from eye_break.core.scheduler import State
from eye_break.ui import icons
from eye_break.ui.components import Page, label, refresh_icon
from eye_break.ui.context import AppContext
from eye_break.ui.overlay import format_clock
from eye_break.ui.pages.about import AboutPage
from eye_break.ui.pages.appearance import AppearancePage
from eye_break.ui.pages.overview import OverviewPage
from eye_break.ui.pages.quotes import QuotesPage
from eye_break.ui.pages.schedule import SchedulePage
from eye_break.ui.pages.settings import SettingsPage
from eye_break.ui.pages.statistics import StatisticsPage
from eye_break.ui.themes import current

NAV = [
    ("overview", "Overview", "overview", OverviewPage),
    ("schedule", "Break schedule", "schedule", SchedulePage),
    ("appearance", "Appearance", "appearance", AppearancePage),
    ("statistics", "Statistics", "statistics", StatisticsPage),
    ("quotes", "Quotations", "quotes", QuotesPage),
    ("settings", "Settings", "settings", SettingsPage),
    ("about", "About", "about", AboutPage),
]


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(icons.app_icon())
        self.setMinimumSize(QSize(940, 640))
        self.resize(1080, 760)
        self.tray_hint_shown = False
        self.on_hide_to_tray = None  # set by the app to show a one-time notice

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(212)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(12, 18, 12, 14)
        side.setSpacing(2)
        brand = QHBoxLayout()
        brand.setContentsMargins(8, 0, 0, 0)
        brand.setSpacing(10)
        logo = QLabel()
        px = icons.logo_pixmap(48)
        px.setDevicePixelRatio(2.0)
        logo.setPixmap(px)
        brand.addWidget(logo)
        brand.addWidget(label(APP_NAME, "brand"))
        brand.addStretch(1)
        side.addLayout(brand)
        side.addSpacing(20)

        self.nav_group = QButtonGroup(self)
        self.nav_buttons: dict[str, QPushButton] = {}
        for index, (key, title, icon_name, _cls) in enumerate(NAV):
            b = QPushButton(title)
            b.setObjectName("NavButton")
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setProperty("iconName", icon_name)
            b.setIconSize(QSize(16, 16))
            b.setToolTip(f"{title} (Ctrl+{index + 1})")
            self.nav_group.addButton(b, index)
            self.nav_buttons[key] = b
            side.addWidget(b)
            QShortcut(QKeySequence(f"Ctrl+{index + 1}"), self, activated=lambda k=key: self.show_page(k))
        side.addStretch(1)
        self.footer_state = label("", "caption")
        self.footer_time = label("", "section")
        foot = QVBoxLayout()
        foot.setContentsMargins(10, 0, 0, 0)
        foot.setSpacing(0)
        foot.addWidget(self.footer_state)
        foot.addWidget(self.footer_time)
        side.addLayout(foot)
        outer.addWidget(sidebar)

        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)
        self.pages: dict[str, Page] = {}
        self._build_pages()
        self.nav_group.idClicked.connect(lambda i: self.show_page(NAV[i][0]))
        ctx.navigate.connect(self._on_navigate)
        ctx.theme.changed.connect(self._on_theme)
        ctx.manager.ticked.connect(self._refresh_footer)
        self._on_theme()
        self.show_page("overview")

    def _build_pages(self) -> None:
        current_key = getattr(self, "_current", "overview")
        for page in self.pages.values():
            self.stack.removeWidget(page)
            page.deleteLater()
        self.pages = {key: cls(self.ctx) for key, _t, _i, cls in NAV}
        for key, *_ in NAV:
            self.stack.addWidget(self.pages[key])
        self._current = current_key

    def show_page(self, key: str) -> None:
        self._current = key
        self.nav_buttons[key].setChecked(True)
        self.stack.setCurrentWidget(self.pages[key])

    def _on_navigate(self, key: str) -> None:
        if key == "__rebuild__":
            self._build_pages()
            self.show_page(self._current)
        else:
            self.show_page(key)

    def _on_theme(self, *_args) -> None:
        t = current()
        for b in self.nav_buttons.values():
            b.setIcon(icons.icon(b.property("iconName"), t.text_muted, 16))
        for page in self.pages.values():
            for btn in page.findChildren(QPushButton):
                refresh_icon(btn)
            page.on_theme()
            page.update()

    def _refresh_footer(self) -> None:
        if not self.isVisible():
            return
        sch = self.ctx.manager.scheduler
        state = sch.state
        if state == State.ON_BREAK:
            self.footer_state.setText("On a break")
            self.footer_time.setText(format_clock(sch.break_remaining))
        elif state in (State.PAUSED, State.MEETING):
            self.footer_state.setText("Meeting mode" if state == State.MEETING else "Paused")
            self.footer_time.setText("—")
        elif state in (State.IDLE, State.SUSPENDED):
            self.footer_state.setText("Timer paused (away)")
            self.footer_time.setText(format_clock(sch.remaining))
        else:
            self.footer_state.setText("Next break in")
            self.footer_time.setText(format_clock(sch.remaining))

    def bring_to_front(self) -> None:
        self.setWindowState((self.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)
        self.show()
        self.raise_()
        self.activateWindow()
        self._refresh_footer()

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        """Closing the window keeps the app running in the tray."""
        event.ignore()
        self.hide()
        if self.on_hide_to_tray and not self.tray_hint_shown:
            self.tray_hint_shown = True
            self.on_hide_to_tray()
