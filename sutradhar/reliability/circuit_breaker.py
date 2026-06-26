"""Circuit breaker (PRD §13) — stop hammering a dead provider.

CLOSED: calls pass through. After `fail_threshold` consecutive failures the
breaker trips to OPEN and short-circuits calls (raising :class:`CircuitOpen`)
until `reset_ms` elapses, then HALF_OPEN admits one trial call: success closes
it, failure re-opens it. A `Clock` is injected so tests are deterministic.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import TypeVar

from sutradhar.core.clock import Clock, MonotonicClock
from sutradhar.core.errors import CircuitOpen

T = TypeVar("T")


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """A per-provider circuit breaker."""

    def __init__(
        self,
        name: str,
        *,
        fail_threshold: int = 5,
        reset_ms: int = 10_000,
        clock: Clock | None = None,
    ) -> None:
        self.name = name
        self.fail_threshold = fail_threshold
        self.reset_ms = reset_ms
        self._clock = clock or MonotonicClock()
        self._state = CircuitState.CLOSED
        self._failures = 0
        self._opened_at_ms = 0.0

    @property
    def state(self) -> CircuitState:
        self._maybe_half_open()
        return self._state

    def _maybe_half_open(self) -> None:
        if (
            self._state is CircuitState.OPEN
            and self._clock.now_ms() - self._opened_at_ms >= self.reset_ms
        ):
            self._state = CircuitState.HALF_OPEN

    def _on_success(self) -> None:
        self._failures = 0
        self._state = CircuitState.CLOSED

    def _on_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.fail_threshold or self._state is CircuitState.HALF_OPEN:
            self._state = CircuitState.OPEN
            self._opened_at_ms = self._clock.now_ms()

    async def call(self, factory: Callable[[], Awaitable[T]]) -> T:
        """Run `factory()` through the breaker."""
        self._maybe_half_open()
        if self._state is CircuitState.OPEN:
            raise CircuitOpen(self.name)
        try:
            result = await factory()
        except Exception:
            self._on_failure()
            raise
        else:
            self._on_success()
            return result
