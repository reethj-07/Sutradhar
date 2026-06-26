"""Provider failover chain (PRD §13, K7).

Wraps an ordered list of interchangeable provider implementations (primary +
secondaries) behind one call site. Each is fronted by its own circuit breaker;
on error/timeout the chain advances to the next provider. If all fail it raises
:class:`AllProvidersFailed`. This is what lets "kill a provider, conversation
survives" hold true.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Generic, TypeVar

from sutradhar.core.errors import AllProvidersFailed, CircuitOpen
from sutradhar.observability.logging import get_logger
from sutradhar.reliability.circuit_breaker import CircuitBreaker

P = TypeVar("P")  # provider type
R = TypeVar("R")  # call result type

_log = get_logger("reliability.failover")


class FailoverChain(Generic[P]):
    """An ordered set of providers tried in turn, each with a circuit breaker."""

    def __init__(
        self,
        stage: str,
        providers: list[P],
        *,
        fail_threshold: int = 5,
        reset_ms: int = 10_000,
    ) -> None:
        if not providers:
            raise ValueError("FailoverChain requires at least one provider")
        self.stage = stage
        self.providers = providers
        self._breakers = [
            CircuitBreaker(
                f"{stage}[{getattr(p, 'name', i)}]",
                fail_threshold=fail_threshold,
                reset_ms=reset_ms,
            )
            for i, p in enumerate(providers)
        ]

    @property
    def primary(self) -> P:
        return self.providers[0]

    async def run(self, call: Callable[[P], Awaitable[R]]) -> R:
        """Invoke `call(provider)` against each provider until one succeeds."""
        errors: list[BaseException] = []
        for provider, breaker in zip(self.providers, self._breakers, strict=True):
            try:
                return await breaker.call(lambda p=provider: call(p))  # type: ignore[misc]
            except CircuitOpen as exc:
                errors.append(exc)
                continue
            except Exception as exc:
                errors.append(exc)
                _log.warning(
                    "provider_failed",
                    stage=self.stage,
                    provider=getattr(provider, "name", "?"),
                    error=str(exc),
                )
                continue
        raise AllProvidersFailed(self.stage, errors)
