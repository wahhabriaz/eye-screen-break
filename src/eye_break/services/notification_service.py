"""Native tray notifications and optional subtle sounds."""

from __future__ import annotations

from PySide6.QtWidgets import QSystemTrayIcon

from eye_break.platform.windows import play_sound
from eye_break.utils.paths import assets_dir


class NotificationService:
    def __init__(self) -> None:
        self.tray: QSystemTrayIcon | None = None

    def notify(self, title: str, message: str, seconds: int = 6) -> None:
        if self.tray and self.tray.isVisible() and QSystemTrayIcon.supportsMessages():
            self.tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, seconds * 1000)

    def sound(self, name: str) -> None:
        """name: pre_break | break_start | break_end"""
        path = assets_dir() / "sounds" / f"{name}.wav"
        if path.exists():
            play_sound(str(path))
