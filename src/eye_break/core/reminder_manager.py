"""Optional secondary health reminders (water, standing, stretching, posture, walking).

Each reminder runs on its own interval of *active* time, independent from the eye-break
timer. They are shown as quiet tray notifications (never overlays), and are coordinated
so they never fire during a break, right before a break, or back-to-back.
"""

from __future__ import annotations

from typing import Any

REMINDER_TEXT: dict[str, tuple[str, str]] = {
    "water": ("Time for some water", "A glass of water is a good idea right now."),
    "stand": ("Stand up for a moment", "Get out of your chair and stand tall for a minute."),
    "stretch": ("Stretch break", "Reach your arms overhead and stretch gently."),
    "posture": ("Posture check", "Sit back, relax your shoulders and keep the screen at eye level."),
    "walk": ("Take a short walk", "A few minutes of walking is a great reset."),
}
REMINDER_LABELS = {"water": "Drink water", "stand": "Stand up", "stretch": "Stretch",
                   "posture": "Posture check", "walk": "Short walk"}
MIN_SPACING_SECONDS = 120.0  # between any two reminders
QUIET_BEFORE_BREAK = 120.0  # no reminders this close to an eye break


class ReminderManager:
    def __init__(self) -> None:
        self.elapsed: dict[str, float] = {k: 0.0 for k in REMINDER_TEXT}
        self._since_last = MIN_SPACING_SECONDS

    def tick(
        self,
        config: dict[str, dict[str, Any]],
        active_delta: float,
        can_interrupt: bool,
        seconds_to_break: float,
    ) -> str | None:
        """Advance timers; return at most one due reminder kind."""
        if active_delta > 0:
            self._since_last += active_delta
            for kind, item in config.items():
                if item.get("enabled") and kind in self.elapsed:
                    self.elapsed[kind] += active_delta
        if not can_interrupt or seconds_to_break < QUIET_BEFORE_BREAK or self._since_last < MIN_SPACING_SECONDS:
            return None
        due = [
            (self.elapsed[k] - item["minutes"] * 60, k)
            for k, item in config.items()
            if item.get("enabled") and k in self.elapsed and self.elapsed[k] >= item["minutes"] * 60
        ]
        if not due:
            return None
        _, kind = max(due)  # the most overdue goes first; others wait for spacing
        self.elapsed[kind] = 0.0
        self._since_last = 0.0
        return kind

    def on_eye_break_completed(self) -> None:
        """A completed eye break also counts as having stood up / looked away."""
        self._since_last = 0.0
        for kind in ("stand", "posture"):
            self.elapsed[kind] = 0.0
