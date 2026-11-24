"""Application entry point and composition root."""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from eye_break import APP_ID, APP_NAME, __version__
from eye_break.core.break_manager import BreakManager
from eye_break.core.clock import Clock, ScaledClock
from eye_break.database.connection import connect
from eye_break.database.repositories import HistoryRepository
from eye_break.platform.windows import IS_WINDOWS, startup
from eye_break.services.notification_service import NotificationService
from eye_break.services.quote_service import QuoteService
from eye_break.services.settings_service import SettingsService
from eye_break.services.statistics_service import StatisticsService
from eye_break.ui import icons
from eye_break.ui.context import AppContext
from eye_break.ui.main_window import MainWindow
from eye_break.ui.overlay import OverlayController
from eye_break.ui.system_tray import SystemTray
from eye_break.ui.themes import ThemeManager
from eye_break.utils import paths
from eye_break.utils.single_instance import SingleInstance, send, server_name

log = logging.getLogger("eye_break")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="eye-break", description=f"{APP_NAME} {__version__}")
    parser.add_argument("--minimized", action="store_true", help="start in the system tray")
    parser.add_argument("--data-dir", help="use a different data directory (testing)")
    parser.add_argument("--dev-speed", type=float, default=float(os.environ.get("EYE_BREAK_DEV_SPEED", "1")),
                        help="development only: run the clock N times faster")
    parser.add_argument("--quit", action="store_true", help="ask a running instance to exit, then exit")
    parser.add_argument("--version", action="version", version=__version__)
    args, _unknown = parser.parse_known_args(argv)
    return args


def setup_logging() -> None:
    handler = RotatingFileHandler(paths.log_dir() / "eye-break.log", maxBytes=512_000, backupCount=2,
                                  encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    if sys.stderr is not None and not getattr(sys, "frozen", False):
        root.addHandler(logging.StreamHandler())


class EyeBreakApp:
    def __init__(self, qt_app: QApplication, args: argparse.Namespace) -> None:
        self.qt = qt_app
        self.settings = SettingsService(paths.settings_file())
        s = self.settings.settings
        self.conn = connect(paths.database_file())
        repo = HistoryRepository(self.conn)
        self.stats = StatisticsService(repo)
        self.quotes = QuoteService(
            paths.assets_dir() / "quotes.json",
            load_recent=lambda: [q for q in (repo.get_kv("recent_quotes") or "").split("\n") if q],
            save_recent=lambda r: repo.set_kv("recent_quotes", "\n".join(r[-120:])),
        )
        self.theme = ThemeManager(s.theme, s.accent)
        self.theme.apply()
        self.notifier = NotificationService()
        self.overlay = OverlayController()
        clock: Clock = ScaledClock(args.dev_speed) if args.dev_speed > 1 else Clock()
        if args.dev_speed > 1:
            log.warning("Development clock running at %sx speed", args.dev_speed)
        self.manager = BreakManager(self.settings, self.stats, self.quotes, self.notifier, self.overlay, clock)
        self.ctx = AppContext(self.settings, self.manager, self.stats, self.quotes, self.theme)
        self._window: MainWindow | None = None
        self._tray_hint_shown = False
        self.tray = SystemTray(self.ctx, self.open_dashboard, self.quit)
        self.notifier.tray = self.tray
        self.qt.aboutToQuit.connect(self.shutdown)
        self._sync_startup_registration()

    @property
    def window(self) -> MainWindow:
        """The dashboard is built on demand and released when closed, keeping the tray footprint small."""
        if self._window is None:
            self._window = MainWindow(self.ctx)
            self._window.on_hide_to_tray = self._on_window_hidden
        return self._window

    def _on_window_hidden(self) -> None:
        if not self._tray_hint_shown:
            self._tray_hint_shown = True
            self.notifier.notify(APP_NAME, "Still running in the system tray. Right-click the icon for quick actions.")
        window, self._window = self._window, None
        if window is not None:
            self.ctx.flush()
            window.deleteLater()

    def _sync_startup_registration(self) -> None:
        """Keep the Run entry pointing at the current executable if the user enabled it."""
        if IS_WINDOWS and startup.is_enabled():
            startup.set_enabled(True)

    def start(self, minimized: bool) -> None:
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()
        else:
            minimized = False  # without a tray the window is the only way in
        self.manager.start()
        if not minimized:
            self.window.bring_to_front()
        log.info("%s %s started (minimized=%s)", APP_NAME, __version__, minimized)

    def open_dashboard(self, page: str = "overview") -> None:
        self.window.show_page(page)
        self.window.bring_to_front()

    def quit(self) -> None:
        self.qt.quit()

    def shutdown(self) -> None:
        log.info("Shutting down")
        self.manager.stop()
        self.ctx.flush()
        self.tray.hide()
        self.conn.close()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.data_dir:
        paths.set_data_dir(args.data_dir)
    setup_logging()
    if IS_WINDOWS:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"{APP_ID}.Desktop")
    qt_app = QApplication(sys.argv[:1])
    qt_app.setApplicationName(APP_NAME)
    qt_app.setOrganizationName(APP_ID)
    qt_app.setApplicationVersion(__version__)
    qt_app.setQuitOnLastWindowClosed(False)
    qt_app.setWindowIcon(icons.app_icon())
    qt_app.setStyle("Fusion")  # consistent base for the custom stylesheet

    # A separate data folder is a separate instance (tests, dev runs); the default folder has no suffix.
    suffix = "-" + hashlib.sha1(str(paths.data_dir()).lower().encode()).hexdigest()[:10] if args.data_dir else ""
    if args.quit:
        send(server_name(suffix), b"quit")
        return 0
    instance = SingleInstance(server_name(suffix))
    if not instance.is_primary():
        log.info("Another instance is running; asked it to show its window")
        return 0

    app = EyeBreakApp(qt_app, args)
    instance.activation_requested.connect(app.open_dashboard)
    instance.quit_requested.connect(app.quit)
    # Autostart passes --minimized; it is honoured when "Start minimised" is on. Manual launches show the window.
    start_minimized = args.minimized and app.settings.settings.start_minimized
    QTimer.singleShot(0, lambda: app.start(minimized=start_minimized))
    code = qt_app.exec()
    instance.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
