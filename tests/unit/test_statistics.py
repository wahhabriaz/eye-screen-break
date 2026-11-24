import csv
from datetime import date, datetime, timedelta

import pytest

from eye_break.database.connection import connect
from eye_break.database.repositories import BreakRecord, HistoryRepository
from eye_break.services.statistics_service import DayStats, StatisticsService, compute_streaks

TODAY = date(2026, 3, 15)


@pytest.fixture()
def stats():
    conn = connect(":memory:")
    return StatisticsService(HistoryRepository(conn))


def add(stats, day: date, outcome: str, actual: float = 30, hour: int = 10):
    start = datetime.combine(day, datetime.min.time()).replace(hour=hour)
    stats.record_break(BreakRecord(start, start + timedelta(seconds=actual), 30, actual,
                                   outcome, "scheduled", "gentle"))


def test_today_summary(stats):
    add(stats, TODAY, "completed")
    add(stats, TODAY, "completed", hour=11)
    add(stats, TODAY, "skipped", actual=5, hour=12)
    add(stats, TODAY, "snoozed", actual=2, hour=13)
    stats.add_active_seconds(datetime(2026, 3, 15, 10), 3600)
    stats.add_active_seconds(datetime(2026, 3, 15, 11), 1800)
    s = stats.summary("today", TODAY)
    assert (s.completed, s.skipped, s.snoozed, s.interrupted) == (2, 1, 1, 0)
    assert s.rate == pytest.approx(2 / 3)
    assert s.break_seconds == pytest.approx(65)  # snoozes excluded
    assert s.active_seconds == pytest.approx(5400)


def test_negative_active_correction_clamped(stats):
    stats.add_active_seconds(datetime(2026, 3, 15, 10), 100)
    stats.add_active_seconds(datetime(2026, 3, 15, 10), -300)
    assert stats.summary("today", TODAY).active_seconds == 0


def test_periods_fill_missing_days(stats):
    add(stats, TODAY - timedelta(days=3), "completed")
    add(stats, TODAY - timedelta(days=40), "completed")
    week = stats.summary("7d", TODAY)
    assert len(week.days) == 7 and week.completed == 1
    assert len(stats.summary("30d", TODAY).days) == 30
    month = stats.summary("month", TODAY)
    assert month.days[0].day == date(2026, 3, 1) and len(month.days) == 15
    assert stats.summary("all", TODAY).completed == 2


def test_empty_history(stats):
    s = stats.summary("all", TODAY)
    assert s.days == [] and s.rate is None and s.current_streak == 0


def test_streaks():
    def day(offset, completed, skipped=0):
        return DayStats(TODAY - timedelta(days=offset), completed=completed, skipped=skipped)

    days = [day(6, 5), day(5, 5), day(4, 1, 3), day(3, 4), day(2, 4, 1), day(1, 5), day(0, 0, 2)]
    current, longest = compute_streaks(days, TODAY)
    # today (in progress, failing) does not break yesterday's streak of 3
    assert current == 3
    assert longest == 3


def test_neutral_days_do_not_break_streak():
    days = [DayStats(TODAY - timedelta(days=2), completed=3), DayStats(TODAY - timedelta(days=1)),
            DayStats(TODAY, completed=2)]
    assert compute_streaks(days, TODAY) == (2, 2)


def test_streak_from_database(stats):
    for offset in range(4):
        add(stats, TODAY - timedelta(days=offset), "completed")
    assert stats.summary("today", TODAY).current_streak == 4


def test_export_and_clear(stats, tmp_path):
    add(stats, TODAY, "completed")
    add(stats, TODAY, "interrupted", actual=10, hour=12)
    path = tmp_path / "out.csv"
    assert stats.export_csv(path) == 2
    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert rows[0][4] == "outcome" and rows[2][4] == "interrupted"
    stats.clear()
    assert stats.summary("all", TODAY).completed == 0


def test_migration_and_corrupt_db_recovery(tmp_path):
    path = tmp_path / "history.db"
    conn = connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    conn.close()
    path.write_bytes(b"this is not a database" * 100)
    conn = connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    assert list(tmp_path.glob("history.corrupt-*.db"))
    conn.close()
