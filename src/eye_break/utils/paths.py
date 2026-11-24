"""Per-user data locations. Mutable data never lives next to the executable."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from eye_break import APP_ID

_override: Path | None = None


def set_data_dir(path: str | Path | None) -> None:
    """Override the data directory (used by tests and `--data-dir`)."""
    global _override
    _override = Path(path) if path else None


def data_dir() -> Path:
    if _override is not None:
        base = _override
    else:
        root = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        base = Path(root) / APP_ID
    base.mkdir(parents=True, exist_ok=True)
    return base


def settings_file() -> Path:
    return data_dir() / "settings.json"


def database_file() -> Path:
    return data_dir() / "history.db"


def log_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def assets_dir() -> Path:
    """Bundled read-only assets (works from source and from a PyInstaller build)."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root) / "eye_break" / "assets"
    return Path(__file__).resolve().parent.parent / "assets"
