"""Orchestrator streaming tool-calling loop (PRD §10)."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

from sutradhar.core.types import LLMResponseEvent, Message, Role, ToolCall, ToolResult
from sutradhar.dialogue.memory import ConversationMemory
from sutradhar.dialogue.orchestrator import DialogueOrchestrator
from sutradhar.dialogue.registry import InMemoryToolRegistry
from sutradhar.dialogue.state import TurnStateMachine
from sutradhar.interfaces.tools import Tool


class _ScriptedToolLLM:
    """Round 1: request a tool call. Round 2: stream a final answer."""

    name = "scripted"

    def __init__(self) -> None:
        self.calls = 0

    async def start(self) -> None: ...
    async def aclose(self) -> None: ...

    async def complete(self, messages: Sequence[Message]) -> str:
        return "ok"

    async def stream(
        self, messages: Sequence[Message], tools: Sequence[dict[str, Any]] | None = None
    ) -> AsyncIterator[LLMResponseEvent]:
        self.calls += 1
        if self.calls == 1:
            yield LLMResponseEvent(
                kind="tool_call",
                tool_call=ToolCall(id="c1", name="lookup_customer", arguments={"query": "Asha"}),
            )
            yield LLMResponseEvent(kind="done", finish_reason="tool_calls")
        else:
            # Should now see the tool result in the message thread.
            assert any(m.role is Role.TOOL for m in messages), "tool result not fed back"
            for tok in ["Found", "Asha", "Menon.", "How", "can", "I", "help?"]:
                yield LLMResponseEvent(kind="token", token=tok + " ")
            yield LLMResponseEvent(kind="done", finish_reason="stop")


def _registry(executed: list[str]) -> InMemoryToolRegistry:
    reg = InMemoryToolRegistry()

    async def handler(args: dict[str, Any]) -> ToolResult:
        executed.append(args.get("query", ""))
        return ToolResult(id="", name="", content='{"found": true, "name": "Asha Menon"}', ok=True)

    reg.register(Tool("lookup_customer", "look up a customer", {"type": "object"}, handler))
    return reg


async def test_tool_loop_executes_then_answers() -> None:
    executed: list[str] = []
    state = TurnStateMachine(session_id="t")
    state.begin_user_turn()
    state.add_user_message("look up Asha please")
    orch = DialogueOrchestrator(
        _ScriptedToolLLM(),  # type: ignore[arg-type]
        state,
        ConversationMemory("t"),
        _registry(executed),
        system_prompt="be helpful",
    )

    clauses = [c async for c in orch.respond("look up Asha please")]

    assert executed == ["Asha"]  # the tool ran with the model's argument
    text = " ".join(clauses)
    assert "Asha Menon" in text  # the final answer used the round-2 stream


async def test_tool_loop_bounded_by_max_rounds() -> None:
    """A model that always requests tools must not loop forever."""

    class _AlwaysTool:
        name = "always"

        async def start(self) -> None: ...
        async def aclose(self) -> None: ...
        async def complete(self, messages: Sequence[Message]) -> str:
            return ""

        async def stream(
            self, messages: Sequence[Message], tools: Sequence[dict[str, Any]] | None = None
        ) -> AsyncIterator[LLMResponseEvent]:
            yield LLMResponseEvent(
                kind="tool_call",
                tool_call=ToolCall(id="x", name="lookup_customer", arguments={"query": "x"}),
            )
            yield LLMResponseEvent(kind="done")

    executed: list[str] = []
    state = TurnStateMachine(session_id="t")
    state.begin_user_turn()
    state.add_user_message("hi")
    orch = DialogueOrchestrator(
        _AlwaysTool(),  # type: ignore[arg-type]
        state,
        ConversationMemory("t"),
        _registry(executed),
        system_prompt="",
        max_tool_rounds=3,
    )
    clauses = [c async for c in orch.respond("hi")]
    assert len(executed) == 3  # stopped at max_tool_rounds, did not hang
    # Fail-soft: even when the model never converges, the turn is never silent.
    assert " ".join(clauses).strip()


async def test_tool_loop_threads_full_preamble_to_model() -> None:
    """The model's pre-tool narration must be threaded back, not dropped."""
    seen_assistant: list[str] = []

    class _PreambleLLM:
        name = "preamble"

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
                for tok in ["Let", "me", "check", "that."]:
                    yield LLMResponseEvent(kind="token", token=tok + " ")
                yield LLMResponseEvent(
                    kind="tool_call",
                    tool_call=ToolCall(id="c1", name="lookup_customer", arguments={"query": "x"}),
                )
                yield LLMResponseEvent(kind="done")
            else:
                seen_assistant.extend(m.content for m in messages if m.role is Role.ASSISTANT)
                yield LLMResponseEvent(kind="token", token="Done. ")
                yield LLMResponseEvent(kind="done")

    state = TurnStateMachine(session_id="t")
    state.begin_user_turn()
    state.add_user_message("hi")
    orch = DialogueOrchestrator(
        _PreambleLLM(),  # type: ignore[arg-type]
        state,
        ConversationMemory("t"),
        _registry([]),
        system_prompt="",
    )
    _ = [c async for c in orch.respond("hi")]
    # Round 2 saw the assistant turn carrying the full pre-tool narration.
    assert any("check that" in a for a in seen_assistant)
