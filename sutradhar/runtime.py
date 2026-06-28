"""Composition root — assemble a runnable pipeline from configuration.

Keeps the wiring (which concrete providers, the orchestrator, memory, tools) in
one place so transports/CLI/tests build a `Pipeline` the same way. Nothing here
imports heavy ML libs at module load; providers are resolved lazily by the
factory based on `Settings`.
"""

from __future__ import annotations

import asyncio
import contextlib

from sutradhar.core.config import Settings
from sutradhar.core.pipeline import Pipeline, PipelineComponents
from sutradhar.core.session import Session, SessionManager
from sutradhar.dialogue.memory import ConversationMemory
from sutradhar.dialogue.orchestrator import DialogueOrchestrator
from sutradhar.dialogue.prompts import system_prompt
from sutradhar.dialogue.registry import InMemoryToolRegistry
from sutradhar.interfaces.tools import ToolRegistry
from sutradhar.interfaces.tracer import Tracer
from sutradhar.interfaces.transport import Transport
from sutradhar.observability.metrics import Metrics
from sutradhar.providers import (
    build_llm,
    build_stt,
    build_tts,
    build_turn_detector,
    build_vad,
)


def build_components(settings: Settings) -> PipelineComponents:
    """Resolve the swappable pipeline components from config."""
    return PipelineComponents(
        vad=build_vad(settings),
        stt=build_stt(settings),
        turn=build_turn_detector(settings),
        llm=build_llm(settings),
        tts=build_tts(settings),
    )


async def start_components(components: PipelineComponents) -> None:
    """Initialize every component (load models / open connections)."""
    await components.vad.start()
    await components.stt.start()
    await components.turn.start()
    await components.llm.start()
    await components.tts.start()


async def aclose_components(components: PipelineComponents) -> None:
    """Release every component's resources (best-effort, never raising)."""
    for comp in (
        components.vad,
        components.stt,
        components.turn,
        components.llm,
        components.tts,
    ):
        # Fail soft on teardown — a provider that errors while closing must not
        # prevent the others from releasing their resources.
        with contextlib.suppress(Exception):
            await comp.aclose()


def build_pipeline(
    session: Session,
    transport: Transport,
    *,
    components: PipelineComponents | None = None,
    tools: ToolRegistry | None = None,
    metrics: Metrics | None = None,
    tracer: Tracer | None = None,
    vertical: str = "lead_qualification",
) -> Pipeline:
    """Assemble a `Pipeline` for `session` over `transport`."""
    settings = session.settings
    components = components or build_components(settings)
    memory = ConversationMemory(
        session.session_id, short_term_turns=settings.memory.short_term_turns
    )
    orchestrator = DialogueOrchestrator(
        components.llm,
        session.state,
        memory,
        tools or InMemoryToolRegistry(),
        system_prompt=system_prompt(vertical),
    )
    return Pipeline(session, components, transport, orchestrator, metrics=metrics, tracer=tracer)


class SessionRuntime:
    """Process-wide holder that loads provider models once and shares them.

    Models (Whisper on GPU, Piper, the Ollama client) are expensive to load, so
    they are built and started lazily on the first session and reused. M1 targets
    one real-time conversation at a time; the concurrency ceiling and per-session
    provider isolation are addressed in M5.
    """

    def __init__(self, settings: Settings, *, max_sessions: int = 4) -> None:
        self.settings = settings
        self.manager = SessionManager(settings, max_sessions=max_sessions)
        self.components: PipelineComponents | None = None
        self._lock = asyncio.Lock()

    async def ensure_components(self) -> PipelineComponents:
        async with self._lock:
            if self.components is None:
                comps = build_components(self.settings)
                await start_components(comps)
                self.components = comps
            return self.components

    async def aclose(self) -> None:
        await self.manager.close_all()
        if self.components is not None:
            await aclose_components(self.components)
            self.components = None
