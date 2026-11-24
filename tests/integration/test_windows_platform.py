"""Real Windows API calls (no mocks). Skipped automatically off Windows."""

import sys

import pytest

from eye_break.platform import windows
from eye_break.platform.windows import startup

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def test_idle_seconds_is_sane():
    value = windows.idle_seconds()
    assert 0 <= value < 10 * 24 * 3600


def test_lock_and_presentation_queries_return_bool():
    assert isinstance(windows.is_session_locked(), bool)
    assert isinstance(windows.is_presenting(), bool)


def test_startup_registration_roundtrip():
    name = "EyeBreakTestOnly"
    try:
        assert startup.set_enabled(True, name)
        assert startup.is_enabled(name)
        assert startup.set_enabled(False, name)
        assert not startup.is_enabled(name)
        assert startup.set_enabled(False, name)  # removing twice is harmless
    finally:
        startup.set_enabled(False, name)
