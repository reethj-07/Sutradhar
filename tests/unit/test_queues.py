"""Bounded stream: ordering, closure, drop-oldest backpressure (PRD §5)."""

from __future__ import annotations

import pytest

from sutradhar.core.queues import BoundedStream, StreamClosed


async def test_put_get_order() -> None:
    s: BoundedStream[int] = BoundedStream(maxsize=4)
    for i in range(3):
        await s.put(i)
    s.close()
    assert [x async for x in s] == [0, 1, 2]


async def test_put_after_close_raises() -> None:
    s: BoundedStream[int] = BoundedStream()
    s.close()
    with pytest.raises(StreamClosed):
        await s.put(1)


async def test_drop_oldest_keeps_newest() -> None:
    s: BoundedStream[int] = BoundedStream(maxsize=2, drop_oldest=True)
    assert s.put_nowait(1)
    assert s.put_nowait(2)
    assert s.put_nowait(3)  # drops the oldest (1)
    s.close()
    out = [x async for x in s]
    assert out == [2, 3]
    assert s.dropped == 1


async def test_non_drop_put_nowait_reports_full() -> None:
    s: BoundedStream[int] = BoundedStream(maxsize=1)
    assert s.put_nowait(1) is True
    assert s.put_nowait(2) is False
    assert s.dropped == 1
