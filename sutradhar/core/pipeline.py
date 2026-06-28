"""Streaming pipeline with turn-taking + barge-in (PRD §5, §6.2, §9; M1/M2).

State-machine-driven **single frame loop**: exactly one consumer reads inbound
audio and dispatches each frame by turn state.

* **LISTENING** — feed VAD + STT (STT runs as its own pump task so partials are
  available mid-utterance); the turn detector decides the endpoint. On endpoint
  the agent reply is launched as a background task and the turn switches to
  SPEAKING.
* **SPEAKING** — the *same* loop keeps running VAD on inbound audio to detect
  **barge-in** (PRD §9.2). On confirmed user speech it cancels the in-flight
  LLM + TTS (shared :class:`CancellationToken`), flushes playout (≤200 ms stop),
  and reconciles state via ``state.barge_in()`` so history reflects the truncated
  turn — then resumes LISTENING.

Using one consumer (never cancelling a pending ``__anext__`` on the frame
generator) is deliberate: a second consumer or a cancelled read would corrupt the
async generator. The agent reply is the cancellable background task instead.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from dataclasses import dataclass

from sutradhar.core.cancellation import CancellationToken, OperationCancelled
from sutradhar.core.config import AudioSettings
from sutradhar.core.queues import BoundedStream
from sutradhar.core.session import Session
from sutradhar.core.types import AudioFrame, Stage, TurnState, VADResult
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
    """Runs the streaming loop (listen → speak, interruptible) for one session."""

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
        self.barge_in_ms = session.settings.turn.barge_in_ms
        self._stt_in_max = 512

        # Per-phase working state.
        self._stt_in: BoundedStream[AudioFrame] | None = None
        self._stt_task: asyncio.Task[None] | None = None
        self._latest: dict[str, str] = {"partial": "", "final": ""}
        self._started = False
        self._trailing = 0.0
        self._utt = 0.0
        self._listen_turn_id = ""
        self._resp_turn_id = ""
        self._cancel: CancellationToken | None = None
        self._respond_task: asyncio.Task[None] | None = None
        self._barge_ms = 0.0

    async def run(self) -> None:
        """Consume the session's audio, listening and replying turn by turn."""
        bind_context(session_id=self.session.session_id)
        self._begin_listening()
        async for frame in self.transport.recv_audio():
            res = self.components.vad.detect(frame)
            if self.state.state is TurnState.SPEAKING:
                await self._on_speaking_frame(frame, res)
            else:
                await self._on_listening_frame(frame, res)
        await self._on_stream_end()

    # -- LISTENING --------------------------------------------------------
    def _begin_listening(self) -> None:
        self.components.vad.reset()
        self.components.turn.reset()
        if self.state.state in (TurnState.IDLE, TurnState.LISTENING):
            self.state.begin_user_turn()
        self._listen_turn_id = uuid.uuid4().hex[:8]
        self.latency.begin_turn(self._listen_turn_id)
        self._stt_in = BoundedStream(self._stt_in_max, name="stt-in")
        self._latest = {"partial": "", "final": ""}
        self._stt_task = asyncio.create_task(self._pump_stt(self._stt_in, self._latest))
        self._started = False
        self._trailing = 0.0
        self._utt = 0.0

    async def _pump_stt(self, stt_in: BoundedStream[AudioFrame], latest: dict[str, str]) -> None:
        async for chunk in self.components.stt.stream(stt_in):
            if chunk.is_final:
                latest["final"] = chunk.text
            else:
                latest["partial"] = chunk.text

    async def _on_listening_frame(self, frame: AudioFrame, res: VADResult) -> None:
        if res.is_speech:
            self._started = True
            self._trailing = 0.0
        elif self._started:
            self._trailing += frame.duration_ms
        if not self._started or self._stt_in is None:
            return
        await self._stt_in.put(frame)
        await asyncio.sleep(0)  # let the STT pump consume the frame
        self._utt += frame.duration_ms
        ctx = TurnContext(
            transcript=self._latest["partial"] or self._latest["final"],
            is_speech=res.is_speech,
            last_vad=res,
            trailing_silence_ms=self._trailing,
            utterance_ms=self._utt,
        )
        if self.components.turn.observe(ctx).endpoint:
            if self.metrics is not None:
                self.metrics.endpoint_decisions.labels(outcome="fired").inc()
            await self._endpoint()

    async def _endpoint(self) -> None:
        self.latency.mark_endpoint()
        with self.latency.stage(Stage.STT, provider=getattr(self.components.stt, "name", "?")):
            if self._stt_in is not None:
                self._stt_in.close()
            await _drain(self._stt_task)
        self._stt_task = None
        transcript = (self._latest["final"] or self._latest["partial"]).strip()
        _log.info("user_utterance", turn_id=self._listen_turn_id, text=transcript)
        if not transcript:
            self._begin_listening()
            return
        # Launch the agent reply as a cancellable task and switch to SPEAKING.
        self.state.add_user_message(transcript)
        self.state.begin_thinking()
        self._resp_turn_id = uuid.uuid4().hex[:8]
        self._cancel = CancellationToken()
        self._barge_ms = 0.0
        self.components.vad.reset()  # fresh VAD state for barge-in monitoring
        self.state.begin_agent_turn(self._resp_turn_id)
        self.latency.start_stage(Stage.LLM)
        self._respond_task = asyncio.create_task(self._speak(transcript, self._cancel))

    # -- SPEAKING (barge-in monitoring) -----------------------------------
    async def _on_speaking_frame(self, frame: AudioFrame, res: VADResult) -> None:
        if self._respond_task is not None and self._respond_task.done():
            await self._finish_speaking()
            return
        if res.is_speech:
            self._barge_ms += frame.duration_ms
            if self._barge_ms >= self.barge_in_ms:
                await self._barge_in()
        else:
            self._barge_ms = max(0.0, self._barge_ms - frame.duration_ms)

    async def _speak(self, transcript: str, cancel: CancellationToken) -> None:
        clauses = self.orchestrator.respond(transcript, self.latency, cancel)
        first = True
        try:
            async for chunk in self.components.tts.stream(clauses):
                if cancel.cancelled:
                    break
                if not chunk.pcm:
                    continue
                if first:
                    first = False
                    self.latency.mark_first_audio()
                self.state.append_spoken(chunk.text)
                await self.transport.send_audio(chunk)
        except OperationCancelled:
            pass

    async def _finish_speaking(self) -> None:
        await _drain(self._respond_task)
        self._respond_task = None
        self.state.complete_agent_turn()
        reply = self.state.history[-1].content if self.state.history else ""
        _log.info("agent_reply", turn_id=self._resp_turn_id, text=reply)
        self._report_turn()
        self._begin_listening()

    async def _barge_in(self) -> None:
        if self._cancel is not None:
            self._cancel.cancel("barge-in")
        await self.transport.flush()  # client drops queued audio -> ≤200 ms stop
        await _drain(self._respond_task)
        self._respond_task = None
        record = self.state.barge_in()  # SPEAKING -> INTERRUPTED -> LISTENING, truncated
        if self.metrics is not None:
            self.metrics.barge_in.inc()
        self.tracer.event("barge_in", {"spoken": record.spoken_text})
        _log.info("barge_in", turn_id=self._resp_turn_id, spoken=record.spoken_text)
        self._report_turn()
        self._begin_listening()

    def _report_turn(self) -> None:
        report = self.latency.end_turn()
        if report is not None:
            _log.info(
                "turn_latency",
                turn_id=self._resp_turn_id,
                **{k: round(v, 1) for k, v in report.as_dict().items()},
            )

    async def _on_stream_end(self) -> None:
        # Finish a reply that was still in flight when the audio stream ended.
        if self.state.state is TurnState.SPEAKING and self._respond_task is not None:
            await _drain(self._respond_task)
            self._respond_task = None
            with contextlib.suppress(Exception):
                self.state.complete_agent_turn()
            self._report_turn()
        if self._stt_task is not None:
            if self._stt_in is not None:
                self._stt_in.close()
            await _drain(self._stt_task)
            self._stt_task = None


async def _drain(task: asyncio.Task[None] | None) -> None:
    if task is None:
        return
    try:
        await task
    except Exception as exc:  # fail soft — a dead stage must not crash the session
        _log.warning("task_failed", error=str(exc))
