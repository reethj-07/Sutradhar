"""Retries with exponential backoff + jitter, and per-stage timeouts (PRD §13).

`retry_async` retries only *transient* failures; `with_timeout` enforces the
per-stage deadline that bounds tail latency and trips failover. Jitter is
deterministic per-attempt (no `random`) so behavior is reproducible in tests.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from sutradhar.core.errors import ProviderError, ProviderTimeout
from sutradhar.observability.logging import get_logger

T = TypeVar("T")
_log = get_logger("reliability.retries")


async def with_timeout(
    coro: Awaitable[T],
    timeout_ms: int,
    *,
    stage: str = "",
    provider: str = "",
) -> T:
    """Await `coro` with a deadline, raising :class:`ProviderTimeout` on expiry."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout_ms / 1000.0)
    except TimeoutError as exc:
        raise ProviderTimeout(
            f"{stage or 'operation'} timed out after {timeout_ms}ms",
            provider=provider,
            stage=stage,
        ) from exc


def _is_transient(exc: BaseException) -> bool:
    if isinstance(exc, ProviderError):
        return exc.transient
    return isinstance(exc, (asyncio.TimeoutError, ConnectionError, OSError))


async def retry_async(
    factory: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 2,
    base_ms: int = 100,
    max_ms: int = 2000,
    stage: str = "",
) -> T:
    """Call `factory()` up to `max_attempts`, backing off on transient errors.

    `factory` returns a fresh awaitable per attempt (awaitables aren't reusable).
    Non-transient errors are re-raised immediately so failover can take over.
    """
    attempt = 0
    last_exc: BaseException | None = None
    while attempt < max_attempts:
        try:
            return await factory()
        except Exception as exc:
            last_exc = exc
            attempt += 1
            if not _is_transient(exc) or attempt >= max_attempts:
                raise
            # Exponential backoff with deterministic decorrelated jitter.
            delay_ms = min(max_ms, base_ms * (2 ** (attempt - 1)))
            jitter = (attempt * 17) % max(1, base_ms)
            _log.warning(
                "retrying",
                stage=stage,
                attempt=attempt,
                max_attempts=max_attempts,
                delay_ms=delay_ms + jitter,
                error=str(exc),
            )
            await asyncio.sleep((delay_ms + jitter) / 1000.0)
    assert last_exc is not None  # pragma: no cover
    raise last_exc
