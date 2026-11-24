import os
from types import SimpleNamespace

import pytest

# Default: headless Qt with two simulated monitors (one at 150% scaling), so tests never dim the
# real screen. Set EYE_BREAK_TEST_QPA=windows to run the same tests against the real desktop.
# (Qt splits platform options on ':', so the config path must be relative - no drive letter.)
_screens = os.path.relpath(os.path.join(os.path.dirname(__file__), "two_screens.json")).replace("\\", "/")
os.environ.setdefault("QT_QPA_PLATFORM", os.environ.get("EYE_BREAK_TEST_QPA", f"offscreen:configfile={_screens}"))


@pytest.fixture()
def services(tmp_path, qapp):
    from eye_break.core.break_manager import BreakManager
    from eye_break.core.clock import FakeClock
    from eye_break.database.connection import connect
    from eye_break.database.repositories import HistoryRepository
    from eye_break.services.notification_service import NotificationService
    from eye_break.services.quote_service import QuoteService
    from eye_break.services.settings_service import SettingsService
    from eye_break.services.statistics_service import StatisticsService
    from eye_break.ui.overlay import OverlayController
    from eye_break.utils.paths import assets_dir

    settings = SettingsService(tmp_path / "settings.json")
    settings.settings.fade_ms = 0  # synchronous show/hide for deterministic tests
    settings.settings.work_minutes = 1
    settings.settings.break_seconds = 20
    settings.settings.notify_before_seconds = 0
    settings.settings.mode = "focus"
    conn = connect(tmp_path / "history.db")
    stats = StatisticsService(HistoryRepository(conn))
    quotes = QuoteService(assets_dir() / "quotes.json")
    notifier = NotificationService()
    notified: list[tuple[str, str]] = []
    notifier.notify = lambda title, msg, seconds=6: notified.append((title, msg))
    notifier.sound = lambda name: notified.append(("sound", name))
    overlay = OverlayController()
    clock = FakeClock()
    state = SimpleNamespace(idle=0.0, locked=False, presenting=False)
    probe = SimpleNamespace(idle_seconds=lambda: state.idle, is_locked=lambda: state.locked,
                            is_presenting=lambda: state.presenting)
    manager = BreakManager(settings, stats, quotes, notifier, overlay, clock=clock, probe=probe)
    yield SimpleNamespace(settings=settings, stats=stats, manager=manager, overlay=overlay, clock=clock,
                          probe_state=state, notified=notified, conn=conn)
    overlay.hide()
    conn.close()
