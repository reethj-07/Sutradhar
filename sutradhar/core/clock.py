"""Time source. A `Clock` Protocol lets tests inject a deterministic clock so
latency assertions don't depend on wall time. Production uses a monotonic clock
(immune to NTP/system-clock jumps) measured in milliseconds.
"""

from __future__ import annotations

import time
from typing import Protocol, runtime_checkable


def monotonic_ms() -> float:
    """Monotonic time in milliseconds — the unit used across the pipeline."""
    return time.perf_counter() * 1000.0


@runtime_checkable
class Clock(Protocol):
    """Pluggable time source (real or fake)."""

    def now_ms(self) -> float: ...


class MonotonicClock:
    """Default real clock backed by :func:`time.perf_counter`."""

    def now_ms(self) -> float:
        return monotonic_ms()


class FakeClock:
    """Deterministic clock for tests. Advance time explicitly with `tick`."""

    def __init__(self, start_ms: float = 0.0) -> None:
        self._now = start_ms

    def now_ms(self) -> float:
        return self._now

    def tick(self, ms: float) -> float:
        self._now += ms
        return self._now
