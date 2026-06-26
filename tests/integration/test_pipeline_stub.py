"""M1 integration: the real streaming pipeline answers an utterance end-to-end.

Drives the actual `Pipeline` (VAD -> STT -> TurnDetector -> Orchestrator/LLM ->
TTS -> Transport) with dependency-free stub providers over a loopback transport.
Proves the half-duplex loop: synthetic speech frames in -> endpoint detected ->
transcript -> streamed reply -> audio chunks out, with voice-to-voice latency
recorded and no state corruption.
"""

from __future__ import annotations

import struct

import pytest

from sutradhar.core.config import Settings
from sutradhar.core.session import SessionManager
from sutradhar.core.types import AudioFrame, TurnState
from sutradhar.runtime import build_components, build_pipeline, start_components
from sutradhar.transport.loopback import LoopbackTransport

pytestmark = pytest.mark.integration

SAMPLE_RATE = 16000
FRAME_MS = 20
SAMPLES = SAMPLE_RATE * FRAME_MS // 1000  # 320


def _frame(seq: int, amplitude: int) -> AudioFrame:
    pcm = struct.pack(f"<{SAMPLES}h", *([amplitude] * SAMPLES))
    return AudioFrame(pcm=pcm, sample_rate=SAMPLE_RATE, seq=seq, timestamp_ms=seq * FRAME_MS)


def _utterance_then_silence(speech: int = 12, silence: int = 30) -> list[AudioFrame]:
    """A burst of 'speech' frames followed by enough silence to endpoint."""
    frames = [_frame(i, 6000) for i in range(speech)]
    frames += [_frame(speech + i, 0) for i in range(silence)]
    return frames


def _stub_settings() -> Settings:
    return Settings(
        env="ci",
        vad={"provider": "stub", "threshold": 0.02},
        stt={"provider": "stub"},
        turn={"provider": "stub", "silence_ms": 300},
        llm={"provider": "stub"},
        tts={"provider": "stub", "sample_rate": SAMPLE_RATE},
        memory={"provider": "stub"},
    )


async def test_pipeline_answers_one_utterance() -> None:
    settings = _stub_settings()
    manager = SessionManager(settings)
    session = await manager.create("itest")

    components = build_components(settings)
    await start_components(components)
    transport = LoopbackTransport("itest", _utterance_then_silence(), sample_rate=SAMPLE_RATE)
    pipeline = build_pipeline(session, transport, components=components)

    await pipeline.run()

    # The agent spoke something back.
    assert transport.sent, "agent produced no audio"
    assert transport.total_audio_ms > 0

    # History reflects a real user->assistant exchange (no corruption).
    roles = [m.role for m in session.state.history]
    assert roles[0].value == "user"
    assert roles[1].value == "assistant"
    assert session.state.history[1].content  # non-empty assistant reply

    # Ended cleanly back in LISTENING (half-duplex), not mid-turn.
    assert session.state.state is TurnState.LISTENING

    await manager.close("itest")


async def test_pipeline_records_voice_to_voice_latency() -> None:
    settings = _stub_settings()
    manager = SessionManager(settings)
    session = await manager.create("lat")

    # Capture each completed turn's latency report off the tracker.
    reports = []
    real_end = session.latency.end_turn

    def _capture() -> object:
        r = real_end()
        if r is not None:
            reports.append(r)
        return r

    session.latency.end_turn = _capture  # type: ignore[method-assign]

    components = build_components(settings)
    await start_components(components)
    transport = LoopbackTransport("lat", _utterance_then_silence(), sample_rate=SAMPLE_RATE)
    pipeline = build_pipeline(session, transport, components=components)
    await pipeline.run()

    assert reports, "no turn latency captured"
    v2v = reports[0].voice_to_voice_ms
    assert v2v is not None and v2v >= 0.0
    await manager.close("lat")


async def test_pipeline_no_speech_produces_no_turn() -> None:
    settings = _stub_settings()
    manager = SessionManager(settings)
    session = await manager.create("silent")

    components = build_components(settings)
    await start_components(components)
    # Pure silence: never starts an utterance.
    frames = [_frame(i, 0) for i in range(20)]
    transport = LoopbackTransport("silent", frames, sample_rate=SAMPLE_RATE)
    pipeline = build_pipeline(session, transport, components=components)
    await pipeline.run()

    assert transport.sent == []
    assert session.state.history == []
    await manager.close("silent")
