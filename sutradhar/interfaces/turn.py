"""TurnDetector interface — endpointing / predictive turn detection (PRD §6.3, §9).

Hybrid policy: acoustic (Silero trailing-silence) + semantic (is the transcript
a complete utterance?). The detector observes the evolving turn state and
decides whether the user has finished, exposing the signals needed to track
false-early / false-late endpoint rates (PRD §9.1, K3).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from sutradhar.core.types import TranscriptChunk, VADResult


@dataclass(frozen=True, slots=True)
class TurnContext:
    """Evidence the detector reasons over for the current (in-progress) turn."""

    transcript: str
    is_speech: bool
    last_vad: VADResult | None
    trailing_silence_ms: float
    utterance_ms: float
    partials: tuple[TranscriptChunk, ...] = ()


@dataclass(frozen=True, slots=True)
class EndpointDecision:
    """The detector's verdict on whether the user's turn is complete."""

    endpoint: bool
    confidence: float
    reason: str = ""
    # Decomposed signals for observability of endpoint accuracy (K3).
    acoustic: bool = False
    semantic: bool = False


@runtime_checkable
class TurnDetector(Protocol):
    """Decides when the user has finished speaking."""

    name: str

    async def start(self) -> None: ...

    def observe(self, ctx: TurnContext) -> EndpointDecision:
        """Return whether the current turn should be endpointed now."""
        ...

    def reset(self) -> None:
        """Reset between turns."""
        ...

    async def aclose(self) -> None: ...
