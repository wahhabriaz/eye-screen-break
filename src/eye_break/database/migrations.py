"""Ordered, idempotent schema migrations tracked with PRAGMA user_version."""

from __future__ import annotations

import sqlite3

MIGRATIONS: list[str] = [
    # 1: initial schema
    """
    CREATE TABLE breaks (
        id INTEGER PRIMARY KEY,
        started_at TEXT NOT NULL,
        ended_at TEXT NOT NULL,
        day TEXT NOT NULL,
        planned_seconds REAL NOT NULL,
        actual_seconds REAL NOT NULL,
        outcome TEXT NOT NULL CHECK (outcome IN ('completed','skipped','snoozed','interrupted')),
        trigger TEXT NOT NULL,
        mode TEXT NOT NULL
    );
    CREATE INDEX idx_breaks_day ON breaks(day);
    CREATE TABLE activity (
        day TEXT PRIMARY KEY,
        active_seconds REAL NOT NULL DEFAULT 0
    );
    CREATE TABLE kv (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    """,
]


def migrate(conn: sqlite3.Connection) -> int:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for index in range(version, len(MIGRATIONS)):
        conn.execute("BEGIN")
        try:
            for statement in MIGRATIONS[index].split(";"):
                if statement.strip():
                    conn.execute(statement)
            conn.execute(f"PRAGMA user_version = {index + 1}")
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return len(MIGRATIONS)
