"""Real-provider audio-path regression test (slow; needs model downloads).

Guards the full local audio chain on real models — Piper synthesizes speech,
Silero VAD detects it (this is the regression guard for the v5 64-sample context
fix), and faster-whisper transcribes it. Excluded from the default/CI run
(`-m "not slow and not gpu"`); run locally with `pytest -m slow` once models are
cached. The LLM is not exercised here (that needs a running Ollama server).
"""

from __future__ import annotations

import pytest

from sutradhar.core.audio import float32_to_pcm16, pcm16_to_float32, resample
from sutradhar.core.config import Settings
from sutradhar.core.types import AudioFrame
from sutradhar.providers import build_stt, build_tts, build_vad

pytestmark = [pytest.mark.integration, pytest.mark.slow]


async def test_piper_silero_whisper_audio_path() -> None:
    settings = Settings()  # real defaults: piper, silero, faster-whisper
    phrase = "Book me a slot for tomorrow afternoon."

    tts = build_tts(settings)
    await tts.start()
    chunk = await tts.synthesize(phrase)
    assert chunk.pcm, "Piper produced no audio"

    samples = resample(pcm16_to_float32(chunk.pcm), chunk.sample_rate, 16000)

    vad = build_vad(settings)
    await vad.start()
    speech = total = 0
    for i in range(0, len(samples) - 320, 320):
        frame = AudioFrame(pcm=float32_to_pcm16(samples[i : i + 320]), sample_rate=16000)
        speech += int(vad.detect(frame).is_speech)
        total += 1
    # The 64-sample context fix makes Silero fire on real speech; >40% of frames
    # of a spoken sentence should register as speech.
    assert total > 0 and speech / total > 0.4, f"VAD under-detected speech: {speech}/{total}"

    stt = build_stt(settings)
    await stt.start()
    transcript = await stt.transcribe(float32_to_pcm16(samples), 16000)
    assert transcript.strip(), "STT returned empty transcript"
    assert "slot" in transcript.lower() or "tomorrow" in transcript.lower()
