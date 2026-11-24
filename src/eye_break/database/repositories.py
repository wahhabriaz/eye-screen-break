"""Small data-access layer over the history database."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True)
class BreakRecord:
    started_at: datetime
    ended_at: datetime
    planned_seconds: float
    actual_seconds: float
    outcome: str
    trigger: str
    mode: str


class HistoryRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def add_break(self, record: BreakRecord) -> None:
        self.conn.execute(
            "INSERT INTO breaks (started_at, ended_at, day, planned_seconds, actual_seconds,"
            " outcome, trigger, mode) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.started_at.isoformat(timespec="seconds"),
                record.ended_at.isoformat(timespec="seconds"),
                record.started_at.date().isoformat(),
                record.planned_seconds,
                round(record.actual_seconds, 1),
                record.outcome,
                record.trigger,
                record.mode,
            ),
        )

    def add_active_seconds(self, day: date, seconds: float) -> None:
        """Add (or, for idle corrections, subtract) active time; never goes below zero."""
        if seconds > 0:
            self.conn.execute(
                "INSERT INTO activity (day, active_seconds) VALUES (?, ?)"
                " ON CONFLICT(day) DO UPDATE SET active_seconds = active_seconds + excluded.active_seconds",
                (day.isoformat(), seconds),
            )
        elif seconds < 0:
            self.conn.execute(
                "UPDATE activity SET active_seconds = MAX(0, active_seconds + ?) WHERE day = ?",
                (seconds, day.isoformat()),
            )

    def daily_rows(self, start: date | None, end: date) -> list[sqlite3.Row]:
        """Per-day aggregates for [start, end] (start None = all time)."""
        start_iso = start.isoformat() if start else "0000-00-00"
        return self.conn.execute(
            """
            WITH days AS (
                SELECT day FROM breaks WHERE day BETWEEN :s AND :e
                UNION SELECT day FROM activity WHERE day BETWEEN :s AND :e
            )
            SELECT d.day,
                COALESCE(SUM(b.outcome = 'completed'), 0) AS completed,
                COALESCE(SUM(b.outcome = 'skipped'), 0) AS skipped,
                COALESCE(SUM(b.outcome = 'snoozed'), 0) AS snoozed,
                COALESCE(SUM(b.outcome = 'interrupted'), 0) AS interrupted,
                COALESCE(SUM(CASE WHEN b.outcome != 'snoozed' THEN b.actual_seconds END), 0) AS break_seconds,
                COALESCE((SELECT active_seconds FROM activity a WHERE a.day = d.day), 0) AS active_seconds
            FROM days d LEFT JOIN breaks b ON b.day = d.day
            GROUP BY d.day ORDER BY d.day
            """,
            {"s": start_iso, "e": end.isoformat()},
        ).fetchall()

    def all_breaks(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT started_at, ended_at, planned_seconds, actual_seconds, outcome, trigger, mode"
            " FROM breaks ORDER BY started_at"
        ).fetchall()

    def first_day(self) -> date | None:
        row = self.conn.execute(
            "SELECT MIN(day) FROM (SELECT day FROM breaks UNION SELECT day FROM activity)"
        ).fetchone()
        return date.fromisoformat(row[0]) if row and row[0] else None

    def clear(self) -> None:
        self.conn.execute("BEGIN")
        self.conn.execute("DELETE FROM breaks")
        self.conn.execute("DELETE FROM activity")
        self.conn.execute("COMMIT")
        self.conn.execute("VACUUM")

    def get_kv(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return row[0] if row else None

    def set_kv(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
