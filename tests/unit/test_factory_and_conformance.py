"""Factory builds stubs from config; stubs structurally satisfy the interfaces."""

from __future__ import annotations

from sutradhar.core.config import Settings
from sutradhar.interfaces import LLM, STT, TTS, VAD, MemoryStore, TurnDetector
from sutradhar.providers import (
    build_llm,
    build_memory,
    build_stt,
    build_tts,
    build_turn_detector,
    build_vad,
)


def _stub_settings() -> Settings:
    return Settings(
        vad={"provider": "stub"},
        stt={"provider": "stub"},
        turn={"provider": "stub"},
        llm={"provider": "stub"},
        tts={"provider": "stub"},
        memory={"provider": "stub"},
    )


def test_factory_builds_stub_providers() -> None:
    s = _stub_settings()
    assert isinstance(build_vad(s), VAD)
    assert isinstance(build_stt(s), STT)
    assert isinstance(build_turn_detector(s), TurnDetector)
    assert isinstance(build_llm(s), LLM)
    assert isinstance(build_tts(s), TTS)
    assert isinstance(build_memory(s), MemoryStore)


def test_default_config_resolves_real_provider_classes() -> None:
    # Default (locked) config maps to the real provider classes without
    # constructing/loading models — i.e. the factory wiring is complete.
    s = Settings()
    assert build_vad(s).name == "silero"
    assert build_stt(s).name == "faster-whisper"
    assert build_llm(s).name == "ollama"
    assert build_tts(s).name == "piper"
    assert build_turn_detector(s).name == "hybrid-turn"
