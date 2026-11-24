"""Break scheduling state machine.

Pure Python (no Qt) and driven by `tick()`, so it is fully testable with a fake clock.
Durations come from monotonic time; wall time is only used for calendar holds
("pause until tomorrow") and timestamps. Work time is accumulated from tick deltas,
and a delta larger than `SLEEP_GAP_SECONDS` is treated as system sleep, never as work.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from eye_break.core.clock import Clock
from eye_break.services.settings_service import Settings

log = logging.getLogger(__name__)

SLEEP_GAP_SECONDS = 20.0
MIN_LEAD_AFTER_RECONFIGURE = 60.0
GENTLE_DEFAULT_NOTICE = 30


class State(StrEnum):
    WORKING = "working"
    IDLE = "idle"
    PRE_BREAK = "pre_break"
    ON_BREAK = "on_break"
    SNOOZED = "snoozed"
    PAUSED = "paused"
    MEETING = "meeting"
    SUSPENDED = "suspended"  # session locked / system suspended


ACTIVE_STATES = frozenset({State.WORKING, State.PRE_BREAK, State.SNOOZED})
HOLD_STATES = frozenset({State.PAUSED, State.MEETING})


class Outcome(StrEnum):
    COMPLETED = "completed"
    SKIPPED = "skipped"
    SNOOZED = "snoozed"
    INTERRUPTED = "interrupted"


@dataclass
class SchedulerConfig:
    work_seconds: float = 30 * 60
    break_seconds: float = 30
    mode: str = "gentle"
    idle_threshold: float = 5 * 60
    idle_reset_enabled: bool = True
    idle_reset_seconds: float = 5 * 60
    notify_before: float = 30
    snooze_seconds: float = 5 * 60
    max_snoozes: int = 2
    auto_meeting: bool = False

    @classmethod
    def from_settings(cls, s: Settings) -> SchedulerConfig:
        notify = s.notify_before_seconds
        if s.mode == "gentle" and notify == 0:
            notify = GENTLE_DEFAULT_NOTICE  # gentle mode always announces breaks
        return cls(
            work_seconds=s.work_minutes * 60,
            break_seconds=s.break_seconds,
            mode=s.mode,
            idle_threshold=s.idle_threshold_minutes * 60,
            idle_reset_enabled=s.idle_reset_enabled,
            idle_reset_seconds=max(s.idle_reset_minutes, s.idle_threshold_minutes) * 60,
            notify_before=notify,
            snooze_seconds=s.snooze_minutes * 60,
            max_snoozes=s.max_snoozes,
            auto_meeting=s.auto_meeting_detection,
        )


@dataclass
class BreakInfo:
    started_mono: float
    started_wall: datetime
    duration: float
    trigger: str  # "scheduled" | "manual"
    snoozes: int = 0


@dataclass
class _Hold:
    state: State
    until_mono: float | None = None
    until_wall: datetime | None = None
    auto: bool = False  # set by full-screen/presentation detection


@dataclass
class Scheduler:
    clock: Clock
    config: SchedulerConfig = field(default_factory=SchedulerConfig)
    listener: Callable[..., Any] | None = None

    def __post_init__(self) -> None:
        self.state: State = State.WORKING
        self.work_elapsed: float = 0.0
        self.active_pending: float = 0.0  # active seconds not yet flushed to statistics
        self.current_break: BreakInfo | None = None
        self.snoozes: int = 0
        self._notified = False
        self._last = self.clock.monotonic()
        self._away_since: float | None = None
        self._resume_state: State = State.WORKING
        self._hold: _Hold | None = None

    # ---- queries ---------------------------------------------------------------------------
    @property
    def remaining(self) -> float:
        return max(0.0, self.config.work_seconds - self.work_elapsed)

    @property
    def break_remaining(self) -> float:
        if not self.current_break:
            return 0.0
        end = self.current_break.started_mono + self.current_break.duration
        return max(0.0, end - self.clock.monotonic())

    @property
    def hold_until(self) -> datetime | None:
        if not self._hold:
            return None
        if self._hold.until_wall:
            return self._hold.until_wall
        if self._hold.until_mono is not None:
            return self.clock.now() + timedelta(seconds=self._hold.until_mono - self.clock.monotonic())
        return None

    @property
    def hold_is_auto(self) -> bool:
        return bool(self._hold and self._hold.auto)

    def can_snooze(self) -> bool:
        if self.config.mode == "strict":
            return False
        if self.config.mode == "focus":
            return self.snoozes < self.config.max_snoozes
        return True

    def can_skip(self) -> bool:
        return self.config.mode != "strict"

    # ---- configuration ---------------------------------------------------------------------
    def configure(self, config: SchedulerConfig) -> None:
        """Apply new preferences live, without restarting the session."""
        old_work = self.config.work_seconds
        self.config = config
        if config.work_seconds != old_work and self.work_elapsed > config.work_seconds - MIN_LEAD_AFTER_RECONFIGURE:
            # Shortening the interval must not fire a surprise break immediately.
            self.work_elapsed = max(0.0, config.work_seconds - MIN_LEAD_AFTER_RECONFIGURE)
        self._refresh_notice()

    # ---- main loop -------------------------------------------------------------------------
    def tick(self, idle_seconds: float = 0.0, locked: bool = False, presenting: bool = False) -> None:
        now = self.clock.monotonic()
        delta = max(0.0, now - self._last)
        self._last = now
        if delta > SLEEP_GAP_SECONDS:
            self._on_sleep_gap(delta)
            delta = 0.0

        if self.state in HOLD_STATES:
            self._check_hold(now, presenting)
            if self.state in HOLD_STATES:
                return

        if self.state == State.ON_BREAK:
            if self.break_remaining <= 0:
                self._end_break(Outcome.COMPLETED)
            return

        if self.state == State.SUSPENDED:
            if not locked:
                self._return_from_away(now)
            return

        if self.state == State.IDLE:
            if locked:
                self._set_state(State.SUSPENDED)
            elif idle_seconds < self.config.idle_threshold:
                self._return_from_away(now)
            return

        # Active states.
        if locked:
            self._resume_state = self.state
            self._away_since = now
            self._set_state(State.SUSPENDED)
            return
        if idle_seconds >= self.config.idle_threshold:
            # The idle threshold window was not real work: give it back.
            credit = min(idle_seconds, self.config.idle_threshold + SLEEP_GAP_SECONDS, self.work_elapsed)
            self.work_elapsed -= credit
            self.active_pending -= credit
            self._resume_state = self.state
            self._away_since = now - idle_seconds
            self._set_state(State.IDLE)
            return
        if presenting and self.config.auto_meeting:
            self._hold = _Hold(State.MEETING, auto=True)
            self._set_state(State.MEETING)
            return

        self.work_elapsed += delta
        self.active_pending += delta
        remaining = self.remaining
        if remaining <= 0:
            self.start_break("scheduled")
        elif not self._notified and 0 < self.config.notify_before and remaining <= self.config.notify_before:
            self._notified = True
            if self.state == State.WORKING:
                self._set_state(State.PRE_BREAK)
            self._emit("pre_break", seconds=remaining)

    # ---- user actions ----------------------------------------------------------------------
    def start_break(self, trigger: str = "manual") -> bool:
        if self.state == State.ON_BREAK:
            return False  # never overlap breaks
        if self.state in HOLD_STATES or self.state in (State.IDLE, State.SUSPENDED):
            if trigger == "scheduled":
                return False
        if self.state not in ACTIVE_STATES:
            self._resume_state = self.state if self.state in HOLD_STATES else State.WORKING
        else:
            self._resume_state = State.WORKING
        self.current_break = BreakInfo(
            started_mono=self.clock.monotonic(),
            started_wall=self.clock.now(),
            duration=self.config.break_seconds,
            trigger=trigger,
            snoozes=self.snoozes,
        )
        self._set_state(State.ON_BREAK)
        self._emit("break_started", info=self.current_break)
        return True

    def skip(self, confirmed: bool = True) -> bool:
        if self.state != State.ON_BREAK or not self.can_skip() or not confirmed:
            return False
        self._end_break(Outcome.SKIPPED)
        return True

    def emergency_dismiss(self) -> bool:
        """Always available, in every mode (documented safety exit for strict mode)."""
        if self.state != State.ON_BREAK:
            return False
        self._end_break(Outcome.SKIPPED, emergency=True)
        return True

    def snooze(self) -> bool:
        """Snooze an active break, or push back the next break while working."""
        snooze = self.config.snooze_seconds
        if self.state == State.ON_BREAK:
            if not self.can_snooze():
                return False
            self.snoozes += 1
            self._end_break(Outcome.SNOOZED, keep_session=True)
            self.work_elapsed = max(0.0, self.config.work_seconds - snooze)
            self._set_state(State.SNOOZED)
        elif self.state in ACTIVE_STATES:
            self.work_elapsed = min(self.work_elapsed, max(0.0, self.config.work_seconds - snooze))
            self._set_state(State.SNOOZED)
        else:
            return False
        self._refresh_notice()
        return True

    def pause(
        self,
        seconds: float | None = None,
        until: datetime | None = None,
        meeting: bool = False,
    ) -> None:
        """Pause reminders for a duration, until a wall time, or indefinitely (both None)."""
        if self.state == State.ON_BREAK:
            self._end_break(Outcome.INTERRUPTED, keep_session=True)
        target = State.MEETING if meeting else State.PAUSED
        until_mono = self.clock.monotonic() + seconds if seconds is not None else None
        self._hold = _Hold(target, until_mono=until_mono, until_wall=until)
        self._set_state(target)

    def resume(self) -> None:
        if self.state == State.ON_BREAK:
            return
        self._hold = None
        self._last = self.clock.monotonic()
        self._set_state(State.WORKING)
        self._refresh_notice()

    def restart_session(self) -> None:
        if self.state == State.ON_BREAK:
            return
        self.work_elapsed = 0.0
        self.snoozes = 0
        self._notified = False
        if self.state in ACTIVE_STATES:
            self._set_state(State.WORKING)
        self._emit("session_reset")

    def take_active_seconds(self) -> float:
        value, self.active_pending = self.active_pending, 0.0
        return value

    # ---- internals -------------------------------------------------------------------------
    def _end_break(self, outcome: Outcome, keep_session: bool = False, emergency: bool = False) -> None:
        info = self.current_break
        if info is None:
            return
        actual = min(info.duration, max(0.0, self.clock.monotonic() - info.started_mono))
        self.current_break = None
        if not keep_session:
            self.work_elapsed = 0.0
            self.snoozes = 0
        self._notified = False
        resume = self._resume_state
        if resume in HOLD_STATES and self._hold and not keep_session:
            self._set_state(resume)
        else:
            self._set_state(State.WORKING)
        self._emit("break_ended", info=info, outcome=outcome, actual=actual,
                   ended_wall=self.clock.now(), emergency=emergency)

    def _on_sleep_gap(self, gap: float) -> None:
        log.info("Detected %.0fs gap (system sleep/hibernate); not counted as work", gap)
        if self.state == State.ON_BREAK:
            self._end_break(Outcome.INTERRUPTED)
            return
        if self.state in ACTIVE_STATES | {State.IDLE, State.SUSPENDED}:
            away = gap
            if self._away_since is not None and self.state != State.WORKING:
                away = self.clock.monotonic() - self._away_since
            if self.config.idle_reset_enabled and away >= self.config.idle_reset_seconds:
                self._reset_after_away()

    def _return_from_away(self, now: float) -> None:
        away = now - self._away_since if self._away_since is not None else 0.0
        self._away_since = None
        if self.config.idle_reset_enabled and away >= self.config.idle_reset_seconds:
            self._reset_after_away()
            self._set_state(State.WORKING)
        else:
            self._set_state(self._resume_state if self._resume_state in ACTIVE_STATES else State.WORKING)
            self._refresh_notice()

    def _reset_after_away(self) -> None:
        self.work_elapsed = 0.0
        self.snoozes = 0
        self._notified = False
        self._resume_state = State.WORKING
        self._emit("session_reset")

    def _check_hold(self, now: float, presenting: bool) -> None:
        hold = self._hold
        if hold is None:
            self.resume()
            return
        expired = (
            (hold.auto and not presenting)
            or (hold.until_mono is not None and now >= hold.until_mono)
            or (hold.until_wall is not None and self.clock.now() >= hold.until_wall)
        )
        if expired:
            self.resume()

    def _refresh_notice(self) -> None:
        self._notified = self.remaining <= self.config.notify_before and self.state == State.PRE_BREAK
        if self.state == State.PRE_BREAK and self.remaining > self.config.notify_before:
            self._set_state(State.WORKING)

    def _set_state(self, state: State) -> None:
        if state == self.state:
            return
        old, self.state = self.state, state
        log.debug("State %s -> %s", old, state)
        self._emit("state_changed", old=old, new=state)

    def _emit(self, event: str, **payload: Any) -> None:
        if self.listener:
            self.listener(event, **payload)


def tomorrow_midnight(now: datetime) -> datetime:
    return datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
