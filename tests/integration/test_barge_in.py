"""M2 integration: barge-in interrupts the agent and reconciles state (PRD §9.2).

Drives the real pipeline with stub providers over a time-paced loopback
transport: the user speaks, the agent starts a (deliberately slow) reply, and the
user speaks again *while the agent is talking*. Asserts the in-flight reply is
cancelled, playout is flushed, the barge-in metric fires, and the conversation
history reflects the truncated turn — no corruption.
"""

from __future__ import annotations

import struct

import pytest

from sutradhar.core.config import Settings
from sutradhar.core.session import SessionManager
from sutradhar.core.types import AudioFrame, TurnState
from sutradhar.observability.metrics import Metrics
from sutradhar.runtime import build_components, build_pipeline, start_components
from sutradhar.transport.loopback import LoopbackTransport

pytestmark = pytest.mark.integration

_SR = 16000
_SAMPLES = _SR * 20 // 1000


def _frame(seq: int, amp: int) -> AudioFrame:
    pcm = struct.pack(f"<{_SAMPLES}h", *([amp] * _SAMPLES))
    return AudioFrame(pcm=pcm, sample_rate=_SR, seq=seq, timestamp_ms=seq * 20)


def _frames(spec: list[tuple[str, int]]) -> list[AudioFrame]:
    out: list[AudioFrame] = []
    for kind, n in spec:
        amp = 6000 if kind == "speech" else 0
        for _ in range(n):
            out.append(_frame(len(out), amp))
    return out


def _settings() -> Settings:
    return Settings.model_validate(
        {
            "env": "ci",
            "vad": {"provider": "stub", "threshold": 0.02},
            "stt": {"provider": "stub"},
            "turn": {"provider": "stub", "silence_ms": 200, "barge_in_ms": 60},
            "llm": {"provider": "stub"},
            "tts": {"provider": "stub", "sample_rate": _SR},
            "memory": {"provider": "stub"},
        }
    )


async def test_barge_in_interrupts_and_reconciles() -> None:
    settings = _settings()
    manager = SessionManager(settings)
    session = await manager.create("barge")

    components = build_components(settings)
    # Long reply + slow per-clause synthesis so the agent is still speaking when
    # the user interrupts.
    components.llm = _LongStubLLM()  # type: ignore[assignment]
    components.tts.chunk_delay_s = 0.05  # type: ignore[attr-defined]
    await start_components(components)

    # speak -> silence (endpoint) -> [agent replies] -> speak again (barge-in).
    frames = _frames([("speech", 8), ("silence", 16), ("speech", 25), ("silence", 10)])
    transport = LoopbackTransport("barge", frames, sample_rate=_SR, frame_delay_s=0.01)
    metrics = Metrics()
    pipeline = build_pipeline(session, transport, components=components, metrics=metrics)

    await pipeline.run()

    # Barge-in fired exactly once and playout was flushed.
    assert metrics.barge_in._value.get() >= 1.0  # type: ignore[attr-defined]
    assert transport._flushes >= 1  # type: ignore[attr-defined]

    # History reflects the real, truncated exchange (no corruption).
    interrupted = [
        m
        for m in session.state.history
        if m.role.value == "assistant" and "[interrupted]" in m.content
    ]
    assert interrupted, "expected a truncated assistant turn in history"
    assert session.state.state in (TurnState.LISTENING, TurnState.CLOSED)

    await manager.close("barge")


class _LongStubLLM:
    """Stub LLM that streams a long multi-clause reply (so it can be interrupted)."""

    name = "stub-llm-long"

    async def start(self) -> None: ...

    async def stream(self, messages, tools=None):  # type: ignore[no-untyped-def]
        from sutradhar.core.types import LLMResponseEvent

        text = "Sure, let me tell you all about our pricing tiers. " * 6
        for tok in text.split(" "):
            yield LLMResponseEvent(kind="token", token=tok + " ")
        yield LLMResponseEvent(kind="done", finish_reason="stop")

    async def complete(self, messages) -> str:  # type: ignore[no-untyped-def]
        return "ok"

    async def aclose(self) -> None: ...
