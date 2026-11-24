"""Injectable clocks so scheduling can be tested without waiting."""

from __future__ import annotations

import time
from datetime import datetime, timedelta


class Clock:
    """Real clock. `monotonic` measures durations; `now` is only for timestamps and calendar logic."""

    def monotonic(self) -> float:
        return time.monotonic()

    def now(self) -> datetime:
        return datetime.now()


class ScaledClock(Clock):
    """Development clock running `speed` times faster than real time (for manual testing)."""

    def __init__(self, speed: float) -> None:
        self.speed = max(1.0, speed)
        self._mono0 = time.monotonic()
        self._wall0 = datetime.now()

    def monotonic(self) -> float:
        return self._mono0 + (time.monotonic() - self._mono0) * self.speed

    def now(self) -> datetime:
        return self._wall0 + timedelta(seconds=self.monotonic() - self._mono0)


class FakeClock(Clock):
    """Manually advanced clock for tests."""

    def __init__(self, start: datetime | None = None) -> None:
        self._mono = 1000.0
        self._wall = start or datetime(2026, 1, 5, 9, 0, 0)

    def monotonic(self) -> float:
        return self._mono

    def now(self) -> datetime:
        return self._wall

    def advance(self, seconds: float) -> None:
        self._mono += seconds
        self._wall += timedelta(seconds=seconds)

    def set_wall(self, wall: datetime) -> None:
        """Simulate a system clock change (monotonic time is unaffected)."""
        self._wall = wall
