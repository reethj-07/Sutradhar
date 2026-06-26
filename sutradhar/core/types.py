"""Domain types — the shared vocabulary spoken by every pipeline stage.

These are deliberately small, immutable-ish dataclasses (frozen where it is
cheap) so they are easy to log, trace and reason about. Audio is carried as
raw little-endian 16-bit PCM (`bytes`) plus its sample rate; we avoid numpy in
the type layer so this module imports instantly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal


# ---------------------------------------------------------------------------
# Turn-taking state machine (PRD §9.3)
# ---------------------------------------------------------------------------
class TurnState(StrEnum):
    """States of one conversation, owned by the dialogue state machine.

    IDLE -> LISTENING -> THINKING -> SPEAKING -> (INTERRUPTED) -> LISTENING ...
    """

    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    INTERRUPTED = "interrupted"
    CLOSED = "closed"


class Stage(StrEnum):
    """Pipeline stages, used for latency marks, metrics labels and tracing."""

    TRANSPORT_IN = "transport_in"
    VAD = "vad"
    STT = "stt"
    TURN = "turn"
    LLM = "llm"
    TTS = "tts"
    TRANSPORT_OUT = "transport_out"
    VOICE_TO_VOICE = "voice_to_voice"


class Role(StrEnum):
    """Chat roles for the LLM message history."""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class AudioFrame:
    """A fixed-size chunk of inbound audio (mono, 16-bit PCM, little-endian).

    Frames flow Transport -> VAD/STT. `seq` is monotonic per session and
    `timestamp_ms` is a monotonic capture time used for latency accounting.
    """

    pcm: bytes
    sample_rate: int
    seq: int = 0
    timestamp_ms: float = 0.0
    num_channels: int = 1

    @property
    def num_samples(self) -> int:
        return len(self.pcm) // (2 * self.num_channels)

    @property
    def duration_ms(self) -> float:
        if self.sample_rate == 0:
            return 0.0
        return 1000.0 * self.num_samples / self.sample_rate


@dataclass(frozen=True, slots=True)
class AudioChunk:
    """A chunk of synthesized outbound audio (mono, 16-bit PCM)."""

    pcm: bytes
    sample_rate: int
    seq: int = 0
    is_final: bool = False
    text: str = ""  # the text this chunk renders (for truncation accounting)

    @property
    def num_samples(self) -> int:
        return len(self.pcm) // 2

    @property
    def duration_ms(self) -> float:
        if self.sample_rate == 0:
            return 0.0
        return 1000.0 * self.num_samples / self.sample_rate


# ---------------------------------------------------------------------------
# VAD
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class VADResult:
    """Per-frame voice-activity decision."""

    is_speech: bool
    probability: float
    timestamp_ms: float = 0.0


# ---------------------------------------------------------------------------
# STT
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Word:
    """An optional word-level timing from the STT engine."""

    text: str
    start_ms: float
    end_ms: float
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class TranscriptChunk:
    """A partial or final transcript emitted by the STT stream.

    Partials update in place (same `turn_seq`), the final closes the utterance.
    """

    text: str
    is_final: bool
    confidence: float = 1.0
    start_ms: float = 0.0
    end_ms: float = 0.0
    turn_seq: int = 0
    words: tuple[Word, ...] = ()


# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class ToolCall:
    """A tool/function call requested by the LLM."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolResult:
    """The result of executing a :class:`ToolCall`, fed back to the LLM."""

    id: str
    name: str
    content: str
    ok: bool = True


LLMEventKind = Literal["token", "tool_call", "done"]


@dataclass(frozen=True, slots=True)
class LLMResponseEvent:
    """One event in the streaming LLM response: a token, a tool call, or done."""

    kind: LLMEventKind
    token: str = ""
    tool_call: ToolCall | None = None
    finish_reason: str | None = None


@dataclass(slots=True)
class Message:
    """A single message in the rolling conversation history."""

    role: Role
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None

    def to_openai(self) -> dict[str, Any]:
        """Render in the OpenAI/Ollama chat message shape."""
        msg: dict[str, Any] = {"role": self.role.value, "content": self.content}
        if self.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments},
                }
                for tc in self.tool_calls
            ]
        if self.tool_call_id is not None:
            msg["tool_call_id"] = self.tool_call_id
        if self.name is not None:
            msg["name"] = self.name
        return msg


# ---------------------------------------------------------------------------
# Session lifecycle (PRD §6.2)
# ---------------------------------------------------------------------------
class SessionEventType(StrEnum):
    """Transport- and pipeline-level session signals."""

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    SPEECH_STARTED = "speech_started"
    SPEECH_ENDED = "speech_ended"
    ENDPOINT = "endpoint"
    BARGE_IN = "barge_in"
    AGENT_SPEAKING = "agent_speaking"
    AGENT_DONE = "agent_done"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class SessionEvent:
    """A control-plane event on a session (distinct from audio data-plane)."""

    type: SessionEventType
    session_id: str
    turn_id: str | None = None
    timestamp_ms: float = 0.0
    detail: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Latency accounting (PRD §8) — voice-to-voice is the metric of record.
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class LatencyMark:
    """A single stage's measured latency within one turn, in milliseconds."""

    stage: Stage
    started_ms: float
    ended_ms: float

    @property
    def elapsed_ms(self) -> float:
        return self.ended_ms - self.started_ms
