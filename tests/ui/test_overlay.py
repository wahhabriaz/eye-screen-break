"""Overlay + BreakManager tests on a simulated two-monitor desktop (mocked OS probes, fake clock)."""

from PySide6.QtCore import QEvent
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from eye_break.core.scheduler import State
from eye_break.ui.overlay import DimWindow, format_clock


def advance(svc, seconds: int) -> None:
    for _ in range(seconds):
        svc.clock.advance(1)
        svc.manager.tick()


def live_dim_windows() -> list[DimWindow]:
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    return [w for w in QApplication.topLevelWidgets() if isinstance(w, DimWindow)]


def breaks(svc):
    return svc.conn.execute("SELECT outcome, actual_seconds, trigger FROM breaks ORDER BY id").fetchall()


def test_two_monitors_simulated(qapp):
    assert len(QGuiApplication.screens()) == 2


def test_break_covers_every_monitor_and_dismisses_itself(services):
    svc = services
    advance(svc, 60)
    assert svc.manager.state == State.ON_BREAK
    windows = svc.overlay.windows
    assert len(windows) == len(QGuiApplication.screens()) == 2
    for w, screen in zip(windows, QGuiApplication.screens()):
        assert w.geometry() == screen.geometry()
        assert w.isVisible()
    assert all(w.content is not None for w in windows)  # "all monitors" shows content everywhere
    content = windows[0].content
    assert content.countdown.text() == "00:20"
    assert content.quote.text()
    advance(svc, 10)
    assert content.countdown.text() == "00:10"
    advance(svc, 10)
    assert svc.manager.state == State.WORKING
    assert not svc.overlay.active
    assert live_dim_windows() == []
    assert [tuple(r) for r in breaks(svc)] == [("completed", 20.0, "scheduled")]


def test_background_alpha_is_separate_from_content(services):
    svc = services
    svc.settings.settings.overlay_opacity = 80
    svc.manager.take_break_now()
    w = svc.overlay.windows[0]
    assert w.alpha == 204  # 80% black is painted per pixel...
    assert w.windowOpacity() == 1.0  # ...while the window itself (text, buttons) stays fully opaque
    image = w.grab().toImage()
    corner = image.pixelColor(3, 3)
    assert (corner.red(), corner.green(), corner.blue(), corner.alpha()) == (0, 0, 0, 204)
    svc.manager.emergency_dismiss()


def test_primary_only_content(services):
    svc = services
    svc.settings.settings.overlay_monitor = "primary"
    svc.manager.take_break_now()
    with_content = [w for w in svc.overlay.windows if w.content]
    assert len(svc.overlay.windows) == 2 and len(with_content) == 1
    assert with_content[0].screen() == QGuiApplication.primaryScreen()
    svc.manager.emergency_dismiss()


def test_monitor_change_rebuilds_overlay(services):
    svc = services
    svc.manager.take_break_now()
    first = list(svc.overlay.windows)
    svc.overlay._on_screens_changed()
    assert len(svc.overlay.windows) == 2
    assert all(w not in first for w in svc.overlay.windows)
    svc.manager.emergency_dismiss()
    assert live_dim_windows() == []


def test_repeated_breaks_do_not_leak_windows(services):
    svc = services
    for _ in range(25):
        svc.manager.take_break_now()
        advance(svc, 21)
    assert live_dim_windows() == []
    assert len(breaks(svc)) == 25


def test_focus_mode_snooze_limit_and_confirmed_skip(services):
    svc = services
    svc.manager.take_break_now()
    content = svc.overlay.windows[0].content
    assert content.snooze_btn.isVisibleTo(content)
    assert "2 left" in content.snooze_btn.text()
    content.snooze_btn.click()
    assert svc.manager.state == State.SNOOZED
    svc.manager.take_break_now()
    content = svc.overlay.windows[0].content
    assert "1 left" in content.snooze_btn.text()
    # skip asks for confirmation first
    content.skip_btn.click()
    assert svc.manager.state == State.ON_BREAK
    assert content.confirm.isVisibleTo(content)
    content.confirm.findChildren(type(content.skip_btn))[-1].click()
    assert svc.manager.state == State.WORKING
    assert [r[0] for r in breaks(svc)] == ["snoozed", "skipped"]


def test_strict_mode_hides_controls_and_emergency_exit_works(services, qtbot):
    svc = services
    svc.settings.settings.mode = "strict"
    svc.manager.apply_settings()
    svc.manager.take_break_now()
    content = svc.overlay.windows[0].content
    assert not content.snooze_btn.isVisibleTo(content)
    assert not content.skip_btn.isVisibleTo(content)
    assert "hold Esc" in content.hint.text()
    svc.manager.skip()  # ordinary skip is refused
    assert svc.manager.state == State.ON_BREAK
    svc.overlay._hold.setInterval(50)  # the real hold is 3 s
    with qtbot.waitSignal(svc.overlay.emergency_requested, timeout=2000):
        svc.overlay._on_esc_pressed()
    assert svc.manager.state == State.WORKING
    assert [r[0] for r in breaks(svc)] == ["skipped"]


def test_releasing_esc_early_cancels_emergency(services, qtbot):
    svc = services
    svc.settings.settings.mode = "strict"
    svc.manager.apply_settings()
    svc.manager.take_break_now()
    svc.overlay._hold.setInterval(200)
    svc.overlay._on_esc_pressed()
    svc.overlay._hold.stop()  # what esc_released triggers
    qtbot.wait(300)
    assert svc.manager.state == State.ON_BREAK
    svc.manager.emergency_dismiss()


def test_preview_does_not_touch_statistics(services, qtbot):
    svc = services
    assert svc.manager.preview()
    assert svc.overlay.previewing
    content = svc.overlay.windows[0].content
    assert content.close_btn.isVisibleTo(content)
    assert not content.skip_btn.isVisibleTo(content)
    with qtbot.waitSignal(svc.overlay.preview_finished, timeout=1000):
        content.close_btn.click()
    assert not svc.overlay.active
    assert breaks(svc) == []
    assert svc.manager.state == State.WORKING


def test_no_overlapping_overlays(services):
    svc = services
    svc.manager.take_break_now()
    first = list(svc.overlay.windows)
    svc.manager.take_break_now()
    assert svc.overlay.windows == first
    assert not svc.manager.preview()
    svc.manager.emergency_dismiss()


def test_pre_break_notification_and_sounds(services):
    svc = services
    s = svc.settings.settings
    s.notify_before_seconds = 10
    s.sound_pre_break = s.sound_break_start = s.sound_break_end = True
    svc.manager.apply_settings()
    advance(svc, 81)
    titles = [t for t, _ in svc.notified]
    assert "Eye break coming up" in titles
    assert ("sound", "pre_break") in svc.notified
    assert ("sound", "break_start") in svc.notified
    assert ("sound", "break_end") in svc.notified


def test_locked_and_idle_never_show_overlay(services):
    svc = services
    svc.probe_state.locked = True
    advance(svc, 300)
    assert svc.manager.state == State.SUSPENDED
    assert not svc.overlay.active


def test_active_time_flushed_to_statistics(services):
    svc = services
    svc.settings.settings.work_minutes = 30
    svc.manager.apply_settings()
    advance(svc, 125)
    svc.manager.stop()
    total = svc.conn.execute("SELECT SUM(active_seconds) FROM activity").fetchone()[0]
    assert total == 125


def test_stop_during_break_records_interruption(services):
    svc = services
    svc.manager.take_break_now()
    advance(svc, 5)
    svc.manager.stop()
    assert [r[0] for r in breaks(svc)] == ["interrupted"]
    assert not svc.overlay.active


def test_format_clock():
    assert format_clock(0) == "00:00"
    assert format_clock(29.2) == "00:30"
    assert format_clock(600) == "10:00"
