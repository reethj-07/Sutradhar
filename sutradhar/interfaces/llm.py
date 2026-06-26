"""LLM interface — streaming chat with tool-calling (PRD §6.3, §10).

Default Ollama serving Qwen2.5-3B-Instruct on CPU + partial GPU offload; swaps
to an OpenAI/Anthropic-compatible stub. `stream()` yields token and tool-call
events so TTS can start before the full response exists (FR4, FR5, PR2).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any, Protocol, runtime_checkable

from sutradhar.core.types import LLMResponseEvent, Message


@runtime_checkable
class LLM(Protocol):
    """Streaming language model with tool-calling."""

    name: str

    async def start(self) -> None: ...

    def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> AsyncIterator[LLMResponseEvent]:
        """Stream the assistant response as token / tool_call / done events."""
        ...

    async def complete(self, messages: Sequence[Message]) -> str:
        """Non-streaming completion (eval / fallback holding phrases)."""
        ...

    async def aclose(self) -> None: ...
