from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QMenu, QVBoxLayout, QWidget

from eye_break.core.scheduler import State
from eye_break.ui.components import (
    Card,
    Page,
    ProgressRing,
    StatTile,
    button,
    format_duration,
    format_rate,
    label,
    refresh_icon,
    repolish,
    tile_grid,
)
from eye_break.ui.context import AppContext
from eye_break.ui.overlay import format_clock
from eye_break.ui.themes import SPACE

STATUS = {
    State.WORKING: ("Working", "Tracking active time until your next break."),
    State.PRE_BREAK: ("Break starting soon", "Finish your thought — a short eye break is about to begin."),
    State.ON_BREAK: ("On a break", "Look away from the screen and let your eyes rest."),
    State.SNOOZED: ("Snoozed", "Your break was postponed."),
    State.PAUSED: ("Paused", "Reminders are paused."),
    State.MEETING: ("Meeting mode", "Reminders are suspended during your meeting."),
    State.IDLE: ("Away", "No activity detected — the timer is paused."),
    State.SUSPENDED: ("Locked", "The screen is locked — the timer is paused."),
}
MODE_LABEL = {"gentle": "Gentle", "focus": "Focus", "strict": "Strict"}


def describe_break(seconds: int) -> str:
    return f"{seconds} sec" if seconds < 60 else (f"{seconds // 60} min" if seconds % 60 == 0
                                                  else f"{seconds // 60} min {seconds % 60} s")


def build_pause_menu(parent: QWidget, ctx: AppContext) -> QMenu:
    m = ctx.manager
    menu = QMenu(parent)
    menu.addAction("For 30 minutes", lambda: m.pause(30 * 60))
    menu.addAction("For 1 hour", lambda: m.pause(3600))
    menu.addAction("For 2 hours", lambda: m.pause(7200))
    menu.addAction("Until tomorrow", lambda: m.pause(until_tomorrow=True))
    menu.addAction("Until I resume", lambda: m.pause())
    return menu


class OverviewPage(Page):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__("Overview", "Your eye-break rhythm at a glance.")
        self.ctx = ctx
        m = ctx.manager

        hero = Card(padding=SPACE["xxl"])
        row = QHBoxLayout()
        row.setSpacing(36)
        self.ring = ProgressRing(224)
        row.addWidget(self.ring, 0, Qt.AlignmentFlag.AlignVCenter)
        info = QVBoxLayout()
        info.setSpacing(SPACE["sm"])
        self.pill = label("", "pill")
        info.addWidget(self.pill, 0, Qt.AlignmentFlag.AlignLeft)
        self.title = label("", "pageTitle")
        info.addWidget(self.title)
        self.detail = label("", "pageSubtitle", wrap=True)
        info.addWidget(self.detail)
        self.next_at = label("", "caption")
        info.addWidget(self.next_at)
        info.addSpacing(SPACE["md"])
        actions = QHBoxLayout()
        actions.setSpacing(SPACE["sm"])
        self.break_btn = button("Take a break now", "primary", "eye", m.take_break_now)
        self.pause_btn = button("Pause", None, "pause")
        self.pause_menu = build_pause_menu(self, ctx)
        self.pause_btn.clicked.connect(self._on_pause_clicked)
        self.restart_btn = button("Restart session", "ghost", "restart", m.restart_session)
        actions.addWidget(self.break_btn)
        actions.addWidget(self.pause_btn)
        actions.addWidget(self.restart_btn)
        actions.addStretch(1)
        info.addLayout(actions)
        info.addStretch(1)
        row.addLayout(info, 1)
        hero.body.addLayout(row)
        self.add(hero)

        self.t_session = StatTile("Current session")
        self.t_completed = StatTile("Breaks completed")
        self.t_skipped = StatTile("Breaks skipped")
        self.t_break_time = StatTile("Break time")
        self.t_active = StatTile("Active computer time", caption="Detected input, not screen time")
        self.t_rate = StatTile("Completion rate")
        self.add(label("TODAY", "overline"))
        self.add(tile_grid([self.t_session, self.t_completed, self.t_skipped,
                            self.t_break_time, self.t_active, self.t_rate], 3))

        sched = Card()
        head = QHBoxLayout()
        head.addWidget(label("Current schedule", "section"))
        head.addStretch(1)
        head.addWidget(button("Edit schedule", "ghost", None, lambda: ctx.navigate.emit("schedule")))
        sched.body.addLayout(head)
        self.schedule_text = label("", "pageSubtitle", wrap=True)
        sched.body.addWidget(self.schedule_text)
        self.add(sched)
        self.finish()

        m.ticked.connect(self.refresh_live)
        m.state_changed.connect(lambda _s: self.refresh_live())
        m.stats_changed.connect(self.refresh_stats)
        ctx.settings_changed.connect(self.refresh_schedule)
        self.refresh_live()
        self.refresh_stats()
        self.refresh_schedule()

    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        self.refresh_live()
        self.refresh_stats()

    def _on_pause_clicked(self) -> None:
        if self.ctx.manager.state in (State.PAUSED, State.MEETING):
            self.ctx.manager.resume()
        else:
            self.pause_menu.exec(self.pause_btn.mapToGlobal(self.pause_btn.rect().bottomLeft()))

    def refresh_live(self) -> None:
        if not self.isVisible():
            return  # no repaint work while the window is hidden
        m = self.ctx.manager
        sch = m.scheduler
        state = sch.state
        title, detail = STATUS[state]
        held = state in (State.PAUSED, State.MEETING)
        if state == State.ON_BREAK and sch.current_break:
            progress = 1 - sch.break_remaining / max(1, sch.current_break.duration)
            self.ring.set(progress, format_clock(sch.break_remaining), "break remaining")
        else:
            progress = sch.work_elapsed / max(1, sch.config.work_seconds)
            caption = "until next break" if not held else "when resumed"
            self.ring.set(progress, format_clock(sch.remaining), caption,
                          muted=held or state in (State.IDLE, State.SUSPENDED))
        until = sch.hold_until
        if held:
            if sch.hold_is_auto:
                detail = "A full-screen app or presentation is active. Reminders resume when it ends."
            elif until:
                detail = f"{detail[:-1]} until {until:%H:%M}{' tomorrow' if until.date() > datetime.now().date() else ''}."
            else:
                detail = f"{detail[:-1]} until you resume."
        self.title.setText(title)
        self.detail.setText(detail)
        pill_text = {State.ON_BREAK: "Resting", State.PAUSED: "Paused", State.MEETING: "Meeting",
                     State.IDLE: "Away", State.SUSPENDED: "Locked"}.get(state, "Active")
        tone = "muted" if state in (State.PAUSED, State.MEETING, State.IDLE, State.SUSPENDED) else None
        tone = "warning" if state == State.PRE_BREAK else tone
        self.pill.setText(pill_text)
        if self.pill.property("tone") != tone:
            self.pill.setProperty("tone", tone)
            repolish(self.pill)
        if state in (State.WORKING, State.PRE_BREAK, State.SNOOZED):
            eta = datetime.now().timestamp() + sch.remaining
            self.next_at.setText(f"Next eye break at {datetime.fromtimestamp(eta):%H:%M}")
        else:
            self.next_at.setText("")
        self.pause_btn.setText("Resume" if held else "Pause")
        self.pause_btn.setProperty("iconName", "play" if held else "pause")
        refresh_icon(self.pause_btn)
        self.break_btn.setEnabled(state != State.ON_BREAK)
        self.restart_btn.setEnabled(state != State.ON_BREAK)
        self.t_session.set(format_duration(sch.work_elapsed))

    def refresh_stats(self) -> None:
        if not self.isVisible():
            return
        today = self.ctx.stats.summary("today", datetime.now().date())
        self.t_completed.set(str(today.completed))
        self.t_skipped.set(str(today.skipped), f"{today.snoozed} snoozed" if today.snoozed else "")
        self.t_break_time.set(format_duration(today.break_seconds))
        self.t_active.set(format_duration(today.active_seconds + max(0.0, self.ctx.manager.pending_active)))
        self.t_rate.set(format_rate(today.rate), f"Streak: {today.current_streak} day"
                        f"{'' if today.current_streak == 1 else 's'}")

    def refresh_schedule(self) -> None:
        s = self.ctx.s
        parts = [
            f"Every {s.work_minutes} min of active work",
            f"{describe_break(s.break_seconds)} breaks",
            f"{MODE_LABEL[s.mode]} mode",
            f"Pause after {s.idle_threshold_minutes} min idle",
        ]
        if s.notify_before_seconds or s.mode == "gentle":
            parts.append("Heads-up notification on")
        self.schedule_text.setText("  ·  ".join(parts))
