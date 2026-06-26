"""Cooperative cancellation — the backbone of barge-in (PRD §6.1, §9.2).

Every in-flight operation (LLM generation, TTS synthesis, audio playout) is
handed a :class:`CancellationToken`. On confirmed user speech the turn engine
cancels the token, and each stage checks `raise_if_cancelled()` / awaits
`wait()` to stop within the PRD's ≤200 ms barge-in budget.

This is intentionally separate from `asyncio.Task.cancel()`: a token can be
shared across many tasks and child tokens, queried without raising, and linked
so cancelling a parent cancels its children.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import suppress
from typing import Any, TypeVar

from sutradhar.core.errors import SutradharError

T = TypeVar("T")


class OperationCancelled(SutradharError):
    """Raised by `raise_if_cancelled()` when a token has been cancelled."""

    def __init__(self, reason: str = "operation cancelled") -> None:
        super().__init__(reason)
        self.reason = reason


class CancellationToken:
    """A shareable, awaitable, linkable cancellation signal."""

    __slots__ = ("_callbacks", "_children", "_event", "_reason")

    def __init__(self) -> None:
        self._event = asyncio.Event()
        self._reason = ""
        self._children: set[CancellationToken] = set()
        self._callbacks: list[Callable[[str], None]] = []

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> str:
        return self._reason

    def cancel(self, reason: str = "cancelled") -> None:
        """Cancel this token (and any linked children). Idempotent."""
        if self._event.is_set():
            return
        self._reason = reason
        self._event.set()
        for cb in self._callbacks:
            with suppress(Exception):
                cb(reason)
        for child in self._children:
            child.cancel(reason)

    def raise_if_cancelled(self) -> None:
        """Raise :class:`OperationCancelled` if cancelled — call at checkpoints."""
        if self._event.is_set():
            raise OperationCancelled(self._reason)

    async def wait(self) -> str:
        """Block until cancelled, returning the reason."""
        await self._event.wait()
        return self._reason

    def on_cancel(self, callback: Callable[[str], None]) -> None:
        """Register a synchronous callback fired exactly once on cancel."""
        if self._event.is_set():
            callback(self._reason)
        else:
            self._callbacks.append(callback)

    def child(self) -> CancellationToken:
        """Create a linked child token; cancelling the parent cancels it."""
        token = CancellationToken()
        if self._event.is_set():
            token.cancel(self._reason)
        else:
            self._children.add(token)
        return token

    def reset(self) -> None:
        """Reset to the un-cancelled state for reuse across turns."""
        self._event.clear()
        self._reason = ""
        self._children.clear()
        self._callbacks.clear()

    async def guard(self, awaitable: asyncio.Future[T] | asyncio.Task[T]) -> T:
        """Await `awaitable`, raising :class:`OperationCancelled` if cancelled
        first. The awaitable is cancelled to avoid leaking a pending task.
        """
        cancel_wait: asyncio.Future[Any] = asyncio.ensure_future(self._event.wait())
        target: asyncio.Future[T] = asyncio.ensure_future(awaitable)
        tasks: set[asyncio.Future[Any]] = {target, cancel_wait}
        try:
            done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            if target in done:
                return target.result()
            target.cancel()
            with suppress(asyncio.CancelledError):
                await target
            raise OperationCancelled(self._reason)
        finally:
            cancel_wait.cancel()
            with suppress(asyncio.CancelledError):
                await cancel_wait

    async def stream(self, source: AsyncIterator[T]) -> AsyncIterator[T]:
        """Wrap an async iterator so it stops promptly on cancellation.

        Used to make STT/LLM/TTS streams barge-in-aware: each item is raced
        against the cancel signal so iteration halts mid-stream.
        """
        iterator = source.__aiter__()
        while True:
            self.raise_if_cancelled()
            nxt = asyncio.ensure_future(iterator.__anext__())
            try:
                item = await self.guard(nxt)
            except StopAsyncIteration:
                return
            yield item
