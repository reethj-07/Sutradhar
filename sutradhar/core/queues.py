"""Bounded async streams with explicit backpressure and clean closure.

Pipeline stages communicate over these (PRD §5: "bounded queues with explicit
backpressure and cancellation"). A bounded queue means a slow consumer (e.g. a
stalled LLM) applies backpressure to the producer instead of growing memory
without limit. `close()` signals end-of-stream so consumers iterating with
`async for` terminate cleanly — even if the buffer is full at close time
(closure is delivered out-of-band via an event, never via a buffered sentinel,
so EOF can't be lost behind backpressure).
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any, Generic, TypeVar

T = TypeVar("T")


class StreamClosed(Exception):
    """Raised by `get()`/`put()` once the stream is closed (and drained, for get)."""


class BoundedStream(Generic[T]):
    """A bounded, closable async stream usable as an async iterator.

    `put` blocks when full (backpressure). `close` signals EOF; iteration stops
    once buffered items are drained. `drop_oldest=True` drops the oldest item on
    overflow instead of blocking — used for real-time audio where freshness
    beats completeness.
    """

    def __init__(self, maxsize: int = 64, *, name: str = "", drop_oldest: bool = False) -> None:
        self._queue: asyncio.Queue[T] = asyncio.Queue(maxsize=maxsize)
        self._closed = False
        self._close_event = asyncio.Event()
        self.name = name
        self.drop_oldest = drop_oldest
        self.dropped = 0

    @property
    def closed(self) -> bool:
        return self._closed

    def qsize(self) -> int:
        return self._queue.qsize()

    async def put(self, item: T) -> None:
        if self._closed:
            raise StreamClosed(f"stream '{self.name}' is closed")
        if self.drop_oldest and self._queue.full():
            with contextlib.suppress(asyncio.QueueEmpty):
                self._queue.get_nowait()
                self.dropped += 1
        await self._queue.put(item)

    def put_nowait(self, item: T) -> bool:
        """Non-blocking put. Returns False if dropped (full and not drop_oldest)."""
        if self._closed:
            raise StreamClosed(f"stream '{self.name}' is closed")
        try:
            self._queue.put_nowait(item)
            return True
        except asyncio.QueueFull:
            if self.drop_oldest:
                with contextlib.suppress(asyncio.QueueEmpty, asyncio.QueueFull):
                    self._queue.get_nowait()
                    self._queue.put_nowait(item)
                    self.dropped += 1
                    return True
            self.dropped += 1
            return False

    async def get(self) -> T:
        """Return the next item, or raise :class:`StreamClosed` when drained."""
        while True:
            try:
                return self._queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            if self._closed:
                raise StreamClosed(f"stream '{self.name}' is closed")
            getter: asyncio.Future[T] = asyncio.ensure_future(self._queue.get())
            closer: asyncio.Future[Any] = asyncio.ensure_future(self._close_event.wait())
            waitset: set[asyncio.Future[Any]] = {getter, closer}
            try:
                done, _ = await asyncio.wait(waitset, return_when=asyncio.FIRST_COMPLETED)
                if getter in done:
                    return getter.result()
                # Closed fired first; abandon the getter and loop to drain/raise.
                getter.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await getter
            finally:
                closer.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await closer

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._close_event.set()

    def __aiter__(self) -> AsyncIterator[T]:
        return self

    async def __anext__(self) -> T:
        try:
            return await self.get()
        except StreamClosed:
            raise StopAsyncIteration from None
