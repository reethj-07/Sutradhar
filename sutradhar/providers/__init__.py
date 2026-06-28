"""Provider implementations + a config-driven factory (FR13).

`build_*` functions resolve the concrete implementation from `Settings` so the
rest of the system never imports a provider directly. The dependency-free
``stub`` providers are always available (used by tests and as the cloud-swap
placeholder); local-OSS providers (faster-whisper, Silero, Ollama, Piper) are
imported lazily so their heavy ML deps load only when actually selected.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sutradhar.interfaces import LLM, STT, TTS, VAD, MemoryStore, TurnDetector

if TYPE_CHECKING:
    from sutradhar.core.config import Settings


def build_vad(settings: Settings) -> VAD:
    p = settings.vad.provider
    if p == "stub":
        from sutradhar.providers.stub import StubVAD

        return StubVAD(threshold=settings.vad.threshold)
    if p == "silero":
        from sutradhar.providers.vad.silero import SileroVAD

        return SileroVAD(settings)
    if p == "webrtcvad":
        from sutradhar.providers.vad.webrtc_vad import WebRtcVAD

        return WebRtcVAD(settings)
    raise ValueError(f"unknown VAD provider: {p}")


def build_stt(settings: Settings) -> STT:
    p = settings.stt.provider
    if p == "stub":
        from sutradhar.providers.stub import StubSTT

        return StubSTT()
    if p == "faster_whisper":
        from sutradhar.providers.stt.faster_whisper import FasterWhisperSTT

        return FasterWhisperSTT(settings)
    raise ValueError(f"unknown STT provider: {p}")


def build_llm(settings: Settings) -> LLM:
    p = settings.llm.provider
    if p == "stub":
        from sutradhar.providers.stub import StubLLM

        return StubLLM()
    if p == "ollama":
        from sutradhar.providers.llm.ollama import OllamaLLM

        return OllamaLLM(settings)
    if p == "openai_compatible":
        from sutradhar.providers.llm.openai_compatible import OpenAICompatibleLLM

        return OpenAICompatibleLLM(settings)
    raise ValueError(f"unknown LLM provider: {p}")


def build_tts(settings: Settings) -> TTS:
    p = settings.tts.provider
    if p == "stub":
        from sutradhar.providers.stub import StubTTS

        return StubTTS(sample_rate=settings.tts.sample_rate)
    if p == "piper":
        from sutradhar.providers.tts.piper import PiperTTS

        return PiperTTS(settings)
    if p == "kokoro":
        from sutradhar.providers.tts.kokoro import KokoroTTS

        return KokoroTTS(settings)
    raise ValueError(f"unknown TTS provider: {p}")


def build_turn_detector(settings: Settings) -> TurnDetector:
    p = settings.turn.provider
    if p == "stub":
        from sutradhar.providers.stub import StubTurnDetector

        return StubTurnDetector(silence_ms=settings.turn.silence_ms)
    if p in ("vad_pause", "hybrid"):
        from sutradhar.providers.turn.detector import HybridTurnDetector

        return HybridTurnDetector(settings)
    raise ValueError(f"unknown turn detector: {p}")


def build_memory(settings: Settings) -> MemoryStore:
    p = settings.memory.provider
    if p == "stub":
        from sutradhar.providers.stub import StubMemoryStore

        return StubMemoryStore()
    if p == "sqlite":
        from sutradhar.providers.memory.sqlite_store import SqliteMemoryStore

        return SqliteMemoryStore(settings)
    raise ValueError(f"unknown memory provider: {p}")


__all__ = [
    "build_llm",
    "build_memory",
    "build_stt",
    "build_tts",
    "build_turn_detector",
    "build_vad",
]
