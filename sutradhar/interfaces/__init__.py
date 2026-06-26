"""Provider-agnostic interfaces (PRD §6.3).

Every model/provider in Sutradhar sits behind one of these abstractions, each
with at least two implementations (local-OSS default + a cloud/alt stub). The
pipeline depends only on these Protocols/ABCs — never on a concrete provider —
which is what makes components swappable purely via configuration (NFR2, NFR8).

    Interface     Local-OSS default     Swap target (stub)
    ---------     -----------------     ------------------
    Transport     WebSocket / Tel-sim   WebRTC, real SIP
    VAD           Silero                webrtcvad
    STT           faster-whisper        Vosk/Moonshine, Deepgram-stub
    TurnDetector  VAD+pause / hybrid    semantic / smart-turn
    LLM           Ollama (Qwen2.5-3B)   OpenAI/Anthropic-compatible-stub
    TTS           Piper                 Kokoro, ElevenLabs/Cartesia-stub
    MemoryStore   SQLite + sqlite-vec   Chroma, Redis
    Tracer        OpenTelemetry         —
"""

from __future__ import annotations

from sutradhar.interfaces.base import Component
from sutradhar.interfaces.llm import LLM
from sutradhar.interfaces.memory import MemoryRecord, MemoryStore
from sutradhar.interfaces.stt import STT
from sutradhar.interfaces.tools import Tool, ToolRegistry
from sutradhar.interfaces.tracer import Span, Tracer
from sutradhar.interfaces.transport import Transport
from sutradhar.interfaces.tts import TTS
from sutradhar.interfaces.turn import EndpointDecision, TurnDetector
from sutradhar.interfaces.vad import VAD

__all__ = [
    "LLM",
    "STT",
    "TTS",
    "VAD",
    "Component",
    "EndpointDecision",
    "MemoryRecord",
    "MemoryStore",
    "Span",
    "Tool",
    "ToolRegistry",
    "Tracer",
    "Transport",
    "TurnDetector",
]
