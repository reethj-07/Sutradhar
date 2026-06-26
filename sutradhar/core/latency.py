"""Per-turn latency accounting (PRD §8, PR5, K1).

The metric of record is **voice-to-voice latency**: end-of-user-speech (endpoint
detected) to the first agent audio byte. A :class:`LatencyTracker` collects a
mark per stage within a turn, computes voice-to-voice, and pushes everything to
Prometheus so every stage's latency is visible per turn in Grafana.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from sutradhar.core.clock import Clock, MonotonicClock
from sutradhar.core.types import LatencyMark, Stage

if TYPE_CHECKING:
    from sutradhar.observability.metrics import Metrics


@dataclass(slots=True)
class TurnLatency:
    """All latency marks for one turn plus the derived voice-to-voice figure."""

    turn_id: str
    marks: dict[Stage, LatencyMark] = field(default_factory=dict)
    endpoint_ms: float | None = None
    first_audio_ms: float | None = None

    @property
    def voice_to_voice_ms(self) -> float | None:
        if self.endpoint_ms is None or self.first_audio_ms is None:
            return None
        return self.first_audio_ms - self.endpoint_ms

    def as_dict(self) -> dict[str, float]:
        out = {stage.value: m.elapsed_ms for stage, m in self.marks.items()}
        v2v = self.voice_to_voice_ms
        if v2v is not None:
            out["voice_to_voice"] = v2v
        return out


class LatencyTracker:
    """Accumulates stage marks for a turn and reports them.

    Usage::

        lt = tracker.begin_turn("turn-1")
        with tracker.stage(Stage.STT, provider="faster-whisper"):
            ...
        tracker.mark_endpoint()           # end-of-user-speech reference
        tracker.mark_first_audio()        # first synthesized byte
        report = tracker.end_turn()
    """

    def __init__(self, clock: Clock | None = None, metrics: Metrics | None = None) -> None:
        self._clock = clock or MonotonicClock()
        self._metrics = metrics
        self._turn: TurnLatency | None = None
        self._open: dict[Stage, float] = {}

    @property
    def current(self) -> TurnLatency | None:
        return self._turn

    def begin_turn(self, turn_id: str) -> TurnLatency:
        self._turn = TurnLatency(turn_id=turn_id)
        self._open.clear()
        return self._turn

    def start_stage(self, stage: Stage) -> None:
        self._open[stage] = self._clock.now_ms()

    def end_stage(self, stage: Stage, provider: str = "") -> None:
        if self._turn is None or stage not in self._open:
            return
        started = self._open.pop(stage)
        ended = self._clock.now_ms()
        self._turn.marks[stage] = LatencyMark(stage=stage, started_ms=started, ended_ms=ended)
        if self._metrics is not None:
            self._metrics.observe_stage(stage.value, provider or "?", (ended - started) / 1000.0)

    def stage(self, stage: Stage, provider: str = "") -> _StageTimer:
        return _StageTimer(self, stage, provider)

    def mark_endpoint(self) -> None:
        """Mark end-of-user-speech — the start of the voice-to-voice clock."""
        if self._turn is not None:
            self._turn.endpoint_ms = self._clock.now_ms()

    def mark_first_audio(self) -> None:
        """Mark the first agent audio byte — the end of the voice-to-voice clock."""
        if self._turn is not None and self._turn.first_audio_ms is None:
            self._turn.first_audio_ms = self._clock.now_ms()

    def end_turn(self) -> TurnLatency | None:
        turn = self._turn
        if turn is not None and self._metrics is not None:
            v2v = turn.voice_to_voice_ms
            if v2v is not None:
                self._metrics.voice_to_voice.observe(v2v / 1000.0)
                self._metrics.turns.inc()
        self._turn = None
        return turn


class _StageTimer:
    """Context manager returned by :meth:`LatencyTracker.stage`."""

    __slots__ = ("_provider", "_stage", "_tracker")

    def __init__(self, tracker: LatencyTracker, stage: Stage, provider: str) -> None:
        self._tracker = tracker
        self._stage = stage
        self._provider = provider

    def __enter__(self) -> _StageTimer:
        self._tracker.start_stage(self._stage)
        return self

    def __exit__(self, *exc: object) -> None:
        self._tracker.end_stage(self._stage, self._provider)
