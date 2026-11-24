"""Qt-side coordinator: drives the scheduler once per second and reacts to its events."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import QObject, QTimer, Signal

from eye_break.core.clock import Clock
from eye_break.core.reminder_manager import REMINDER_TEXT, ReminderManager
from eye_break.core.scheduler import (
    ACTIVE_STATES,
    BreakInfo,
    Outcome,
    Scheduler,
    SchedulerConfig,
    State,
    tomorrow_midnight,
)
from eye_break.database.repositories import BreakRecord
from eye_break.platform import windows as win
from eye_break.services.notification_service import NotificationService
from eye_break.services.quote_service import QuoteService
from eye_break.services.settings_service import SettingsService
from eye_break.services.statistics_service import StatisticsService
from eye_break.ui.overlay import BreakView, OverlayController, OverlayOptions
from eye_break.ui.themes import current as current_tokens

log = logging.getLogger(__name__)

TICK_MS = 1000
FLUSH_EVERY_SECONDS = 60
PREVIEW_SECONDS = 10


class SystemProbe:
    """Indirection over OS queries so tests can substitute values."""

    idle_seconds: Callable[[], float] = staticmethod(win.idle_seconds)
    is_locked: Callable[[], bool] = staticmethod(win.is_session_locked)
    is_presenting: Callable[[], bool] = staticmethod(win.is_presenting)


class BreakManager(QObject):
    state_changed = Signal(object)
    ticked = Signal()
    stats_changed = Signal()

    def __init__(
        self,
        settings: SettingsService,
        stats: StatisticsService,
        quotes: QuoteService,
        notifier: NotificationService,
        overlay: OverlayController,
        clock: Clock | None = None,
        probe: SystemProbe | None = None,
    ) -> None:
        super().__init__()
        self.settings_service = settings
        self.stats = stats
        self.quotes = quotes
        self.notifier = notifier
        self.overlay = overlay
        self.clock = clock or Clock()
        self.probe = probe or SystemProbe()
        self.reminders = ReminderManager()
        self.scheduler = Scheduler(
            clock=self.clock,
            config=SchedulerConfig.from_settings(settings.settings),
            listener=self._on_event,
        )
        self._unflushed = 0.0
        self._since_flush = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self.tick)
        overlay.snooze_requested.connect(self.snooze)
        overlay.skip_requested.connect(lambda: self.skip(confirmed=True))
        overlay.emergency_requested.connect(self.emergency_dismiss)

    @property
    def s(self):
        return self.settings_service.settings

    @property
    def pending_active(self) -> float:
        """Active seconds measured but not yet written to the database."""
        return self._unflushed + self.scheduler.active_pending

    def discard_pending_activity(self) -> None:
        """Used when the user deletes their history."""
        self._unflushed = 0.0
        self.scheduler.take_active_seconds()

    @property
    def state(self) -> State:
        return self.scheduler.state

    def start(self) -> None:
        self._timer.start()

    def stop(self) -> None:
        """Clean shutdown: stop timers, close overlays, persist pending activity."""
        self._timer.stop()
        if self.scheduler.state == State.ON_BREAK:
            self.scheduler.pause()  # records the open break as interrupted
        self.overlay.hide(immediate=True)
        self._flush(force=True)

    # ---- actions (UI / tray) ---------------------------------------------------------------
    def apply_settings(self) -> None:
        self.scheduler.configure(SchedulerConfig.from_settings(self.s))
        self.ticked.emit()

    def take_break_now(self) -> None:
        if self.overlay.previewing:
            self.overlay.hide()
        self.scheduler.start_break("manual")

    def snooze(self) -> None:
        self.scheduler.snooze()
        self.ticked.emit()

    def skip(self, confirmed: bool = True) -> None:
        self.scheduler.skip(confirmed=confirmed)

    def emergency_dismiss(self) -> None:
        self.scheduler.emergency_dismiss()

    def pause(self, seconds: float | None = None, until_tomorrow: bool = False, meeting: bool = False) -> None:
        until = tomorrow_midnight(self.clock.now()) if until_tomorrow else None
        self.scheduler.pause(seconds=seconds, until=until, meeting=meeting)
        self.ticked.emit()

    def resume(self) -> None:
        self.scheduler.resume()
        self.ticked.emit()

    def restart_session(self) -> None:
        self.scheduler.restart_session()
        self.ticked.emit()

    def preview(self) -> bool:
        """Show a short, dismissible overlay preview that never touches statistics."""
        if self.scheduler.state == State.ON_BREAK:
            return False
        view = BreakView(
            duration=PREVIEW_SECONDS,
            quote=self._quote(),
            instruction=self.quotes.next_instruction() if self.s.show_instructions else None,
            mode=self.s.mode,
            preview=True,
        )
        self.overlay.show(view, self.overlay_options())
        return True

    def overlay_options(self) -> OverlayOptions:
        s = self.s
        return OverlayOptions(
            opacity=s.overlay_opacity, font_scale=s.overlay_font_scale, countdown_size=s.countdown_size,
            show_quote=s.show_quotes, show_instruction=s.show_instructions, show_progress=s.show_progress,
            fade_ms=s.fade_ms, monitor=s.overlay_monitor, accent=current_tokens().accent,
        )

    # ---- loop ------------------------------------------------------------------------------
    def tick(self) -> None:
        sch = self.scheduler
        presenting = self.s.auto_meeting_detection and sch.state != State.ON_BREAK and self.probe.is_presenting()
        sch.tick(idle_seconds=self.probe.idle_seconds(), locked=self.probe.is_locked(), presenting=presenting)

        if sch.state == State.ON_BREAK:
            self.overlay.set_remaining(sch.break_remaining)
            if self.s.mode == "strict":
                self.overlay.raise_windows()

        delta = sch.take_active_seconds()
        self._unflushed += delta
        self._since_flush += TICK_MS / 1000
        kind = self.reminders.tick(
            self.s.reminders, max(0.0, delta),
            can_interrupt=sch.state in ACTIVE_STATES, seconds_to_break=sch.remaining,
        )
        if kind:
            title, message = REMINDER_TEXT[kind]
            self.notifier.notify(title, message)
        self._flush()
        self.ticked.emit()

    def _flush(self, force: bool = False) -> None:
        if (force or self._since_flush >= FLUSH_EVERY_SECONDS) and self._unflushed:
            self.stats.add_active_seconds(self.clock.now(), self._unflushed)
            self._unflushed = 0.0
            self._since_flush = 0.0
            self.stats_changed.emit()

    # ---- scheduler events ------------------------------------------------------------------
    def _on_event(self, event: str, **payload) -> None:
        handler = getattr(self, f"_on_{event}", None)
        if handler:
            handler(**payload)

    def _on_state_changed(self, old: State, new: State) -> None:
        self.state_changed.emit(new)

    def _on_pre_break(self, seconds: float) -> None:
        secs = round(seconds)
        when = f"{secs} seconds" if secs < 90 else f"{round(secs / 60)} minutes"
        self.notifier.notify("Eye break coming up", f"Your next eye break starts in {when}.")
        if self.s.sound_pre_break:
            self.notifier.sound("pre_break")

    def _on_break_started(self, info: BreakInfo) -> None:
        mode = self.s.mode
        sch = self.scheduler
        snoozes_left = None
        if mode == "focus":
            snoozes_left = max(0, self.s.max_snoozes - sch.snoozes)
        view = BreakView(
            duration=info.duration,
            quote=self._quote(),
            instruction=self.quotes.next_instruction() if self.s.show_instructions else None,
            mode=mode,
            can_snooze=sch.can_snooze(),
            snoozes_left=snoozes_left,
            can_skip=sch.can_skip(),
            skip_needs_confirm=mode == "focus",
            snooze_minutes=self.s.snooze_minutes,
        )
        self.overlay.show(view, self.overlay_options())
        if self.s.sound_break_start:
            self.notifier.sound("break_start")
        log.info("Break started (%s, %ss, mode=%s)", info.trigger, info.duration, mode)

    def _on_break_ended(self, info: BreakInfo, outcome: Outcome, actual: float,
                        ended_wall: datetime, emergency: bool) -> None:
        self.overlay.hide()
        self.stats.record_break(BreakRecord(
            started_at=info.started_wall, ended_at=ended_wall, planned_seconds=info.duration,
            actual_seconds=actual, outcome=str(outcome), trigger=info.trigger, mode=self.s.mode,
        ))
        if outcome == Outcome.COMPLETED:
            self.reminders.on_eye_break_completed()
            if self.s.sound_break_end:
                self.notifier.sound("break_end")
        log.info("Break ended: %s after %.0fs%s", outcome, actual, " (emergency)" if emergency else "")
        self.stats_changed.emit()

    def _quote(self) -> str | None:
        if not self.s.show_quotes:
            return None
        return self.quotes.next_quote(self.s.quote_categories, self.s.custom_quotes)
