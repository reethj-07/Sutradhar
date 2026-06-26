"""Streaming pipeline orchestration (PRD §5, §6.2). Skeleton; built in M1.

The pipeline wires the async stages — Transport -> VAD -> STT -> TurnDetector ->
Orchestrator(LLM) -> TTS -> Transport — over bounded queues with explicit
backpressure and cancellation. Each stage runs as an independent task; the turn
engine cancels in-flight LLM/TTS work on barge-in. Stitched together in M1/M2.
"""

from __future__ import annotations

from dataclasses import dataclass

from sutradhar.core.session import Session
from sutradhar.interfaces import LLM, STT, TTS, VAD, TurnDetector


@dataclass(slots=True)
class PipelineComponents:
    """The swappable components a pipeline runs with (resolved from config)."""

    vad: VAD
    stt: STT
    turn: TurnDetector
    llm: LLM
    tts: TTS


class Pipeline:
    """Runs the half-duplex streaming loop for one session. Implemented in M1."""

    def __init__(self, session: Session, components: PipelineComponents) -> None:
        self.session = session
        self.components = components

    async def run(self) -> None:  # pragma: no cover - M1
        raise NotImplementedError("Pipeline.run is implemented in M1")
