"""Domain type invariants."""

from __future__ import annotations

import pytest

from sutradhar.core.types import (
    AudioChunk,
    AudioFrame,
    Message,
    Role,
    ToolCall,
)


def test_audio_frame_duration() -> None:
    # 320 samples * 2 bytes = 640 bytes @ 16 kHz => 20 ms.
    frame = AudioFrame(pcm=bytes(640), sample_rate=16000)
    assert frame.num_samples == 320
    assert frame.duration_ms == pytest.approx(20.0)


def test_audio_chunk_duration() -> None:
    chunk = AudioChunk(pcm=bytes(44100 * 2), sample_rate=44100)
    assert chunk.duration_ms == pytest.approx(1000.0)


def test_empty_audio_is_zero_duration() -> None:
    assert AudioFrame(pcm=b"", sample_rate=16000).duration_ms == 0.0
    assert AudioChunk(pcm=b"", sample_rate=0).duration_ms == 0.0


def test_message_openai_render_with_tool_call() -> None:
    msg = Message(
        role=Role.ASSISTANT,
        content="",
        tool_calls=[ToolCall(id="c1", name="lookup", arguments={"id": 7})],
    )
    rendered = msg.to_openai()
    assert rendered["role"] == "assistant"
    assert rendered["tool_calls"][0]["function"]["name"] == "lookup"
    assert rendered["tool_calls"][0]["function"]["arguments"] == {"id": 7}
