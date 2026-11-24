"""Thin ctypes/winreg wrappers. Every function degrades to a harmless default off Windows.

Nothing here reads keystrokes, window contents or screenshots: idle detection only asks
Windows *when* the last input happened.
"""

from __future__ import annotations

import logging
import sys

log = logging.getLogger(__name__)
IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _shell32 = ctypes.WinDLL("shell32", use_last_error=True)

    class _LASTINPUTINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

    _user32.GetLastInputInfo.argtypes = [ctypes.POINTER(_LASTINPUTINFO)]
    _user32.GetLastInputInfo.restype = wintypes.BOOL
    _kernel32.GetTickCount.restype = wintypes.DWORD
    _user32.OpenInputDesktop.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    _user32.OpenInputDesktop.restype = wintypes.HANDLE
    _user32.CloseDesktop.argtypes = [wintypes.HANDLE]
    _user32.GetUserObjectInformationW.argtypes = [
        wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD)
    ]
    _shell32.SHQueryUserNotificationState.argtypes = [ctypes.POINTER(ctypes.c_int)]

_DESKTOP_SWITCHDESKTOP = 0x0100
_UOI_NAME = 2
# QUNS_BUSY (full-screen app), QUNS_RUNNING_D3D_FULL_SCREEN, QUNS_PRESENTATION_MODE
_PRESENTING_STATES = {2, 3, 4}


def idle_seconds() -> float:
    """Seconds since the last keyboard/mouse input in this session."""
    if not IS_WINDOWS:
        return 0.0
    info = _LASTINPUTINFO(ctypes.sizeof(_LASTINPUTINFO), 0)
    if not _user32.GetLastInputInfo(ctypes.byref(info)):
        return 0.0
    return ((_kernel32.GetTickCount() - info.dwTime) & 0xFFFFFFFF) / 1000.0


def is_session_locked() -> bool:
    """True when the input desktop is not the user's default desktop (lock screen, secure desktop)."""
    if not IS_WINDOWS:
        return False
    handle = _user32.OpenInputDesktop(0, False, _DESKTOP_SWITCHDESKTOP)
    if not handle:
        return True
    try:
        buf = ctypes.create_unicode_buffer(256)
        needed = wintypes.DWORD()
        if not _user32.GetUserObjectInformationW(handle, _UOI_NAME, buf, ctypes.sizeof(buf), ctypes.byref(needed)):
            return False
        return buf.value.lower() != "default"
    finally:
        _user32.CloseDesktop(handle)


def is_presenting() -> bool:
    """True while Windows reports a full-screen app, D3D game or presentation mode."""
    if not IS_WINDOWS:
        return False
    state = ctypes.c_int(0)
    if _shell32.SHQueryUserNotificationState(ctypes.byref(state)) != 0:
        return False
    return state.value in _PRESENTING_STATES


def play_sound(path: str) -> None:
    if not IS_WINDOWS:
        return
    import winsound

    try:
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except RuntimeError:
        log.warning("Could not play sound %s", path)
