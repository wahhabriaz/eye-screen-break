from datetime import datetime

import pytest

from eye_break.core.clock import FakeClock
from eye_break.core.scheduler import (
    Outcome,
    Scheduler,
    SchedulerConfig,
    State,
    tomorrow_midnight,
)
from eye_break.services.settings_service import Settings


class Recorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict]] = []

    def __call__(self, event: str, **payload) -> None:
        self.events.append((event, payload))

    def named(self, name: str) -> list[dict]:
        return [p for e, p in self.events if e == name]


def make(**overrides) -> tuple[Scheduler, FakeClock, Recorder]:
    cfg = SchedulerConfig(work_seconds=600, break_seconds=30, notify_before=0, mode="gentle")
    for key, value in overrides.items():
        setattr(cfg, key, value)
    clock = FakeClock()
    rec = Recorder()
    return Scheduler(clock=clock, config=cfg, listener=rec), clock, rec


def run(s: Scheduler, clock: FakeClock, seconds: int, step: float = 1.0, **tick) -> None:
    for _ in range(int(seconds / step)):
        clock.advance(step)
        s.tick(**tick)


def test_break_triggers_exactly_at_interval():
    s, clock, rec = make()
    run(s, clock, 599)
    assert s.state == State.WORKING
    assert s.remaining == pytest.approx(1)
    run(s, clock, 1)
    assert s.state == State.ON_BREAK
    assert len(rec.named("break_started")) == 1


def test_timer_uses_elapsed_time_not_tick_count():
    s, clock, _ = make()
    run(s, clock, 300, step=7.5)  # irregular, slow ticks
    assert s.work_elapsed == pytest.approx(300)


def test_break_countdown_completes_and_resets_session():
    s, clock, rec = make()
    run(s, clock, 600)
    assert s.break_remaining == pytest.approx(30)
    run(s, clock, 15)
    assert s.break_remaining == pytest.approx(15)
    run(s, clock, 15)
    assert s.state == State.WORKING
    ended = rec.named("break_ended")[0]
    assert ended["outcome"] == Outcome.COMPLETED
    assert ended["actual"] == pytest.approx(30)
    assert s.work_elapsed == 0


def test_no_overlapping_breaks():
    s, clock, rec = make()
    assert s.start_break("manual")
    assert not s.start_break("manual")
    assert not s.start_break("scheduled")
    assert len(rec.named("break_started")) == 1


def test_pre_break_notice_emitted_once():
    s, clock, rec = make(notify_before=30)
    run(s, clock, 570)
    assert s.state == State.PRE_BREAK
    run(s, clock, 10)
    assert len(rec.named("pre_break")) == 1


def test_gentle_mode_forces_notice():
    cfg = SchedulerConfig.from_settings(Settings(mode="gentle", notify_before_seconds=0))
    assert cfg.notify_before == 30
    cfg = SchedulerConfig.from_settings(Settings(mode="strict", notify_before_seconds=0))
    assert cfg.notify_before == 0


def test_pause_and_resume_keeps_elapsed():
    s, clock, _ = make()
    run(s, clock, 100)
    s.pause()
    run(s, clock, 1000)
    assert s.state == State.PAUSED
    assert s.work_elapsed == pytest.approx(100)
    s.resume()
    run(s, clock, 10)
    assert s.work_elapsed == pytest.approx(110)


def test_timed_pause_expires():
    s, clock, _ = make()
    s.pause(seconds=1800)
    run(s, clock, 1799)
    assert s.state == State.PAUSED
    run(s, clock, 2)
    assert s.state == State.WORKING


def test_pause_until_tomorrow_uses_wall_clock():
    s, clock, _ = make()
    until = tomorrow_midnight(clock.now())
    assert until == datetime(2026, 1, 6)
    s.pause(until=until)
    run(s, clock, 60)
    assert s.state == State.PAUSED
    clock.set_wall(datetime(2026, 1, 6, 0, 0, 1))
    run(s, clock, 1)
    assert s.state == State.WORKING


def test_meeting_mode_expires():
    s, clock, _ = make()
    s.pause(seconds=900, meeting=True)
    assert s.state == State.MEETING
    run(s, clock, 901)
    assert s.state == State.WORKING


def test_meeting_until_manual_resume():
    s, clock, _ = make()
    s.pause(meeting=True)
    run(s, clock, 5000)
    assert s.state == State.MEETING
    s.resume()
    assert s.state == State.WORKING


def test_auto_meeting_while_presenting():
    s, clock, _ = make(auto_meeting=True)
    run(s, clock, 10, presenting=True)
    assert s.state == State.MEETING and s.hold_is_auto
    run(s, clock, 2, presenting=False)
    assert s.state == State.WORKING


def test_presenting_ignored_when_detection_disabled():
    s, clock, _ = make(auto_meeting=False)
    run(s, clock, 10, presenting=True)
    assert s.state == State.WORKING


def test_snooze_gentle_unlimited():
    s, clock, rec = make(snooze_seconds=300)
    for _ in range(4):
        s.start_break()
        assert s.snooze()
        assert s.state == State.SNOOZED
        assert s.remaining == pytest.approx(300)
    assert [p["outcome"] for p in rec.named("break_ended")] == [Outcome.SNOOZED] * 4


def test_snooze_then_break_fires_after_snooze_period():
    s, clock, rec = make(snooze_seconds=300)
    run(s, clock, 600)
    assert s.snooze()
    run(s, clock, 299)
    assert s.state == State.SNOOZED
    run(s, clock, 1)
    assert s.state == State.ON_BREAK
    assert s.current_break.snoozes == 1


def test_focus_mode_limits_snoozes():
    s, clock, _ = make(mode="focus", max_snoozes=2)
    s.start_break()
    assert s.snooze()
    s.start_break()
    assert s.snooze()
    s.start_break()
    assert not s.snooze()
    assert s.state == State.ON_BREAK


def test_skip_requires_confirmation_flag():
    s, clock, rec = make(mode="focus")
    s.start_break()
    assert not s.skip(confirmed=False)
    assert s.state == State.ON_BREAK
    assert s.skip(confirmed=True)
    assert rec.named("break_ended")[0]["outcome"] == Outcome.SKIPPED


def test_strict_mode_blocks_skip_and_snooze_but_allows_emergency():
    s, clock, rec = make(mode="strict")
    s.start_break()
    assert not s.skip()
    assert not s.snooze()
    assert s.state == State.ON_BREAK
    assert s.emergency_dismiss()
    assert s.state == State.WORKING
    ended = rec.named("break_ended")[0]
    assert ended["outcome"] == Outcome.SKIPPED and ended["emergency"]


def test_idle_pauses_timer_and_resumes():
    s, clock, _ = make(idle_threshold=300, idle_reset_seconds=900)
    run(s, clock, 100)
    # user goes idle; idle seconds grow with time
    for i in range(1, 301):
        clock.advance(1)
        s.tick(idle_seconds=i)
    assert s.state == State.IDLE
    # the idle seconds were credited back (within one tick)
    assert s.work_elapsed == pytest.approx(100, abs=1)
    run(s, clock, 200, idle_seconds=500)
    assert s.state == State.IDLE
    run(s, clock, 1, idle_seconds=0)
    assert s.state == State.WORKING
    assert s.work_elapsed == pytest.approx(100, abs=1)


def test_long_idle_resets_session_when_enabled():
    s, clock, rec = make(idle_threshold=300, idle_reset_seconds=600)
    run(s, clock, 400)
    clock.advance(1)
    s.tick(idle_seconds=300)
    run(s, clock, 400, idle_seconds=700)
    run(s, clock, 1, idle_seconds=0)
    assert s.state == State.WORKING
    assert s.work_elapsed == pytest.approx(0, abs=1)
    assert rec.named("session_reset")


def test_long_idle_does_not_reset_when_disabled():
    s, clock, _ = make(idle_threshold=300, idle_reset_enabled=False, idle_reset_seconds=600)
    run(s, clock, 400)
    clock.advance(1)
    s.tick(idle_seconds=300)
    run(s, clock, 1000, idle_seconds=1300)
    run(s, clock, 1, idle_seconds=0)
    assert s.work_elapsed == pytest.approx(101, abs=1)


def test_locked_session_never_triggers_break():
    s, clock, rec = make()
    run(s, clock, 500)
    run(s, clock, 3000, locked=True)
    assert s.state == State.SUSPENDED
    assert not rec.named("break_started")


def test_sleep_gap_not_counted_and_no_accumulated_breaks():
    s, clock, rec = make(idle_reset_seconds=300)
    run(s, clock, 500)
    clock.advance(8 * 3600)  # laptop slept overnight
    s.tick()
    assert len(rec.named("break_started")) == 0
    assert s.work_elapsed == 0  # long sleep resets session
    run(s, clock, 10)
    assert s.work_elapsed == pytest.approx(10)


def test_short_sleep_gap_does_not_count_as_work():
    s, clock, _ = make(idle_reset_seconds=3600)
    run(s, clock, 100)
    clock.advance(600)
    s.tick()
    assert s.work_elapsed == pytest.approx(100)


def test_sleep_during_break_marks_interrupted():
    s, clock, rec = make()
    s.start_break()
    clock.advance(3600)
    s.tick()
    assert rec.named("break_ended")[0]["outcome"] == Outcome.INTERRUPTED
    assert s.state == State.WORKING


def test_wall_clock_change_does_not_affect_timer():
    s, clock, rec = make()
    run(s, clock, 300)
    clock.set_wall(datetime(2030, 1, 1))
    run(s, clock, 1)
    clock.set_wall(datetime(2020, 1, 1))
    run(s, clock, 298)
    assert s.state == State.WORKING
    run(s, clock, 1)
    assert s.state == State.ON_BREAK


def test_reconfigure_shorter_interval_gives_lead_time():
    s, clock, rec = make()
    run(s, clock, 500)
    s.configure(SchedulerConfig(work_seconds=120, break_seconds=30, notify_before=0))
    s.tick()
    assert s.state == State.WORKING
    assert s.remaining == pytest.approx(60)


def test_reconfigure_break_duration_applies_to_next_break():
    s, clock, _ = make()
    s.configure(SchedulerConfig(work_seconds=600, break_seconds=120, notify_before=0))
    s.start_break()
    assert s.current_break.duration == 120


def test_restart_session():
    s, clock, rec = make()
    run(s, clock, 300)
    s.restart_session()
    assert s.work_elapsed == 0
    assert s.state == State.WORKING


def test_manual_break_during_pause_returns_to_pause():
    s, clock, _ = make()
    s.pause()
    assert s.start_break("manual")
    run(s, clock, 31)
    assert s.state == State.PAUSED


def test_scheduled_break_not_started_while_paused():
    s, clock, _ = make()
    s.pause()
    assert not s.start_break("scheduled")


def test_pause_during_break_interrupts_it():
    s, clock, rec = make()
    s.start_break()
    s.pause(seconds=60)
    assert rec.named("break_ended")[0]["outcome"] == Outcome.INTERRUPTED
    assert s.state == State.PAUSED


def test_active_seconds_accumulate_and_flush():
    s, clock, _ = make()
    run(s, clock, 120)
    assert s.take_active_seconds() == pytest.approx(120)
    assert s.take_active_seconds() == 0


def test_tray_snooze_while_working_pushes_break_back():
    s, clock, _ = make(snooze_seconds=300)
    run(s, clock, 550)
    assert s.snooze()
    assert s.remaining == pytest.approx(300)
    run(s, clock, 100)
    assert s.snooze()  # snoozing again never shortens the wait
    assert s.remaining == pytest.approx(300)
