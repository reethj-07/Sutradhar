"""Stub providers behave deterministically and conform to the interfaces."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sutradhar.core.types import AudioFrame, Message, Role
from sutradhar.providers.stub import (
    StubLLM,
    StubMemoryStore,
    StubSTT,
    StubTTS,
    StubVAD,
)


def _frame(level: int, n: int = 320) -> AudioFrame:
    # Constant-level 16-bit samples => predictable RMS.
    import struct

    pcm = struct.pack(f"<{n}h", *([level] * n))
    return AudioFrame(pcm=pcm, sample_rate=16000)


def test_stub_vad_detects_energy() -> None:
    vad = StubVAD(threshold=0.05)
    assert vad.detect(_frame(0)).is_speech is False
    assert vad.detect(_frame(8000)).is_speech is True


async def _drain_frames() -> AsyncIterator[AudioFrame]:
    for _ in range(3):
        yield _frame(1000)


async def test_stub_stt_streams_partials_then_final() -> None:
    stt = StubSTT(transcript="book a slot")
    chunks = [c async for c in stt.stream(_drain_frames())]
    assert chunks[-1].is_final is True
    assert chunks[-1].text == "book a slot"
    assert [c.is_final for c in chunks[:-1]] == [False, False, False]


async def test_stub_llm_streams_tokens_then_done() -> None:
    llm = StubLLM()
    msgs = [Message(role=Role.USER, content="what are your hours")]
    events = [e async for e in llm.stream(msgs)]
    assert events[-1].kind == "done"
    text = "".join(e.token for e in events if e.kind == "token")
    assert "what are your hours" in text


async def test_stub_tts_emits_audio_sized_to_text() -> None:
    tts = StubTTS(sample_rate=16000)

    async def text() -> AsyncIterator[str]:
        yield "hello there"

    chunks = [c async for c in tts.stream(text())]
    assert chunks[0].duration_ms > 0
    assert chunks[-1].is_final is True


async def test_stub_memory_retrieves_by_overlap() -> None:
    mem = StubMemoryStore()
    await mem.append("s1", "customer prefers morning appointments")
    await mem.append("s1", "the weather is nice")
    hits = await mem.retrieve("s1", "morning appointment slot")
    assert hits
    assert "morning" in hits[0].text
