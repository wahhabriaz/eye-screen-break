"""User preferences: validated, persisted atomically as JSON, recovered on corruption."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

WORK_PRESETS = [20, 30, 45, 60, 90, 120]
BREAK_PRESETS = [20, 30, 60, 120, 180, 300, 600]
NOTIFY_OPTIONS = [0, 10, 30, 60, 120]
MODES = ("gentle", "focus", "strict")
THEMES = ("system", "light", "dark")
ACCENTS = ("teal", "green", "blue", "violet", "amber", "rose")
MONITOR_OPTIONS = ("all", "primary", "cursor")
QUOTE_CATEGORIES = ("eyes", "breaks", "habits", "rest", "balance", "productivity", "wellbeing")
REMINDER_KINDS = ("water", "stand", "stretch", "posture", "walk")

MIN_WORK_MINUTES, MAX_WORK_MINUTES = 1, 180
MIN_BREAK_SECONDS, MAX_BREAK_SECONDS = 10, 3600
MAX_CUSTOM_QUOTE_LENGTH = 240


def _default_reminders() -> dict[str, dict[str, Any]]:
    minutes = {"water": 60, "stand": 45, "stretch": 60, "posture": 30, "walk": 90}
    return {kind: {"enabled": False, "minutes": minutes[kind]} for kind in REMINDER_KINDS}


@dataclass
class Settings:
    work_minutes: int = 30
    break_seconds: int = 30
    mode: str = "gentle"
    snooze_minutes: int = 5
    max_snoozes: int = 2  # focus mode limit per break
    idle_threshold_minutes: int = 5
    idle_reset_enabled: bool = True
    idle_reset_minutes: int = 5
    notify_before_seconds: int = 30
    sound_pre_break: bool = False
    sound_break_start: bool = False
    sound_break_end: bool = False
    theme: str = "system"
    accent: str = "teal"
    overlay_opacity: int = 80
    overlay_font_scale: int = 100
    countdown_size: int = 96
    show_quotes: bool = True
    show_instructions: bool = True
    show_progress: bool = True
    fade_ms: int = 400
    overlay_monitor: str = "all"
    quote_categories: list[str] = field(default_factory=lambda: list(QUOTE_CATEGORIES))
    custom_quotes: list[str] = field(default_factory=list)
    start_with_windows: bool = False
    start_minimized: bool = True
    auto_meeting_detection: bool = False
    reminders: dict[str, dict[str, Any]] = field(default_factory=_default_reminders)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Any) -> Settings:
        """Build settings from untrusted data; every invalid field falls back to its default."""
        defaults = cls()
        if not isinstance(raw, dict):
            return defaults
        values: dict[str, Any] = {}
        for f in fields(cls):
            default = getattr(defaults, f.name)
            value = raw.get(f.name, default)
            values[f.name] = _validate(f.name, value, default)
        result = cls(**values)
        if result.idle_reset_minutes < result.idle_threshold_minutes:
            result.idle_reset_minutes = result.idle_threshold_minutes
        return result


def _int_in(value: Any, low: int, high: int, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    value = int(value)
    return value if low <= value <= high else default


def _validate(name: str, value: Any, default: Any) -> Any:
    ranges = {
        "work_minutes": (MIN_WORK_MINUTES, MAX_WORK_MINUTES),
        "break_seconds": (MIN_BREAK_SECONDS, MAX_BREAK_SECONDS),
        "snooze_minutes": (1, 60),
        "max_snoozes": (0, 10),
        "idle_threshold_minutes": (1, 60),
        "idle_reset_minutes": (1, 240),
        "overlay_opacity": (50, 100),
        "overlay_font_scale": (80, 150),
        "countdown_size": (48, 180),
        "fade_ms": (0, 2000),
    }
    choices = {
        "mode": MODES,
        "theme": THEMES,
        "accent": ACCENTS,
        "overlay_monitor": MONITOR_OPTIONS,
        "notify_before_seconds": NOTIFY_OPTIONS,
    }
    if name in ranges:
        return _int_in(value, *ranges[name], default)
    if name in choices:
        return value if value in choices[name] else default
    if isinstance(default, bool):
        return value if isinstance(value, bool) else default
    if name == "quote_categories":
        if not isinstance(value, list):
            return default
        return [c for c in QUOTE_CATEGORIES if c in value]
    if name == "custom_quotes":
        if not isinstance(value, list):
            return default
        cleaned = [str(q).strip()[:MAX_CUSTOM_QUOTE_LENGTH] for q in value if isinstance(q, str)]
        return list(dict.fromkeys(q for q in cleaned if q))
    if name == "reminders":
        result = _default_reminders()
        if isinstance(value, dict):
            for kind in REMINDER_KINDS:
                item = value.get(kind)
                if isinstance(item, dict):
                    enabled = item.get("enabled")
                    result[kind]["enabled"] = enabled if isinstance(enabled, bool) else False
                    result[kind]["minutes"] = _int_in(item.get("minutes"), 5, 240, result[kind]["minutes"])
        return result
    return default


def validate_work_minutes(text: str) -> int | None:
    """Parse a user-entered custom interval; None when invalid."""
    try:
        value = int(text.strip())
    except (ValueError, AttributeError):
        return None
    return value if MIN_WORK_MINUTES <= value <= MAX_WORK_MINUTES else None


def validate_break_seconds(text: str) -> int | None:
    try:
        value = int(text.strip())
    except (ValueError, AttributeError):
        return None
    return value if MIN_BREAK_SECONDS <= value <= MAX_BREAK_SECONDS else None


class SettingsService:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.settings = self.load()

    def load(self) -> Settings:
        if not self.path.exists():
            return Settings()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            backup = self.path.with_name(f"settings.corrupt-{datetime.now():%Y%m%d-%H%M%S}.json")
            log.warning("Settings file unreadable (%s); backing up to %s and using defaults", exc, backup)
            try:
                os.replace(self.path, backup)
            except OSError:
                log.exception("Could not back up corrupt settings")
            return Settings()
        return Settings.from_dict(raw)

    def save(self) -> None:
        self.settings = Settings.from_dict(self.settings.to_dict())
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.settings.to_dict(), indent=2), encoding="utf-8")
        os.replace(tmp, self.path)
