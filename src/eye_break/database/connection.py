"""SQLite connection with schema migrations and corruption recovery."""

from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from eye_break.database.migrations import migrate

log = logging.getLogger(__name__)


def connect(path: Path | str) -> sqlite3.Connection:
    """Open (and migrate) the history database; a corrupt file is moved aside and recreated."""
    try:
        return _open(path)
    except sqlite3.DatabaseError as exc:
        if str(path) == ":memory:":
            raise
        path = Path(path)
        backup = path.with_name(f"history.corrupt-{datetime.now():%Y%m%d-%H%M%S}.db")
        log.error("History database unreadable (%s); moving to %s", exc, backup)
        os.replace(path, backup)
        for suffix in ("-wal", "-shm"):
            Path(f"{path}{suffix}").unlink(missing_ok=True)
        return _open(path)


def _open(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), isolation_level=None)  # autocommit; explicit transactions
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA quick_check").fetchone()
        migrate(conn)
    except Exception:
        conn.close()  # release the file handle so a corrupt file can be moved aside
        raise
    return conn
