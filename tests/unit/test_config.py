"""Config loads defaults and honors nested env overrides (FR13, PRD §15)."""

from __future__ import annotations

import pytest

from sutradhar.core.config import Settings


def test_defaults_match_locked_stack() -> None:
    s = Settings()
    assert s.stt.provider == "faster_whisper"
    assert s.stt.model_size == "small"
    assert s.stt.device == "cuda"
    assert s.llm.provider == "ollama"
    assert s.llm.model.startswith("qwen2.5:3b")
    assert s.tts.provider == "piper"
    assert s.vad.provider == "silero"
    assert s.transport.default == "websocket"


def test_audio_frame_bytes() -> None:
    s = Settings()
    # 16 kHz, 20 ms, 16-bit mono => 320 samples => 640 bytes.
    assert s.audio.frame_bytes == 640


def test_nested_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUTRADHAR_STT__MODEL_SIZE", "base")
    monkeypatch.setenv("SUTRADHAR_LLM__TEMPERATURE", "0.1")
    monkeypatch.setenv("SUTRADHAR_TTS__PROVIDER", "kokoro")
    s = Settings()
    assert s.stt.model_size == "base"
    assert s.llm.temperature == pytest.approx(0.1)
    assert s.tts.provider == "kokoro"


def test_invalid_provider_rejected() -> None:
    with pytest.raises(ValueError):
        Settings(stt={"provider": "not-a-real-provider"})
