"""Shared state handed to every page: settings, services and live-apply helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PySide6.QtCore import QObject, QTimer, Signal

from eye_break.core.break_manager import BreakManager
from eye_break.services.quote_service import QuoteService
from eye_break.services.settings_service import Settings, SettingsService
from eye_break.services.statistics_service import StatisticsService
from eye_break.ui.themes import ThemeManager


class AppContext(QObject):
    settings_changed = Signal()
    navigate = Signal(str)

    def __init__(self, settings: SettingsService, manager: BreakManager, stats: StatisticsService,
                 quotes: QuoteService, theme: ThemeManager) -> None:
        super().__init__()
        self.settings_service = settings
        self.manager = manager
        self.stats = stats
        self.quotes = quotes
        self.theme = theme
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(300)  # coalesce slider drags into one write
        self._save_timer.timeout.connect(self.settings_service.save)

    @property
    def s(self) -> Settings:
        return self.settings_service.settings

    def update(self, **changes: Any) -> None:
        """Apply changes immediately (no restart needed) and persist shortly after."""
        for key, value in changes.items():
            setattr(self.s, key, value)
        if "theme" in changes or "accent" in changes:
            self.theme.apply(self.s.theme, self.s.accent)
        self.manager.apply_settings()
        self._save_timer.start()
        self.settings_changed.emit()

    def flush(self) -> None:
        if self._save_timer.isActive():
            self._save_timer.stop()
            self.settings_service.save()
