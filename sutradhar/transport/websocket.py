"""WebSocket transport — default browser client channel (PRD §7). Wired in M1.

The browser streams 16 kHz mono PCM frames over a WebSocket; the server streams
synthesized PCM back. Implements the :class:`Transport` interface. Built in M1.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sutradhar.core.types import AudioChunk, AudioFrame, SessionEvent


class WebSocketTransport:
    name = "websocket"

    def __init__(self, session_id: str, sample_rate: int = 16000) -> None:
        self.session_id = session_id
        self.sample_rate = sample_rate

    def recv_audio(self) -> AsyncIterator[AudioFrame]:  # pragma: no cover - M1
        raise NotImplementedError("WebSocketTransport is wired in M1")

    async def send_audio(self, chunk: AudioChunk) -> None:  # pragma: no cover - M1
        raise NotImplementedError

    async def flush(self) -> None: ...

    def events(self) -> AsyncIterator[SessionEvent]:  # pragma: no cover - M1
        raise NotImplementedError("WebSocketTransport is wired in M1")

    async def close(self) -> None: ...
