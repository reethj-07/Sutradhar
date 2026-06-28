"""M3 capstone: a task completes via tool calls and memory persists (PRD §10, §17).

Drives the real pipeline with stub audio providers + a scripted tool-calling LLM,
the real CRM tools (against the in-process backend via ASGI), and the real SQLite
memory store. Asserts: the agent calls a tool, books via the backend, replies, and
the exchange is persisted to long-term memory.
"""

from __future__ import annotations

import struct
from collections.abc import AsyncIterator, Sequence
from typing import Any

import httpx
import pytest

from mock_backend.app import create_app
from sutradhar.core.config import Settings
from sutradhar.core.session import SessionManager
from sutradhar.core.types import AudioFrame, LLMResponseEvent, Message, Role, ToolCall
from sutradhar.dialogue.tools_crm import build_crm_tools
from sutradhar.providers.memory.sqlite_store import SqliteMemoryStore
from sutradhar.runtime import build_components, build_pipeline, start_components
from sutradhar.transport.loopback import LoopbackTransport

pytestmark = pytest.mark.integration

_SR = 16000
_SAMPLES = _SR * 20 // 1000


def _frames(speech: int, silence: int) -> list[AudioFrame]:
    out = [
        AudioFrame(pcm=struct.pack(f"<{_SAMPLES}h", *([6000] * _SAMPLES)), sample_rate=_SR)
        for _ in range(speech)
    ]
    out += [
        AudioFrame(pcm=struct.pack(f"<{_SAMPLES}h", *([0] * _SAMPLES)), sample_rate=_SR)
        for _ in range(silence)
    ]
    return out


class _BookingLLM:
    """Round 1: book a slot. Round 2: confirm in words."""

    name = "booking"

    def __init__(self) -> None:
        self.calls = 0

    async def start(self) -> None: ...
    async def aclose(self) -> None: ...
    async def complete(self, messages: Sequence[Message]) -> str:
        return ""

    async def stream(
        self, messages: Sequence[Message], tools: Sequence[dict[str, Any]] | None = None
    ) -> AsyncIterator[LLMResponseEvent]:
        self.calls += 1
        if self.calls == 1:
            yield LLMResponseEvent(
                kind="tool_call",
                tool_call=ToolCall(
                    id="b1",
                    name="book_slot",
                    arguments={"customer_id": 1, "day": "Tuesday", "time": "10:00"},
                ),
            )
            yield LLMResponseEvent(kind="done")
        else:
            assert any(m.role is Role.TOOL for m in messages)
            for tok in ["You're", "booked", "for", "Tuesday", "at", "ten."]:
                yield LLMResponseEvent(kind="token", token=tok + " ")
            yield LLMResponseEvent(kind="done")


async def test_task_completes_via_tools_and_memory_persists() -> None:
    settings = Settings.model_validate(
        {
            "env": "ci",
            "vad": {"provider": "stub", "threshold": 0.02},
            "stt": {"provider": "stub"},
            "turn": {"provider": "stub", "silence_ms": 200},
            "llm": {"provider": "stub"},
            "tts": {"provider": "stub", "sample_rate": _SR},
            "memory": {"provider": "sqlite", "db_path": ":memory:"},
            "backend": {"base_url": "http://crm"},
        }
    )
    backend = create_app(":memory:")

    async with (
        backend.router.lifespan_context(backend),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=backend), base_url="http://crm"
        ) as crm_client,
    ):
        manager = SessionManager(settings)
        session = await manager.create("m3")

        components = build_components(settings)
        components.llm = _BookingLLM()  # type: ignore[assignment]
        await start_components(components)

        store = SqliteMemoryStore(settings)
        await store.start()
        tools = build_crm_tools(settings, client=crm_client)

        transport = LoopbackTransport("m3", _frames(10, 25), sample_rate=_SR)
        pipeline = build_pipeline(
            session, transport, components=components, tools=tools, memory_store=store
        )
        await pipeline.run()

        # The agent produced a spoken confirmation built from the tool result.
        reply = next(
            (m.content for m in reversed(session.state.history) if m.role is Role.ASSISTANT),
            "",
        )
        assert "booked" in reply.lower()

        # The slot is actually booked in the backend (task completed via tool call).
        slot = await crm_client.post(
            "/tools/book_slot", json={"customer_id": 2, "day": "Tuesday", "time": "10:00"}
        )
        assert slot.json()["booked"] is False  # already taken by the agent's booking

        # The exchange persisted to long-term memory.
        recalled = await store.retrieve("m3", "booked Tuesday", k=5)
        assert any("booked" in r.text.lower() or "agent" in r.text.lower() for r in recalled)

        await store.aclose()
        await manager.close("m3")
