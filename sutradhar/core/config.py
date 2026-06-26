"""Typed configuration via pydantic-settings (PRD §15).

One nested `Settings` tree, populated from defaults -> `.env` -> environment.
Every provider is selected by string here, so swapping STT/LLM/TTS/VAD/transport
is a config change, never a code change (FR13). Env vars are prefixed
`SUTRADHAR_` and nested with `__`, e.g. `SUTRADHAR_STT__MODEL_SIZE=base`.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class AudioSettings(BaseModel):
    sample_rate: int = 16000
    frame_ms: int = 20
    telephony_sample_rate: int = 8000

    @property
    def frame_bytes(self) -> int:
        """Bytes per VAD frame (16-bit mono PCM)."""
        return int(self.sample_rate * self.frame_ms / 1000) * 2


class VADSettings(BaseModel):
    provider: Literal["silero", "webrtcvad", "stub"] = "silero"
    threshold: float = 0.5
    min_silence_ms: int = 480
    speech_pad_ms: int = 120


class STTSettings(BaseModel):
    provider: Literal["faster_whisper", "vosk", "stub"] = "faster_whisper"
    model_size: Literal["tiny", "base", "small", "medium"] = "small"
    device: Literal["cuda", "cpu"] = "cuda"
    compute_type: str = "int8_float16"
    language: str = "en"
    beam_size: int = 1  # greedy for latency


class TurnSettings(BaseModel):
    provider: Literal["vad_pause", "hybrid", "stub"] = "hybrid"
    silence_ms: int = 480
    max_utterance_ms: int = 15000
    semantic_enabled: bool = True
    min_endpoint_chars: int = 2


class LLMSettings(BaseModel):
    provider: Literal["ollama", "openai_compatible", "stub"] = "ollama"
    model: str = "qwen2.5:3b-instruct-q4_K_M"
    base_url: str = "http://127.0.0.1:11434"
    api_key: str = ""  # for openai_compatible / cloud stubs
    temperature: float = 0.4
    max_tokens: int = 512
    num_ctx: int = 4096


class TTSSettings(BaseModel):
    provider: Literal["piper", "kokoro", "stub"] = "piper"
    voice: str = "en_US-amy-medium"
    sample_rate: int = 22050
    speed: float = 1.0


class MemorySettings(BaseModel):
    provider: Literal["sqlite", "chroma", "stub"] = "sqlite"
    db_path: str = "data/sutradhar.db"
    short_term_turns: int = 12
    retrieve_k: int = 4


class TransportSettings(BaseModel):
    default: Literal["websocket", "webrtc", "telephony_sim"] = "websocket"


class ObsSettings(BaseModel):
    metrics_enabled: bool = True
    metrics_port: int = 9100
    tracing_enabled: bool = False
    otlp_endpoint: str = "http://127.0.0.1:4317"
    service_name: str = "sutradhar"


class ReliabilitySettings(BaseModel):
    stage_timeout_ms: int = 8000
    retry_max_attempts: int = 2
    retry_base_ms: int = 100
    circuit_fail_threshold: int = 5
    circuit_reset_ms: int = 10000
    failover_enabled: bool = True


class BackendSettings(BaseModel):
    base_url: str = "http://127.0.0.1:8090"


class Settings(BaseSettings):
    """Root configuration object. Access via :func:`get_settings`."""

    model_config = SettingsConfigDict(
        env_prefix="SUTRADHAR_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    env: Literal["local", "ci", "prod"] = "local"
    log_level: LogLevel = "INFO"
    log_json: bool = False
    host: str = "127.0.0.1"
    port: int = 8080

    audio: AudioSettings = Field(default_factory=AudioSettings)
    vad: VADSettings = Field(default_factory=VADSettings)
    stt: STTSettings = Field(default_factory=STTSettings)
    turn: TurnSettings = Field(default_factory=TurnSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    tts: TTSSettings = Field(default_factory=TTSSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    transport: TransportSettings = Field(default_factory=TransportSettings)
    obs: ObsSettings = Field(default_factory=ObsSettings)
    reliability: ReliabilitySettings = Field(default_factory=ReliabilitySettings)
    backend: BackendSettings = Field(default_factory=BackendSettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton (cached)."""
    return Settings()


def reload_settings() -> Settings:
    """Clear the cache and re-read settings (used by tests)."""
    get_settings.cache_clear()
    return get_settings()
