"""Transport interface — move audio frames in/out of a session (PRD §6.3).

One interface spans the browser WebSocket client, an optional aiortc WebRTC
path, and a simulated-telephony (8 kHz, SIP-like lifecycle) adapter. The
pipeline reads inbound frames from `recv_audio()`, writes synthesized audio to
`send_audio()`, and learns about connect/disconnect/barge-in via `events()`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from sutradhar.core.types import AudioChunk, AudioFrame, SessionEvent


@runtime_checkable
class Transport(Protocol):
    """Bidirectional audio + control channel for one session."""

    name: str
    session_id: str
    sample_rate: int

    def recv_audio(self) -> AsyncIterator[AudioFrame]:
        """Yield inbound audio frames until the peer disconnects."""
        ...

    async def send_audio(self, chunk: AudioChunk) -> None:
        """Send one chunk of synthesized audio to the peer."""
        ...

    async def flush(self) -> None:
        """Drop any buffered outbound audio immediately (barge-in)."""
        ...

    def events(self) -> AsyncIterator[SessionEvent]:
        """Yield session lifecycle/control events."""
        ...

    async def close(self) -> None:
        """Close the channel and release resources."""
        ...
