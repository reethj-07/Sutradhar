"""Hybrid turn detector (PRD §9.1).

Fuses two signals into one endpoint decision:

* **Acoustic** — trailing silence past a threshold proposes an endpoint
  (implemented from M0; this is the ``vad_pause`` policy).
* **Semantic** — a lightweight classifier judging whether the transcript is a
  complete utterance, to cut premature endpoints on natural pauses and reduce
  lag on clearly-finished sentences. M0 ships a fast heuristic; M2 replaces it
  with a trained smart-turn-style classifier behind the same call.

Policy fusion is tunable and exposes its decomposed signals so false-early /
false-late endpoint rates (K3) can be measured.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sutradhar.interfaces.turn import EndpointDecision, TurnContext

if TYPE_CHECKING:
    from sutradhar.core.config import Settings

# Tokens that strongly imply the speaker is *not* done (M0 heuristic).
_CONTINUATION_HINTS = frozenset(
    {"and", "but", "so", "because", "or", "the", "a", "an", "to", "my", "i", "for"}
)
# Sentence-final punctuation the STT may emit.
_TERMINALS = (".", "?", "!")


class HybridTurnDetector:
    """Acoustic + semantic endpoint detector with tunable fusion."""

    name = "hybrid-turn"

    def __init__(self, settings: Settings) -> None:
        self.silence_ms = settings.turn.silence_ms
        self.max_utterance_ms = settings.turn.max_utterance_ms
        self.semantic_enabled = (
            settings.turn.semantic_enabled and settings.turn.provider == "hybrid"
        )
        self.min_chars = settings.turn.min_endpoint_chars

    async def start(self) -> None: ...

    def _semantic_complete(self, transcript: str) -> float:
        """Heuristic completeness score in [0, 1] (M0; replaced by a model in M2)."""
        text = transcript.strip()
        if not text:
            return 0.0
        if text.endswith(_TERMINALS):
            return 0.95
        last = text.split()[-1].lower().strip(",;:")
        if last in _CONTINUATION_HINTS:
            return 0.1  # clearly mid-thought
        # A few words with no trailing connective reads as a likely complete clause.
        words = text.split()
        return 0.7 if len(words) >= 3 else 0.4

    def observe(self, ctx: TurnContext) -> EndpointDecision:
        text = ctx.transcript.strip()
        acoustic = (
            not ctx.is_speech
            and ctx.trailing_silence_ms >= self.silence_ms
            and len(text) >= self.min_chars
        )

        # Hard stop: utterance ran too long — endpoint regardless.
        if ctx.utterance_ms >= self.max_utterance_ms and text:
            return EndpointDecision(
                endpoint=True,
                confidence=0.6,
                reason="max_utterance",
                acoustic=acoustic,
                semantic=False,
            )

        if not self.semantic_enabled:
            return EndpointDecision(
                endpoint=acoustic,
                confidence=1.0 if acoustic else 0.0,
                reason="acoustic" if acoustic else "",
                acoustic=acoustic,
            )

        sem_score = self._semantic_complete(text)
        semantic = sem_score >= 0.6

        # Fusion: endpoint when acoustic silence is met AND the utterance looks
        # complete; OR a strong semantic terminal even on a shorter pause.
        endpoint = (acoustic and semantic) or (
            sem_score >= 0.9 and ctx.trailing_silence_ms >= self.silence_ms * 0.5 and bool(text)
        )
        confidence = round(min(1.0, 0.5 * float(acoustic) + 0.5 * sem_score), 3)
        reason = "acoustic+semantic" if endpoint else ("waiting" if text else "")
        return EndpointDecision(
            endpoint=endpoint,
            confidence=confidence,
            reason=reason,
            acoustic=acoustic,
            semantic=semantic,
        )

    def reset(self) -> None: ...

    async def aclose(self) -> None: ...
