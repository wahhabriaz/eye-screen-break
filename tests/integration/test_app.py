"""Full application wiring (real services, real SQLite/JSON on disk; Qt offscreen)."""

import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from PySide6.QtWidgets import QPushButton

from eye_break.app import EyeBreakApp, parse_args
from eye_break.core.scheduler import State
from eye_break.ui.main_window import NAV
from eye_break.utils import paths
from eye_break.utils.single_instance import SingleInstance, send


@pytest.fixture()
def make_app(tmp_path, qapp):
    created: list[EyeBreakApp] = []

    def factory() -> EyeBreakApp:
        paths.set_data_dir(tmp_path)
        app = EyeBreakApp(qapp, parse_args(["--data-dir", str(tmp_path)]))
        created.append(app)
        return app

    yield factory
    for app in created:
        if app.conn:
            try:
                app.shutdown()
            except Exception:  # already shut down
                pass
    paths.set_data_dir(None)


CLIENT = """
import sys
from PySide6.QtCore import QCoreApplication
from eye_break.utils.single_instance import SingleInstance
app = QCoreApplication([])
print(SingleInstance(sys.argv[1]).is_primary(sys.argv[2].encode()))
"""


def run_second_instance(name: str, message: str) -> subprocess.Popen:
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[2] / "src")}
    return subprocess.Popen([sys.executable, "-c", CLIENT, name, message], env=env,
                            stdout=subprocess.PIPE, text=True)


def test_single_instance_enforced_across_processes(qtbot):
    name = f"EyeBreakTest-{uuid.uuid4().hex}"
    first = SingleInstance(name)
    assert first.is_primary()
    with qtbot.waitSignal(first.activation_requested, timeout=10000):
        proc = run_second_instance(name, "show")
    assert proc.communicate(timeout=10)[0].strip() == "False"  # the second launch defers to the first
    with qtbot.waitSignal(first.quit_requested, timeout=10000):
        proc = run_second_instance(name, "quit")
    proc.communicate(timeout=10)
    first.close()
    assert not send(name, b"show")  # nobody listening any more
    third = SingleInstance(name)
    assert third.is_primary()  # the name is free again after the first instance exits
    third.close()


def test_settings_persist_across_restart(make_app):
    app = make_app()
    app.ctx.update(work_minutes=45, break_seconds=120, theme="light", mode="strict", custom_quotes=["Mine."])
    app.shutdown()
    app.conn = None
    again = make_app()
    s = again.settings.settings
    assert (s.work_minutes, s.break_seconds, s.theme, s.mode, s.custom_quotes) == (45, 120, "light", "strict", ["Mine."])
    assert again.manager.scheduler.config.work_seconds == 45 * 60


def test_history_persists_across_restart(make_app):
    app = make_app()
    app.overlay.options.fade_ms = 0
    app.settings.settings.fade_ms = 0
    app.manager.take_break_now()
    app.manager.skip()
    app.shutdown()
    app.conn = None
    again = make_app()
    from datetime import date

    assert again.stats.summary("today", date.today()).skipped == 1


def test_every_page_builds_in_both_themes(make_app):
    app = make_app()
    for theme in ("dark", "light", "system"):
        app.theme.apply(theme, "violet")
        for key, *_ in NAV:
            app.window.show_page(key)
            assert app.window.stack.currentWidget() is app.window.pages[key]


def test_no_button_is_a_placeholder(make_app):
    """Every visible button must be wired to something."""
    app = make_app()
    for page in app.window.pages.values():
        for btn in page.findChildren(QPushButton):
            if btn.property("variant") == "segment" or btn.isCheckable():
                continue
            assert btn.receivers("2clicked(bool)") > 0, f"unwired button: {btn.text()!r}"


def test_tray_menu_actions(make_app):
    app = make_app()
    tray = app.tray
    texts = [a.text() for a in tray.menu.actions() if a.text()]
    for expected in ("Open dashboard", "Take a break now", "Pause reminders", "Resume reminders",
                     "Pause for", "Meeting mode", "Settings", "Exit Eye Break"):
        assert expected in texts
    assert any(t.startswith("Snooze for") for t in texts)
    assert tray.status_action.text().startswith("Next break in")
    tray.pause_action.trigger()
    assert app.manager.state == State.PAUSED
    tray.refresh()
    assert tray.resume_action.isEnabled() and not tray.pause_action.isEnabled()
    tray.resume_action.trigger()
    assert app.manager.state == State.WORKING
    tray.meeting_menu.actions()[0].trigger()  # 15 minutes
    assert app.manager.state == State.MEETING
    assert "Meeting mode until" in tray.status_text()


def test_close_hides_to_tray_and_releases_window(make_app, qtbot):
    app = make_app()
    window = app.window
    window.show()
    window.close()
    assert not window.isVisible()
    assert app._window is None  # released to keep the background footprint small
    # long-lived signals keep firing safely after the pages are destroyed
    qtbot.wait(50)
    app.manager.tick()
    app.manager.pause()
    app.manager.resume()
    app.ctx.update(work_minutes=45)
    assert app.manager._timer is not None  # app still running
    assert app.window is not window  # reopening builds a fresh dashboard


def test_live_settings_change_without_restart(make_app):
    app = make_app()
    app.ctx.update(work_minutes=20)
    assert app.manager.scheduler.config.work_seconds == 20 * 60
    app.ctx.update(break_seconds=45)
    app.manager.take_break_now()
    assert app.manager.scheduler.current_break.duration == 45
