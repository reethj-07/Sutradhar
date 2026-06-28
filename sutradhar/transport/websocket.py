"""WebSocket transport — default browser client channel (PRD §7).

Wraps a Starlette/FastAPI ``WebSocket``. The browser streams mono 16-bit PCM at
16 kHz as binary frames; the server re-chunks them into fixed-size pipeline
frames. Outbound TTS audio is resampled to a fixed playback rate and sent back as
binary; small JSON text messages carry control events (e.g. ``agent_done``).

Implements the :class:`Transport` interface. Half-duplex for M1; ``flush`` is the
hook M2 uses to stop playout on barge-in.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

from sutradhar.core.audio import resample_pcm16
from sutradhar.core.types import AudioChunk, AudioFrame, SessionEvent, SessionEventType
from sutradhar.observability.logging import get_logger

if TYPE_CHECKING:
    from starlette.websockets import WebSocket

_log = get_logger("transport.websocket")

# Playback rate sent to the browser (browser AudioContext resamples on play).
OUT_SAMPLE_RATE = 24000


class WebSocketTransport:
    name = "websocket"

    def __init__(
        self,
        websocket: WebSocket,
        session_id: str,
        *,
        sample_rate: int = 16000,
        frame_ms: int = 20,
        out_sample_rate: int = OUT_SAMPLE_RATE,
    ) -> None:
        self.ws = websocket
        self.session_id = session_id
        self.sample_rate = sample_rate
        self.out_sample_rate = out_sample_rate
        self._frame_bytes = int(sample_rate * frame_ms / 1000) * 2
        self._frame_ms = frame_ms
        self._buf = bytearray()
        self._seq = 0
        self._closed = False

    async def recv_audio(self) -> AsyncIterator[AudioFrame]:
        """Yield fixed-size PCM frames assembled from inbound WebSocket bytes."""
        from starlette.websockets import WebSocketDisconnect

        try:
            while True:
                message = await self.ws.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                data = message.get("bytes")
                if data is None:
                    # Ignore text/control messages on the inbound audio path.
                    continue
                self._buf.extend(data)
                while len(self._buf) >= self._frame_bytes:
                    chunk = bytes(self._buf[: self._frame_bytes])
                    del self._buf[: self._frame_bytes]
                    self._seq += 1
                    yield AudioFrame(
                        pcm=chunk,
                        sample_rate=self.sample_rate,
                        seq=self._seq,
                        timestamp_ms=self._seq * self._frame_ms,
                    )
        except WebSocketDisconnect:
            _log.info("ws_disconnected", session_id=self.session_id)

    async def send_audio(self, chunk: AudioChunk) -> None:
        if self._closed or not chunk.pcm:
            return
        pcm = resample_pcm16(chunk.pcm, chunk.sample_rate, self.out_sample_rate)
        try:
            await self.ws.send_bytes(pcm)
        except Exception as exc:  # peer gone mid-send; treat as closed
            self._closed = True
            _log.info("ws_send_failed", session_id=self.session_id, error=str(exc))

    async def flush(self) -> None:
        # Tell the client to drop any queued playout (barge-in, M2).
        await self._send_event(SessionEventType.BARGE_IN)

    async def _send_event(
        self, kind: SessionEventType, detail: dict[str, Any] | None = None
    ) -> None:
        if self._closed:
            return
        try:
            await self.ws.send_json({"event": kind.value, "detail": detail or {}})
        except Exception:  # best-effort control channel
            self._closed = True

    async def events(self) -> AsyncIterator[SessionEvent]:
        # Inbound control events are not used in M1; yield nothing.
        empty: list[SessionEvent] = []
        for event in empty:
            yield event

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with contextlib.suppress(Exception):  # already closed
            await self.ws.close()
