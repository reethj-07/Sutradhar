"""In-memory loopback transport (tests + no-hardware demo).

Feeds a preloaded list of audio frames into the pipeline and collects everything
the agent speaks back. Implements the :class:`Transport` interface so the *real*
pipeline can be exercised end-to-end without a microphone, GPU or browser — used
by the M1 integration test and `sutradhar demo --stub`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable

from sutradhar.core.types import AudioChunk, AudioFrame, SessionEvent


class LoopbackTransport:
    name = "loopback"

    def __init__(
        self,
        session_id: str,
        frames: Iterable[AudioFrame],
        *,
        sample_rate: int = 16000,
    ) -> None:
        self.session_id = session_id
        self.sample_rate = sample_rate
        self._frames = list(frames)
        self.sent: list[AudioChunk] = []
        self._flushes = 0

    async def recv_audio(self) -> AsyncIterator[AudioFrame]:
        for frame in self._frames:
            yield frame

    async def send_audio(self, chunk: AudioChunk) -> None:
        self.sent.append(chunk)

    async def flush(self) -> None:
        self._flushes += 1

    async def events(self) -> AsyncIterator[SessionEvent]:
        empty: list[SessionEvent] = []  # loopback emits no control events
        for event in empty:
            yield event

    async def close(self) -> None: ...

    # -- test helpers ------------------------------------------------------
    @property
    def spoken_text(self) -> str:
        return " ".join(c.text for c in self.sent if c.text).strip()

    @property
    def total_audio_ms(self) -> float:
        return sum(c.duration_ms for c in self.sent)
