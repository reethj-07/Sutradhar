"""Reliability: circuit breaker, retries, failover (PRD §13, K7)."""

from __future__ import annotations

import pytest

from sutradhar.core.clock import FakeClock
from sutradhar.core.errors import (
    AllProvidersFailed,
    CircuitOpen,
    ProviderError,
)
from sutradhar.reliability.circuit_breaker import CircuitBreaker, CircuitState
from sutradhar.reliability.failover import FailoverChain
from sutradhar.reliability.retries import retry_async, with_timeout


# --- circuit breaker -------------------------------------------------------
async def test_circuit_opens_after_threshold() -> None:
    clock = FakeClock()
    cb = CircuitBreaker("x", fail_threshold=3, reset_ms=1000, clock=clock)

    async def boom() -> None:
        raise ProviderError("down", transient=False)

    for _ in range(3):
        with pytest.raises(ProviderError):
            await cb.call(boom)
    assert cb.state is CircuitState.OPEN
    with pytest.raises(CircuitOpen):
        await cb.call(boom)


async def test_circuit_half_open_then_closes_on_success() -> None:
    clock = FakeClock()
    cb = CircuitBreaker("x", fail_threshold=1, reset_ms=500, clock=clock)

    async def boom() -> None:
        raise ProviderError("down")

    with pytest.raises(ProviderError):
        await cb.call(boom)
    assert cb.state is CircuitState.OPEN

    clock.tick(600)  # past reset window
    assert cb.state is CircuitState.HALF_OPEN

    async def ok() -> int:
        return 1

    assert await cb.call(ok) == 1
    assert cb.state is CircuitState.CLOSED


# --- retries ---------------------------------------------------------------
async def test_retry_succeeds_after_transient_failures() -> None:
    attempts = {"n": 0}

    async def flaky() -> str:
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise ProviderError("blip", transient=True)
        return "ok"

    out = await retry_async(flaky, max_attempts=3, base_ms=1)
    assert out == "ok"
    assert attempts["n"] == 2


async def test_retry_does_not_retry_non_transient() -> None:
    attempts = {"n": 0}

    async def hard_fail() -> None:
        attempts["n"] += 1
        raise ProviderError("fatal", transient=False)

    with pytest.raises(ProviderError):
        await retry_async(hard_fail, max_attempts=5, base_ms=1)
    assert attempts["n"] == 1


async def test_with_timeout_raises_provider_timeout() -> None:
    import asyncio

    from sutradhar.core.errors import ProviderTimeout

    async def slow() -> None:
        await asyncio.sleep(1)

    with pytest.raises(ProviderTimeout):
        await with_timeout(slow(), timeout_ms=10, stage="stt")


# --- failover --------------------------------------------------------------
class _Provider:
    def __init__(self, name: str, *, healthy: bool) -> None:
        self.name = name
        self.healthy = healthy

    async def run(self) -> str:
        if not self.healthy:
            raise ProviderError(f"{self.name} down", transient=False)
        return self.name


async def test_failover_uses_secondary_when_primary_dead() -> None:
    chain: FailoverChain[_Provider] = FailoverChain(
        "llm",
        [_Provider("primary", healthy=False), _Provider("secondary", healthy=True)],
    )
    result = await chain.run(lambda p: p.run())
    assert result == "secondary"


async def test_failover_raises_when_all_dead() -> None:
    chain: FailoverChain[_Provider] = FailoverChain(
        "llm",
        [_Provider("a", healthy=False), _Provider("b", healthy=False)],
    )
    with pytest.raises(AllProvidersFailed):
        await chain.run(lambda p: p.run())
