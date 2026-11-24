"""Per-user "start with Windows" via HKCU\\...\\Run (no administrator rights needed).

Only the single value named `EyeBreak` is ever written or removed.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from eye_break import APP_ID
from eye_break.platform.windows import IS_WINDOWS

log = logging.getLogger(__name__)
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    main = Path(__file__).resolve().parents[4] / "main.py"
    return f'"{pythonw if pythonw.exists() else exe}" "{main}" --minimized'


def is_enabled(value_name: str = APP_ID) -> bool:
    if not IS_WINDOWS:
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, value_name)
            return True
    except FileNotFoundError:
        return False


def set_enabled(enabled: bool, value_name: str = APP_ID) -> bool:
    """Returns True on success."""
    if not IS_WINDOWS:
        return False
    import winreg

    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, launch_command())
            else:
                try:
                    winreg.DeleteValue(key, value_name)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        log.exception("Could not update startup registration")
        return False
