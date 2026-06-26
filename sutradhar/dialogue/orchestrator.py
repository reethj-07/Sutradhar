"""Dialogue orchestrator (PRD §10). Skeleton; the streaming tool-call loop is
built in M1 (LLM streaming) and M3 (tool execution + memory injection).

Responsibilities: assemble the prompt (system + memory + windowed history),
stream the LLM, detect tool calls, execute them via the registry, feed results
back, and emit clause-sized text fragments to TTS — all cancellable for barge-in.
"""

from __future__ import annotations

from sutradhar.dialogue.memory import ConversationMemory
from sutradhar.dialogue.state import TurnStateMachine
from sutradhar.interfaces import LLM
from sutradhar.interfaces.tools import ToolRegistry


class DialogueOrchestrator:
    """Drives one assistant turn end to end. Implemented in M1/M3."""

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
