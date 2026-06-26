"""Dialogue orchestrator (PRD §10).

Drives one assistant turn: assemble the prompt (system + memory + windowed
history), stream the LLM, split the token stream into *clauses* and yield them so
TTS can start before the full response exists (first-clause synthesis, PR2). Tool
execution + long-term memory injection are layered in M3; barge-in cancellation
is layered in M2 (the whole stream is already cancellation-aware via the token).
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator

from sutradhar.core.cancellation import CancellationToken
from sutradhar.core.latency import LatencyTracker
from sutradhar.core.types import Message, Role, Stage
from sutradhar.dialogue.memory import ConversationMemory
from sutradhar.dialogue.state import TurnStateMachine
from sutradhar.interfaces import LLM
from sutradhar.interfaces.tools import ToolRegistry
from sutradhar.observability.logging import get_logger

_log = get_logger("dialogue.orchestrator")

# A clause boundary: sentence/clause punctuation followed by whitespace or end.
_BOUNDARY = re.compile(r"[.!?,;:](?=\s|$)")
# Emit an over-long run even without punctuation so first audio isn't delayed.
_SOFT_LIMIT = 60


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
    ) -> None:
        self.llm = llm
        self.state = state
        self.memory = memory
        self.tools = tools
        self.system_prompt = system_prompt

    def _messages(self) -> list[Message]:
        msgs: list[Message] = []
        if self.system_prompt:
            msgs.append(Message(role=Role.SYSTEM, content=self.system_prompt))
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

        `user_text` is expected to already be in `state.history`; it is passed
        for logging/clarity. `latency` (if given) records LLM first-token time.
        """
        messages = self._messages()
        tool_schemas = self.tools.schemas()
        buffer = ""
        first_token = True
        events = self.llm.stream(messages, tool_schemas or None)
        stream = cancel.stream(events) if cancel is not None else events
        async for ev in stream:
            if ev.kind == "token":
                if first_token:
                    first_token = False
                    if latency is not None:
                        latency.end_stage(Stage.LLM, provider=getattr(self.llm, "name", "?"))
                buffer += ev.token
                clauses, buffer = self._split_clauses(buffer)
                for clause in clauses:
                    yield clause
            elif ev.kind == "tool_call":
                # Tool execution is wired in M3; ignore for the M1 core loop.
                _log.debug("tool_call_ignored_m1", tool=getattr(ev.tool_call, "name", "?"))
            elif ev.kind == "done":
                break
        tail = buffer.strip()
        if tail:
            yield tail
