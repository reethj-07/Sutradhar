"""Common lifecycle mixin for providers.

Providers are async-context-friendly: `start()` loads models / opens
connections (lazy, so importing a provider never pulls heavy ML libs), and
`aclose()` releases GPU/file/socket resources deterministically (PRD §13
"sessions clean up resources deterministically"). `health()` powers the
operator health surface and circuit breakers.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Component(Protocol):
    """Lifecycle a swappable provider exposes to the runtime."""

    name: str

    async def start(self) -> None:
        """Lazily initialize (load model, open connection). Idempotent."""
        ...

    async def aclose(self) -> None:
        """Release all resources. Idempotent and safe to call after failure."""
        ...

    async def health(self) -> bool:
        """Cheap liveness check used by `/readyz` and circuit breakers."""
        ...
