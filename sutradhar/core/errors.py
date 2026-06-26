"""Exception hierarchy. Fail-soft (PRD §13) depends on classifying failures:
transient (retry), provider-down (failover/circuit-break), or fatal.
"""

from __future__ import annotations


class SutradharError(Exception):
    """Base class for all Sutradhar errors."""


class ConfigError(SutradharError):
    """Invalid or inconsistent configuration."""


class TransportClosed(SutradharError):
    """The transport channel was closed by the peer or locally."""


class ProviderError(SutradharError):
    """A provider (STT/LLM/TTS/VAD/...) failed.

    `transient=True` marks failures worth retrying (network blip, 5xx);
    `transient=False` marks failures that should trip failover immediately.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str = "",
        stage: str = "",
        transient: bool = True,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.stage = stage
        self.transient = transient


class ProviderTimeout(ProviderError):
    """A provider exceeded its per-stage deadline."""

    def __init__(self, message: str, *, provider: str = "", stage: str = "") -> None:
        super().__init__(message, provider=provider, stage=stage, transient=True)


class CircuitOpen(SutradharError):
    """A circuit breaker is open; the call was short-circuited."""

    def __init__(self, name: str) -> None:
        super().__init__(f"circuit '{name}' is open")
        self.name = name


class AllProvidersFailed(SutradharError):
    """Every implementation in a failover chain failed."""

    def __init__(self, stage: str, errors: list[BaseException]) -> None:
        super().__init__(f"all providers failed for stage '{stage}' ({len(errors)} tried)")
        self.stage = stage
        self.errors = errors
