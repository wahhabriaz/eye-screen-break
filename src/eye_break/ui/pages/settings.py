from __future__ import annotations

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QMessageBox, QWidget

from eye_break.core.reminder_manager import REMINDER_LABELS, REMINDER_TEXT
from eye_break.platform.windows import IS_WINDOWS, startup
from eye_break.services.settings_service import REMINDER_KINDS, Settings
from eye_break.ui.components import Card, Divider, Page, Segmented, SettingRow, ToggleSwitch, button, label, section
from eye_break.ui.context import AppContext
from eye_break.ui.pages.schedule import spin
from eye_break.utils.paths import data_dir


class SettingsPage(Page):
    def __init__(self, ctx: AppContext) -> None:
        super().__init__("Settings", "Startup, notifications, sounds and optional health reminders.")
        self.ctx = ctx
        s = ctx.s

        gen = Card()
        section(gen, "General")
        self.startup_toggle = ToggleSwitch(startup.is_enabled(), "Start with Windows")
        self.startup_toggle.setEnabled(IS_WINDOWS)
        self.startup_toggle.toggled.connect(self._on_startup)
        gen.body.addWidget(SettingRow("Start with Windows",
                                      "Launch Eye Break when you sign in. Per-user; no administrator rights needed.",
                                      self.startup_toggle))
        mini = ToggleSwitch(s.start_minimized, "Start minimised to tray")
        mini.toggled.connect(lambda v: ctx.update(start_minimized=v))
        gen.body.addWidget(SettingRow("Start minimised to the tray", "Only the tray icon appears at launch.", mini))
        self.add(gen)

        notif = Card()
        section(notif, "Notifications")
        seg = Segmented([("Off", 0), ("10 s", 10), ("30 s", 30), ("1 min", 60), ("2 min", 120)],
                        s.notify_before_seconds)
        seg.changed.connect(lambda v: ctx.update(notify_before_seconds=v))
        self.notify_row = SettingRow("Heads-up before a break", "", seg)
        notif.body.addWidget(self.notify_row)
        notif.body.addWidget(Divider())
        notif.body.addWidget(label("Sounds are soft chimes and are off by default.", "caption"))
        for key, title in (("sound_pre_break", "Sound before a break"), ("sound_break_start", "Sound when a break starts"),
                           ("sound_break_end", "Sound when a break ends")):
            tg = ToggleSwitch(getattr(s, key), title)
            tg.toggled.connect(lambda v, k=key: ctx.update(**{k: v}))
            notif.body.addWidget(SettingRow(title, "", tg))
        test = QWidget()
        trow = QHBoxLayout(test)
        trow.setContentsMargins(0, 0, 0, 0)
        for name, text in (("pre_break", "Heads-up"), ("break_start", "Start"), ("break_end", "End")):
            trow.addWidget(button(text, "ghost", "play", lambda n=name: ctx.manager.notifier.sound(n)))
        trow.addStretch(1)
        notif.body.addWidget(SettingRow("Preview sounds", "", test))
        self.add(notif)

        rem = Card()
        section(rem, "Health reminders", "Optional quiet notifications on their own timers (active time only). "
                                         "They never appear during or right before an eye break.")
        for kind in REMINDER_KINDS:
            item = s.reminders[kind]
            holder = QWidget()
            row = QHBoxLayout(holder)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(12)
            minutes = spin(item["minutes"], 5, 240, " min", lambda v, k=kind: self._set_reminder(k, minutes=v))
            tg = ToggleSwitch(item["enabled"], REMINDER_LABELS[kind])
            tg.toggled.connect(lambda v, k=kind: self._set_reminder(k, enabled=v))
            row.addWidget(minutes)
            row.addWidget(tg)
            rem.body.addWidget(SettingRow(REMINDER_LABELS[kind], REMINDER_TEXT[kind][1], holder))
        self.add(rem)

        data = Card()
        section(data, "Data and privacy")
        data.body.addWidget(label("Eye Break works entirely offline: no accounts, telemetry, analytics or network "
                                  "requests. It never captures keystrokes, screenshots or window contents.",
                                  "caption", wrap=True))
        path = str(data_dir())
        data.body.addWidget(SettingRow("Data folder", path,
                                       button("Open folder", None, None,
                                              lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(path)))))
        data.body.addWidget(SettingRow("Reset preferences", "Restore every setting to its default. History is kept.",
                                       button("Reset", "danger", None, self._reset)))
        self.add(data)
        self.finish()
        ctx.settings_changed.connect(self._sync)
        self._sync()

    def _sync(self) -> None:
        gentle = self.ctx.s.mode == "gentle" and self.ctx.s.notify_before_seconds == 0
        desc = ("Gentle mode always shows a 30-second heads-up." if gentle
                else "A notification before the overlay appears.")
        self.notify_row.description.setText(desc)
        self.notify_row.description.show()

    def _set_reminder(self, kind: str, **changes) -> None:
        reminders = {k: dict(v) for k, v in self.ctx.s.reminders.items()}
        reminders[kind].update(changes)
        self.ctx.update(reminders=reminders)

    def _on_startup(self, enabled: bool) -> None:
        if startup.set_enabled(enabled):
            self.ctx.update(start_with_windows=enabled)
        else:
            self.startup_toggle.blockSignals(True)
            self.startup_toggle.setChecked(startup.is_enabled())
            self.startup_toggle.blockSignals(False)
            QMessageBox.warning(self, "Startup", "Could not update the Windows startup setting.")

    def _reset(self) -> None:
        answer = QMessageBox.question(
            self, "Reset preferences", "Restore all preferences to their defaults?",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.Cancel)
        if answer != QMessageBox.StandardButton.Yes:
            return
        keep_startup = startup.is_enabled()
        defaults = Settings(start_with_windows=keep_startup)
        self.ctx.update(**defaults.to_dict())
        self.ctx.flush()
        self.ctx.navigate.emit("__rebuild__")
