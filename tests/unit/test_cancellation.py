"""Cancellation token — the barge-in backbone (PRD §9.2)."""

from __future__ import annotations

import asyncio

import pytest

from sutradhar.core.cancellation import CancellationToken, OperationCancelled


def test_cancel_is_idempotent_and_records_reason() -> None:
    tok = CancellationToken()
    assert not tok.cancelled
    tok.cancel("barge-in")
    tok.cancel("again")
    assert tok.cancelled
    assert tok.reason == "barge-in"


def test_raise_if_cancelled() -> None:
    tok = CancellationToken()
    tok.raise_if_cancelled()  # no-op
    tok.cancel("stop")
    with pytest.raises(OperationCancelled):
        tok.raise_if_cancelled()


def test_child_token_cancelled_by_parent() -> None:
    parent = CancellationToken()
    child = parent.child()
    assert not child.cancelled
    parent.cancel("boom")
    assert child.cancelled
    assert child.reason == "boom"


def test_on_cancel_callback_fires_once() -> None:
    tok = CancellationToken()
    calls: list[str] = []
    tok.on_cancel(calls.append)
    tok.cancel("x")
    tok.cancel("y")
    assert calls == ["x"]


async def test_guard_returns_result_when_not_cancelled() -> None:
    tok = CancellationToken()

    async def work() -> int:
        await asyncio.sleep(0)
        return 42

    assert await tok.guard(asyncio.ensure_future(work())) == 42


async def test_guard_raises_when_cancelled_first() -> None:
    tok = CancellationToken()

    async def slow() -> int:
        await asyncio.sleep(5)
        return 1

    fut = asyncio.ensure_future(slow())
    loop = asyncio.get_running_loop()
    loop.call_later(0.01, tok.cancel, "interrupt")
    with pytest.raises(OperationCancelled):
        await tok.guard(fut)
    assert fut.cancelled()


async def test_stream_stops_promptly_on_cancel() -> None:
    tok = CancellationToken()

    async def numbers() -> object:
        for i in range(1000):
            await asyncio.sleep(0.001)
            yield i

    seen: list[int] = []
    with pytest.raises(OperationCancelled):
        async for n in tok.stream(numbers()):
            seen.append(n)
            if n == 2:
                tok.cancel("done")
    assert seen == [0, 1, 2]
