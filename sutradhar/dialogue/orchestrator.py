"""Dialogue orchestrator (PRD §10).

Drives one assistant turn: assemble the prompt (system + recalled memory +
windowed history), stream the LLM, split the token stream into *clauses* and yield
them so TTS can start before the full response exists (first-clause synthesis,
PR2). Runs the streaming **tool-calling loop** (M3): when the model emits tool
calls it executes them against the registry, feeds the results back, and continues
until a final spoken answer — bounded by ``max_tool_rounds``. Long-term memory is
recalled before the turn and the exchange persisted after. The whole stream is
cancellation-aware (M2 barge-in).
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any

from sutradhar.core.cancellation import CancellationToken
from sutradhar.core.latency import LatencyTracker
from sutradhar.core.types import Message, Role, Stage, ToolCall
from sutradhar.dialogue.memory import ConversationMemory
from sutradhar.dialogue.state import TurnStateMachine
from sutradhar.interfaces import LLM
from sutradhar.interfaces.memory import MemoryRecord
from sutradhar.interfaces.tools import ToolRegistry
from sutradhar.observability.logging import get_logger

_log = get_logger("dialogue.orchestrator")

# A clause boundary: sentence/clause punctuation followed by whitespace or end.
_BOUNDARY = re.compile(r"[.!?,;:](?=\s|$)")
# Emit an over-long run even without punctuation so first audio isn't delayed.
_SOFT_LIMIT = 60


@dataclass(slots=True)
class _Round:
    """Per-round accumulator: full assistant text + any tool calls it requested."""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)


class DialogueOrchestrator:
    """Streams an assistant response as TTS-ready text clauses."""

    def __init__(
        self,
        llm: LLM,
        state: TurnStateMachine,
        memory: ConversationMemory,
        tools: ToolRegistry,
        *,
        system_prompt: str = "",
        max_tool_rounds: int = 4,
    ) -> None:
        self.llm = llm
        self.state = state
        self.memory = memory
        self.tools = tools
        self.system_prompt = system_prompt
        self.max_tool_rounds = max_tool_rounds
        self._first_token = True

    def _messages(self, recalled: Sequence[MemoryRecord] = ()) -> list[Message]:
        msgs: list[Message] = []
        if self.system_prompt:
            msgs.append(Message(role=Role.SYSTEM, content=self.system_prompt))
        if recalled:
            facts = "\n".join(f"- {r.text}" for r in recalled)
            msgs.append(
                Message(role=Role.SYSTEM, content=f"Relevant context from earlier:\n{facts}")
            )
        msgs.extend(self.memory.window(self.state.history))
        return msgs

    @staticmethod
    def _split_clauses(buffer: str) -> tuple[list[str], str]:
        """Pull complete clauses out of `buffer`, returning (clauses, remainder)."""
        clauses: list[str] = []
        while True:
            match = _BOUNDARY.search(buffer)
            if match:
                end = match.end()
                clause = buffer[:end].strip()
                buffer = buffer[end:]
                if clause:
                    clauses.append(clause)
                continue
            if len(buffer) >= _SOFT_LIMIT and " " in buffer:
                cut = buffer.rfind(" ", 0, _SOFT_LIMIT)
                clause = buffer[:cut].strip()
                buffer = buffer[cut:]
                if clause:
                    clauses.append(clause)
                continue
            break
        return clauses, buffer

    async def respond(
        self,
        user_text: str,
        latency: LatencyTracker | None = None,
        cancel: CancellationToken | None = None,
    ) -> AsyncIterator[str]:
        """Yield TTS-ready clauses for the assistant's reply to `user_text`.

        Runs the tool-calling loop: stream the LLM; if it requests tools, execute
        them, feed results back, and continue until a final answer (bounded by
        ``max_tool_rounds``). `user_text` is already in `state.history`; it is used
        for memory recall/persistence. `latency` records LLM first-token time.
        """
        recalled = await self.memory.recall(user_text)
        messages = self._messages(recalled)
        tool_schemas = self.tools.schemas()
        self._first_token = True
        spoken: list[str] = []
        answered = False

        for _round in range(self.max_tool_rounds):
            holder = _Round()
            async for clause in self._stream_round(
                messages, tool_schemas or None, latency, holder, cancel
            ):
                spoken.append(clause)
                yield clause

            if not holder.tool_calls:
                answered = True
                break

            # Thread the FULL assistant text this round (not just the remainder)
            # plus the tool calls, then feed each tool result back for the next round.
            messages.append(
                Message(
                    role=Role.ASSISTANT, content=holder.text.strip(), tool_calls=holder.tool_calls
                )
            )
            for call in holder.tool_calls:
                result = await self.tools.execute(call)
                _log.info("tool_executed", tool=call.name, ok=result.ok)
                messages.append(
                    Message(
                        role=Role.TOOL,
                        content=result.content,
                        tool_call_id=call.id,
                        name=call.name,
                    )
                )

        if not answered:
            # Tool rounds exhausted — force one final answer with tools disabled so
            # the turn is never silent (PRD §13 fail-soft).
            _log.warning("tool_rounds_exhausted", rounds=self.max_tool_rounds)
            holder = _Round()
            async for clause in self._stream_round(messages, None, latency, holder, cancel):
                spoken.append(clause)
                yield clause

        if not spoken:
            # Last-resort holding phrase: a voice agent must never go dead-air.
            fallback = "Sorry, I didn't quite catch that. Could you say that again?"
            spoken.append(fallback)
            yield fallback

        # Persist the exchange to long-term memory (best-effort; never raises here).
        final = " ".join(spoken).strip()
        await self.memory.remember(f"caller: {user_text}", kind="turn")
        if final:
            await self.memory.remember(f"agent: {final}", kind="turn")

    async def _stream_round(
        self,
        messages: list[Message],
        tools_arg: list[dict[str, Any]] | None,
        latency: LatencyTracker | None,
        holder: _Round,
        cancel: CancellationToken | None,
    ) -> AsyncIterator[str]:
        """Stream one LLM call: yield TTS clauses, collect tool calls + full text."""
        buffer = ""
        events = self.llm.stream(messages, tools_arg)
        stream = cancel.stream(events) if cancel is not None else events
        async for ev in stream:
            if ev.kind == "token":
                if self._first_token:
                    self._first_token = False
                    if latency is not None:
                        latency.end_stage(Stage.LLM, provider=getattr(self.llm, "name", "?"))
                buffer += ev.token
                clauses, buffer = self._split_clauses(buffer)
                for clause in clauses:
                    holder.text += clause + " "
                    yield clause
            elif ev.kind == "tool_call" and ev.tool_call is not None:
                holder.tool_calls.append(ev.tool_call)
            elif ev.kind == "done":
                break
        tail = buffer.strip()
        if tail:
            holder.text += tail
            yield tail
