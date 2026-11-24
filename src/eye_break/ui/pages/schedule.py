from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QButtonGroup, QFrame, QHBoxLayout, QLineEdit, QRadioButton, QSpinBox, QVBoxLayout, QWidget

from eye_break.services.settings_service import (
    BREAK_PRESETS,
    MAX_BREAK_SECONDS,
    MAX_WORK_MINUTES,
    MIN_BREAK_SECONDS,
    MIN_WORK_MINUTES,
    WORK_PRESETS,
    validate_break_seconds,
    validate_work_minutes,
)
from eye_break.ui.components import (
    Card,
    Divider,
    Page,
    Segmented,
    SettingRow,
    ToggleSwitch,
    button,
    label,
    repolish,
    section,
)
from eye_break.ui.context import AppContext
from eye_break.ui.themes import SPACE

MODES = [
    ("gentle", "Gentle", "A heads-up notification first. Skip or snooze freely."),
    ("focus", "Focus", "The overlay appears automatically. Limited snoozes; skipping asks for confirmation."),
    ("strict", "Strict", "No skip or snooze buttons. Emergency exit: hold Esc for 3 seconds or use the tray menu."),
]


def spin(value: int, low: int, high: int, suffix: str, on_change) -> QSpinBox:
    box = QSpinBox()
    box.setRange(low, high)
    box.setValue(value)
    box.setSuffix(suffix)
    box.setFixedWidth(96)
    box.setAlignment(Qt.AlignmentFlag.AlignRight)
    box.valueChanged.connect(on_change)
    return box


class CustomInput(QWidget):
    """A validated free-form number entry shown when "Custom" is selected."""

    def __init__(self, placeholder: str, hint: str, validator, on_valid) -> None:
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        row = QHBoxLayout()
        row.setSpacing(SPACE["sm"])
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.setFixedWidth(160)
        self.edit.returnPressed.connect(self._apply)
        apply_btn = button("Apply", None, None, self._apply)
        row.addWidget(self.edit)
        row.addWidget(apply_btn)
        row.addStretch(1)
        lay.addLayout(row)
        self.message = label(hint, "hint")
        self.hint = hint
        lay.addWidget(self.message)
        self.validator, self.on_valid = validator, on_valid
        self.edit.textEdited.connect(self._live_check)

    def _live_check(self, text: str) -> None:
        ok = not text.strip() or self.validator(text) is not None
        self.edit.setProperty("invalid", not ok)
        repolish(self.edit)
        self.message.setProperty("role", "hint" if ok else "error")
        self.message.setText(self.hint if ok else f"Please enter a whole number. {self.hint}")
        repolish(self.message)

    def _apply(self) -> bool:
        value = self.validator(self.edit.text())
        self._live_check(self.edit.text() or "x")
        if value is None:
            return False
        self.message.setProperty("role", "hint")
        self.message.setText(f"Saved. {self.hint}")
        repolish(self.message)
        self.on_valid(value)
        return True


class SchedulePage(Page):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__("Break schedule", "Choose how long you work between breaks and how breaks behave. "
                                           "Changes apply immediately.")
        self.ctx = ctx
        s = ctx.s

        # ---- work interval
        work = Card()
        section(work, "Work interval", "Measured in active computer time; idle and locked periods are not counted.")
        options = [(f"{m} min", m) for m in WORK_PRESETS] + [("Custom", "custom")]
        self.work_seg = Segmented(options, s.work_minutes if s.work_minutes in WORK_PRESETS else "custom")
        self.work_seg.changed.connect(self._on_work_preset)
        work.body.addWidget(self.work_seg)
        work.body.addWidget(label("20 minutes follows the popular 20-20-20 routine: every 20 minutes, look at "
                                  "something 20 feet away for 20 seconds.", "hint", wrap=True))
        self.work_custom = CustomInput(
            f"Minutes ({MIN_WORK_MINUTES}–{MAX_WORK_MINUTES})",
            f"Any interval from {MIN_WORK_MINUTES} to {MAX_WORK_MINUTES} minutes.",
            validate_work_minutes, lambda v: ctx.update(work_minutes=v),
        )
        self.work_custom.edit.setText(str(s.work_minutes))
        self.work_custom.setVisible(s.work_minutes not in WORK_PRESETS)
        work.body.addWidget(self.work_custom)
        self.add(work)

        # ---- break duration
        brk = Card()
        section(brk, "Break duration")
        names = {20: "20 s", 30: "30 s", 60: "1 min", 120: "2 min", 180: "3 min", 300: "5 min", 600: "10 min"}
        options = [(names[b], b) for b in BREAK_PRESETS] + [("Custom", "custom")]
        self.break_seg = Segmented(options, s.break_seconds if s.break_seconds in BREAK_PRESETS else "custom")
        self.break_seg.changed.connect(self._on_break_preset)
        brk.body.addWidget(self.break_seg)
        self.break_custom = CustomInput(
            f"Seconds ({MIN_BREAK_SECONDS}–{MAX_BREAK_SECONDS})",
            f"Any duration from {MIN_BREAK_SECONDS} seconds to {MAX_BREAK_SECONDS // 60} minutes, in seconds.",
            validate_break_seconds, lambda v: ctx.update(break_seconds=v),
        )
        self.break_custom.edit.setText(str(s.break_seconds))
        self.break_custom.setVisible(s.break_seconds not in BREAK_PRESETS)
        brk.body.addWidget(self.break_custom)
        self.add(brk)

        # ---- mode
        mode = Card()
        section(mode, "Break mode")
        self.mode_group = QButtonGroup(self)
        for key, title, desc in MODES:
            opt = QFrame()
            lay = QHBoxLayout(opt)
            lay.setContentsMargins(0, 4, 0, 4)
            radio = QRadioButton(title)
            radio.setChecked(s.mode == key)
            radio.setProperty("mode", key)
            radio.setCursor(Qt.CursorShape.PointingHandCursor)
            radio.setMinimumWidth(90)
            self.mode_group.addButton(radio)
            lay.addWidget(radio, 0, Qt.AlignmentFlag.AlignTop)
            lay.addWidget(label(desc, "caption", wrap=True), 1)
            mode.body.addWidget(opt)
        self.mode_group.buttonClicked.connect(lambda b: self._on_mode(b.property("mode")))
        mode.body.addWidget(Divider())
        mode.body.addWidget(SettingRow("Snooze length", "How long a snooze postpones a break.",
                                       spin(s.snooze_minutes, 1, 60, " min",
                                            lambda v: ctx.update(snooze_minutes=v))))
        self.snooze_limit = SettingRow("Focus mode snooze limit", "Snoozes allowed per break in Focus mode.",
                                       spin(s.max_snoozes, 0, 10, "", lambda v: ctx.update(max_snoozes=v)))
        mode.body.addWidget(self.snooze_limit)
        self.add(mode)

        # ---- idle
        idle = Card()
        section(idle, "Idle detection", "Uses only the time of your last keyboard or mouse input — never what "
                                        "you type. Detected activity is not the same as time spent looking at the screen.")
        idle.body.addWidget(SettingRow("Pause the timer after", "No keyboard or mouse input for this long.",
                                       spin(s.idle_threshold_minutes, 1, 60, " min",
                                            lambda v: ctx.update(idle_threshold_minutes=v))))
        self.reset_toggle = ToggleSwitch(s.idle_reset_enabled, "Restart session after a long absence")
        self.reset_toggle.toggled.connect(lambda v: ctx.update(idle_reset_enabled=v))
        idle.body.addWidget(SettingRow("Restart the session after a long absence",
                                       "Time away from the computer counts as a break.", self.reset_toggle))
        self.reset_minutes = spin(s.idle_reset_minutes, 1, 240, " min",
                                  lambda v: ctx.update(idle_reset_minutes=max(v, ctx.s.idle_threshold_minutes)))
        idle.body.addWidget(SettingRow("Absence needed to restart", "Must be at least the idle threshold.",
                                       self.reset_minutes))
        self.add(idle)

        # ---- meetings
        meet = Card()
        section(meet, "Meetings and presentations")
        auto = ToggleSwitch(s.auto_meeting_detection, "Pause during full-screen apps")
        auto.toggled.connect(lambda v: ctx.update(auto_meeting_detection=v))
        meet.body.addWidget(SettingRow(
            "Pause during full-screen apps and presentations",
            "Uses the Windows notification state (full-screen apps, games, presentation mode). It does not "
            "detect windowed video calls — use Meeting mode from the tray menu for those.", auto))
        self.add(meet)
        self.finish()

        self._sync_mode_rows()

    def _on_work_preset(self, value) -> None:
        self.work_custom.setVisible(value == "custom")
        if value != "custom":
            self.ctx.update(work_minutes=value)
        else:
            self.work_custom.edit.setFocus()

    def _on_break_preset(self, value) -> None:
        self.break_custom.setVisible(value == "custom")
        if value != "custom":
            self.ctx.update(break_seconds=value)
        else:
            self.break_custom.edit.setFocus()

    def _on_mode(self, mode: str) -> None:
        self.ctx.update(mode=mode)
        self._sync_mode_rows()

    def _sync_mode_rows(self) -> None:
        self.snooze_limit.setEnabled(self.ctx.s.mode == "focus")
