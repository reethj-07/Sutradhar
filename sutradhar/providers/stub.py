"""Dependency-free stub providers.

These implement the interfaces deterministically with zero ML dependencies.
They serve three purposes:

1. The "cloud-stub" swap target the PRD requires for every interface (≥2 impls).
2. A fast, hermetic substrate for unit/integration tests and CI (no models).
3. A way to exercise the full pipeline (M1) before the real models are wired.

Audio math uses the stdlib ``array`` module (``audioop`` was removed in 3.13).
"""

from __future__ import annotations

import array
import asyncio
import math
from collections.abc import AsyncIterator, Sequence
from typing import Any

from sutradhar.core.types import (
    AudioChunk,
    AudioFrame,
    LLMResponseEvent,
    Message,
    TranscriptChunk,
    VADResult,
)
from sutradhar.interfaces.memory import MemoryRecord
from sutradhar.interfaces.turn import EndpointDecision, TurnContext


def _rms(pcm: bytes) -> float:
    """Root-mean-square amplitude of 16-bit PCM, normalized to [0, 1]."""
    if not pcm:
        return 0.0
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    if not samples:
        return 0.0
    acc = sum(s * s for s in samples)
    return math.sqrt(acc / len(samples)) / 32768.0


class StubVAD:
    """Energy-threshold VAD. Real audio with speech crosses the threshold."""

    name = "stub-vad"

    def __init__(self, threshold: float = 0.01) -> None:
        self.threshold = threshold

    async def start(self) -> None: ...

    def detect(self, frame: AudioFrame) -> VADResult:
        energy = _rms(frame.pcm)
        return VADResult(
            is_speech=energy >= self.threshold,
            probability=min(1.0, energy / max(self.threshold, 1e-6)),
            timestamp_ms=frame.timestamp_ms,
        )

    def reset(self) -> None: ...

    async def aclose(self) -> None: ...


class StubSTT:
    """Emits a scripted transcript word-by-word as partials, then a final.

    Feed it a transcript via the constructor or set `next_transcript` per turn;
    defaults to a fixed phrase so tests are deterministic.
    """

    name = "stub-stt"

    def __init__(self, transcript: str = "hello this is a stub transcript") -> None:
        self.next_transcript = transcript

    async def start(self) -> None: ...

    async def stream(self, audio: AsyncIterator[AudioFrame]) -> AsyncIterator[TranscriptChunk]:
        # Drain audio to mimic real consumption (and end-of-stream detection).
        async for _ in audio:
            pass
        words = self.next_transcript.split()
        acc: list[str] = []
        for i, w in enumerate(words):
            acc.append(w)
            yield TranscriptChunk(text=" ".join(acc), is_final=False, turn_seq=i)
            await asyncio.sleep(0)
        yield TranscriptChunk(text=" ".join(words), is_final=True, confidence=0.95)

    async def transcribe(self, pcm: bytes, sample_rate: int) -> str:
        return self.next_transcript

    async def aclose(self) -> None: ...


class StubLLM:
    """Deterministic LLM: streams a short, templated reply token by token."""

    name = "stub-llm"

    def __init__(self, reply: str | None = None) -> None:
        self._reply = reply

    async def start(self) -> None: ...

    def _make_reply(self, messages: Sequence[Message]) -> str:
        if self._reply is not None:
            return self._reply
        last_user = next((m.content for m in reversed(messages) if m.role.value == "user"), "")
        snippet = last_user.strip()[:60]
        return f"Sure — you said: {snippet}. How can I help further?"

    async def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> AsyncIterator[LLMResponseEvent]:
        reply = self._make_reply(messages)
        for tok in reply.split(" "):
            yield LLMResponseEvent(kind="token", token=tok + " ")
            await asyncio.sleep(0)
        yield LLMResponseEvent(kind="done", finish_reason="stop")

    async def complete(self, messages: Sequence[Message]) -> str:
        return self._make_reply(messages)

    async def aclose(self) -> None: ...


class StubTTS:
    """Synthesizes silence sized to the text (sounds like nothing, times like speech)."""

    name = "stub-tts"

    def __init__(self, sample_rate: int = 22050, ms_per_char: float = 55.0) -> None:
        self.sample_rate = sample_rate
        self.ms_per_char = ms_per_char

    async def start(self) -> None: ...

    def _pcm_for(self, text: str) -> bytes:
        ms = max(20.0, len(text) * self.ms_per_char)
        n = int(self.sample_rate * ms / 1000.0)
        return bytes(2 * n)  # 16-bit silence

    async def stream(self, text: AsyncIterator[str]) -> AsyncIterator[AudioChunk]:
        seq = 0
        async for fragment in text:
            if not fragment.strip():
                continue
            yield AudioChunk(
                pcm=self._pcm_for(fragment),
                sample_rate=self.sample_rate,
                seq=seq,
                text=fragment,
            )
            seq += 1
            await asyncio.sleep(0)
        yield AudioChunk(pcm=b"", sample_rate=self.sample_rate, seq=seq, is_final=True)

    async def synthesize(self, text: str) -> AudioChunk:
        return AudioChunk(pcm=self._pcm_for(text), sample_rate=self.sample_rate, text=text)

    async def aclose(self) -> None: ...


class StubTurnDetector:
    """Endpoints on trailing silence past the configured threshold."""

    name = "stub-turn"

    def __init__(self, silence_ms: int = 480) -> None:
        self.silence_ms = silence_ms

    async def start(self) -> None: ...

    def observe(self, ctx: TurnContext) -> EndpointDecision:
        endpoint = (
            not ctx.is_speech
            and ctx.trailing_silence_ms >= self.silence_ms
            and len(ctx.transcript.strip()) > 0
        )
        return EndpointDecision(
            endpoint=endpoint,
            confidence=1.0 if endpoint else 0.0,
            reason="trailing_silence" if endpoint else "",
            acoustic=endpoint,
        )

    def reset(self) -> None: ...

    async def aclose(self) -> None: ...


class StubMemoryStore:
    """In-memory store with naive substring retrieval (no embeddings)."""

    name = "stub-memory"

    def __init__(self) -> None:
        self._records: list[MemoryRecord] = []
        self._counter = 0

    async def start(self) -> None: ...

    async def append(
        self,
        session_id: str,
        text: str,
        *,
        kind: str = "turn",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        self._counter += 1
        rec_id = f"mem-{self._counter}"
        self._records.append(
            MemoryRecord(
                id=rec_id,
                session_id=session_id,
                text=text,
                kind=kind,
                metadata=metadata or {},
            )
        )
        return rec_id

    async def retrieve(self, session_id: str, query: str, *, k: int = 4) -> list[MemoryRecord]:
        q = {w.lower() for w in query.split()}

        def overlap(r: MemoryRecord) -> int:
            return len(q & {w.lower() for w in r.text.split()})

        candidates = [r for r in self._records if r.session_id == session_id]
        ranked = sorted(candidates, key=overlap, reverse=True)
        return [
            MemoryRecord(r.id, r.session_id, r.text, r.kind, float(overlap(r)), r.metadata)
            for r in ranked[:k]
            if overlap(r) > 0
        ]

    async def aclose(self) -> None: ...
