from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import QInputDialog, QMenu, QSystemTrayIcon

from eye_break import APP_NAME
from eye_break.core.scheduler import State
from eye_break.ui import icons
from eye_break.ui.context import AppContext
from eye_break.ui.overlay import format_clock


class SystemTray(QSystemTrayIcon):
    def __init__(self, ctx: AppContext, open_dashboard: Callable[[str], None], quit_app: Callable[[], None]) -> None:
        super().__init__(icons.app_icon())
        self.ctx = ctx
        m = ctx.manager
        self._icon_paused = icons.app_icon(paused=True)
        self._icon_active = icons.app_icon()
        self._last_tooltip = ""
        self._paused_icon = False

        menu = QMenu()  # owned by self.menu below
        menu.addAction("Open dashboard", lambda: open_dashboard("overview"))
        self.status_action = menu.addAction("")
        self.status_action.setEnabled(False)
        menu.addSeparator()
        self.break_action = menu.addAction("Take a break now", m.take_break_now)
        self.snooze_action = menu.addAction("Snooze for 5 minutes", m.snooze)
        self.end_action = menu.addAction("End break now (emergency)", m.emergency_dismiss)
        menu.addSeparator()
        self.pause_action = menu.addAction("Pause reminders", lambda: m.pause())
        self.resume_action = menu.addAction("Resume reminders", m.resume)
        # keep references: otherwise PySide may garbage-collect the submenus
        self.pause_for_menu = pause_for = menu.addMenu("Pause for")
        pause_for.addAction("30 minutes", lambda: m.pause(30 * 60))
        pause_for.addAction("1 hour", lambda: m.pause(3600))
        pause_for.addAction("2 hours", lambda: m.pause(7200))
        pause_for.addAction("Until tomorrow", lambda: m.pause(until_tomorrow=True))
        self.meeting_menu = meeting = menu.addMenu("Meeting mode")
        for text, seconds in (("15 minutes", 900), ("30 minutes", 1800), ("1 hour", 3600), ("2 hours", 7200)):
            meeting.addAction(text, lambda s=seconds: m.pause(s, meeting=True))
        meeting.addAction("Custom duration…", self._custom_meeting)
        meeting.addAction("Until I resume", lambda: m.pause(meeting=True))
        menu.addSeparator()
        menu.addAction("Settings", lambda: open_dashboard("settings"))
        menu.addAction(f"Exit {APP_NAME}", quit_app)
        menu.aboutToShow.connect(self.refresh)
        self.menu = menu
        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)
        self._open = open_dashboard
        m.ticked.connect(self._refresh_tooltip)
        m.state_changed.connect(lambda _s: self.refresh())
        ctx.settings_changed.connect(self.refresh)
        self.refresh()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self._open("overview")

    def _custom_meeting(self) -> None:
        minutes, ok = QInputDialog.getInt(None, "Meeting mode", "Pause reminders for how many minutes?", 45, 1, 600)
        if ok:
            self.ctx.manager.pause(minutes * 60, meeting=True)

    def status_text(self) -> str:
        sch = self.ctx.manager.scheduler
        state = sch.state
        if state == State.ON_BREAK:
            return f"On a break — {format_clock(sch.break_remaining)} left"
        if state in (State.PAUSED, State.MEETING):
            label = "Meeting mode" if state == State.MEETING else "Paused"
            if sch.hold_is_auto:
                return "Paused while a full-screen app is active"
            until = sch.hold_until
            return f"{label} until {until:%H:%M}" if until else f"{label} until resumed"
        if state in (State.IDLE, State.SUSPENDED):
            return f"Timer paused (away) — {format_clock(sch.remaining)} left"
        minutes = int(sch.remaining // 60)
        return f"Next break in {format_clock(sch.remaining)}" if minutes < 1 else f"Next break in {minutes + 1} min"

    def refresh(self) -> None:
        m = self.ctx.manager
        sch = m.scheduler
        state = sch.state
        on_break = state == State.ON_BREAK
        held = state in (State.PAUSED, State.MEETING)
        self.status_action.setText(self.status_text())
        self.break_action.setEnabled(not on_break)
        self.snooze_action.setEnabled((on_break and sch.can_snooze()) or (not on_break and not held))
        self.end_action.setVisible(on_break and self.ctx.s.mode == "strict")
        self.pause_action.setEnabled(not held)
        self.resume_action.setEnabled(held)
        self.snooze_action.setText(f"Snooze for {self.ctx.s.snooze_minutes} minutes")
        paused = held
        if paused != self._paused_icon:
            self._paused_icon = paused
            self.setIcon(self._icon_paused if paused else self._icon_active)
        self._refresh_tooltip()

    def _refresh_tooltip(self) -> None:
        text = f"{APP_NAME} — {self.status_text()}"
        if text != self._last_tooltip:
            self._last_tooltip = text
            self.setToolTip(text)
        if self.menu.isVisible():
            self.status_action.setText(self.status_text())
