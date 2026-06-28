"""Streaming half-duplex pipeline (PRD §5, §6.2, M1).

Wires the async stages — Transport -> VAD -> STT -> TurnDetector ->
Orchestrator(LLM) -> TTS -> Transport — for one session, over bounded queues with
explicit backpressure. STT runs as its own task fed by a bounded stream, so
partial transcripts are available *during* the utterance and the turn detector
can endpoint on the fused acoustic+semantic signal.

M1 is half-duplex (listen, then speak); barge-in (interrupting the agent while it
speaks) is layered on in M2 — the cancellation token is already threaded through
so that change is local. Every turn records per-stage and voice-to-voice latency.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass

from sutradhar.core.cancellation import CancellationToken
from sutradhar.core.config import AudioSettings
from sutradhar.core.queues import BoundedStream
from sutradhar.core.session import Session
from sutradhar.core.types import AudioFrame, Stage, TurnState
from sutradhar.dialogue.orchestrator import DialogueOrchestrator
from sutradhar.interfaces import LLM, STT, TTS, VAD, TurnDetector
from sutradhar.interfaces.tracer import Tracer
from sutradhar.interfaces.transport import Transport
from sutradhar.interfaces.turn import TurnContext
from sutradhar.observability.logging import bind_context, get_logger
from sutradhar.observability.metrics import Metrics
from sutradhar.observability.tracing import NoopTracer

_log = get_logger("core.pipeline")


@dataclass(slots=True)
class PipelineComponents:
    """The swappable components a pipeline runs with (resolved from config)."""

    vad: VAD
    stt: STT
    turn: TurnDetector
    llm: LLM
    tts: TTS


class Pipeline:
    """Runs the half-duplex streaming loop for one session."""

    def __init__(
        self,
        session: Session,
        components: PipelineComponents,
        transport: Transport,
        orchestrator: DialogueOrchestrator,
        *,
        metrics: Metrics | None = None,
        tracer: Tracer | None = None,
    ) -> None:
        self.session = session
        self.components = components
        self.transport = transport
        self.orchestrator = orchestrator
        self.state = session.state
        self.latency = session.latency
        self.metrics = metrics
        self.tracer: Tracer = tracer or NoopTracer()
        self.audio: AudioSettings = session.settings.audio
        self._stt_in_max = 512

    async def run(self) -> None:
        """Consume the session's audio, answering each user utterance in turn."""
        bind_context(session_id=self.session.session_id)
        frames = self.transport.recv_audio().__aiter__()
        while True:
            transcript = await self._listen(frames)
            if transcript is None:
                break
            await self._respond(transcript)

    # -- listen: frames -> VAD -> STT -> endpoint -------------------------
    async def _listen(self, frames: AsyncIterator[AudioFrame]) -> str | None:
        vad, stt, turn = self.components.vad, self.components.stt, self.components.turn
        vad.reset()
        turn.reset()
        if self.state.state in (TurnState.IDLE, TurnState.LISTENING):
            self.state.begin_user_turn()

        turn_id = uuid.uuid4().hex[:8]
        self.latency.begin_turn(turn_id)

        stt_in: BoundedStream[AudioFrame] = BoundedStream(self._stt_in_max, name="stt-in")
        latest = {"partial": "", "final": ""}

        async def pump_stt() -> None:
            async for chunk in stt.stream(stt_in):
                if chunk.is_final:
                    latest["final"] = chunk.text
                else:
                    latest["partial"] = chunk.text

        stt_task = asyncio.create_task(pump_stt())
        started = False
        trailing_ms = 0.0
        utterance_ms = 0.0
        endpoint = False

        with self.tracer.span("turn.listen", {"turn_id": turn_id}):
            async for frame in frames:
                res = vad.detect(frame)
                if res.is_speech:
                    started = True
                    trailing_ms = 0.0
                elif started:
                    trailing_ms += frame.duration_ms

                if not started:
                    continue

                await stt_in.put(frame)
                # Yield so the STT pump task can consume the frame and update the
                # partial transcript before the turn detector reads it.
                await asyncio.sleep(0)
                utterance_ms += frame.duration_ms
                ctx = TurnContext(
                    transcript=latest["partial"] or latest["final"],
                    is_speech=res.is_speech,
                    last_vad=res,
                    trailing_silence_ms=trailing_ms,
                    utterance_ms=utterance_ms,
                )
                if turn.observe(ctx).endpoint:
                    endpoint = True
                    if self.metrics is not None:
                        self.metrics.endpoint_decisions.labels(outcome="fired").inc()
                    break

        # End of utterance (endpoint) or end of audio stream.
        if not started:
            stt_in.close()
            await _drain(stt_task)
            return None

        self.latency.mark_endpoint()
        if endpoint:
            self.tracer.event("endpoint", {"utterance_ms": utterance_ms})
        with self.latency.stage(Stage.STT, provider=getattr(stt, "name", "?")):
            stt_in.close()
            await _drain(stt_task)
        transcript = (latest["final"] or latest["partial"]).strip()
        _log.info("user_utterance", turn_id=turn_id, text=transcript, endpoint=endpoint)
        return transcript or None

    # -- respond: LLM -> clauses -> TTS -> transport ----------------------
    async def _respond(self, transcript: str) -> None:
        self.state.add_user_message(transcript)
        turn_id = uuid.uuid4().hex[:8]
        self.state.begin_thinking()
        self.state.begin_agent_turn(turn_id)

        cancel = CancellationToken()  # M2 uses this to interrupt on barge-in
        self.latency.start_stage(Stage.LLM)
        clauses = self.orchestrator.respond(transcript, self.latency, cancel)

        first_audio = True
        with self.tracer.span("turn.respond", {"turn_id": turn_id}):
            async for chunk in self.components.tts.stream(clauses):
                if not chunk.pcm:
                    continue
                if first_audio:
                    first_audio = False
                    self.latency.mark_first_audio()
                self.state.append_spoken(chunk.text)
                await self.transport.send_audio(chunk)

        self.state.complete_agent_turn()
        reply = self.state.history[-1].content if self.state.history else ""
        _log.info("agent_reply", turn_id=turn_id, text=reply)
        report = self.latency.end_turn()
        if report is not None:
            _log.info(
                "turn_latency",
                turn_id=turn_id,
                **{k: round(v, 1) for k, v in report.as_dict().items()},
            )


async def _drain(task: asyncio.Task[None]) -> None:
    try:
        await task
    except Exception as exc:  # fail soft — a dead STT must not crash the session
        _log.warning("stt_task_failed", error=str(exc))
