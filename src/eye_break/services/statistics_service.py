"""Break history recording, aggregation, streaks and CSV export."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from eye_break.database.repositories import BreakRecord, HistoryRepository

PERIODS = {"today": "Today", "7d": "Last 7 days", "30d": "Last 30 days", "month": "This month", "all": "All time"}
STREAK_MIN_RATE = 0.8  # a day counts toward a streak when >= 80% of its breaks were completed


@dataclass
class DayStats:
    day: date
    completed: int = 0
    skipped: int = 0
    snoozed: int = 0
    interrupted: int = 0
    break_seconds: float = 0.0
    active_seconds: float = 0.0

    @property
    def finished(self) -> int:
        return self.completed + self.skipped + self.interrupted

    @property
    def rate(self) -> float | None:
        return self.completed / self.finished if self.finished else None


@dataclass
class Summary:
    period: str
    days: list[DayStats] = field(default_factory=list)
    current_streak: int = 0
    longest_streak: int = 0

    def _sum(self, attr: str) -> float:
        return sum(getattr(d, attr) for d in self.days)

    @property
    def completed(self) -> int:
        return int(self._sum("completed"))

    @property
    def skipped(self) -> int:
        return int(self._sum("skipped"))

    @property
    def snoozed(self) -> int:
        return int(self._sum("snoozed"))

    @property
    def interrupted(self) -> int:
        return int(self._sum("interrupted"))

    @property
    def break_seconds(self) -> float:
        return self._sum("break_seconds")

    @property
    def active_seconds(self) -> float:
        return self._sum("active_seconds")

    @property
    def rate(self) -> float | None:
        finished = self.completed + self.skipped + self.interrupted
        return self.completed / finished if finished else None


def period_start(period: str, today: date, first_day: date | None) -> date | None:
    if period == "today":
        return today
    if period == "7d":
        return today - timedelta(days=6)
    if period == "30d":
        return today - timedelta(days=29)
    if period == "month":
        return today.replace(day=1)
    return first_day


def compute_streaks(days: list[DayStats], today: date) -> tuple[int, int]:
    """Days without any finished break are neutral; a day below the threshold breaks the streak."""
    judged = [(d.day, d.rate >= STREAK_MIN_RATE) for d in days if d.rate is not None]
    longest = run = 0
    for _, ok in judged:
        run = run + 1 if ok else 0
        longest = max(longest, run)
    current = 0
    for day, ok in reversed(judged):
        if day > today:
            continue
        if not ok:
            if day == today and current == 0:
                continue  # today is still in progress; do not break yesterday's streak
            break
        current += 1
    return current, longest


class StatisticsService:
    def __init__(self, repo: HistoryRepository) -> None:
        self.repo = repo

    def record_break(self, record: BreakRecord) -> None:
        self.repo.add_break(record)

    def add_active_seconds(self, when: datetime, seconds: float) -> None:
        self.repo.add_active_seconds(when.date(), seconds)

    def summary(self, period: str, today: date) -> Summary:
        first = self.repo.first_day()
        start = period_start(period, today, first)
        rows = self.repo.daily_rows(start, today)
        by_day = {r["day"]: r for r in rows}
        days: list[DayStats] = []
        if start is not None:
            current = start
            while current <= today:  # fill gaps so charts have continuous axes
                row = by_day.get(current.isoformat())
                days.append(_to_day(current, row))
                current += timedelta(days=1)
        all_rows = self.repo.daily_rows(None, today)
        streak_days = [_to_day(date.fromisoformat(r["day"]), r) for r in all_rows]
        current_streak, longest = compute_streaks(streak_days, today)
        return Summary(period, days, current_streak, longest)

    def export_csv(self, path: Path) -> int:
        rows = self.repo.all_breaks()
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["started_at", "ended_at", "planned_seconds", "actual_seconds",
                             "outcome", "trigger", "mode"])
            for r in rows:
                writer.writerow([r[k] for k in r.keys()])
        return len(rows)

    def clear(self) -> None:
        self.repo.clear()


def _to_day(day: date, row) -> DayStats:
    if row is None:
        return DayStats(day)
    return DayStats(
        day=day,
        completed=int(row["completed"]),
        skipped=int(row["skipped"]),
        snoozed=int(row["snoozed"]),
        interrupted=int(row["interrupted"]),
        break_seconds=float(row["break_seconds"]),
        active_seconds=float(row["active_seconds"]),
    )
