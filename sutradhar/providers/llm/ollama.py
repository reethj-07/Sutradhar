"""Ollama LLM — default, serving Qwen2.5-3B-Instruct Q4_K_M (PRD §7). Wired in M1.

Uses the async Ollama client to stream chat tokens and tool calls from a local
Ollama server (CPU + partial GPU offload). The client is imported in ``start()``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import TYPE_CHECKING, Any

from sutradhar.core.types import LLMResponseEvent, Message

if TYPE_CHECKING:
    from sutradhar.core.config import Settings


class OllamaLLM:
    name = "ollama"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.model = settings.llm.model
        self._client = None  # ollama.AsyncClient, created in start()

    async def start(self) -> None:
        raise NotImplementedError("OllamaLLM is wired in M1 (AsyncClient + model pull)")

    def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> AsyncIterator[LLMResponseEvent]:  # pragma: no cover - M1
        raise NotImplementedError("OllamaLLM is wired in M1")

    async def complete(self, messages: Sequence[Message]) -> str:  # pragma: no cover
        raise NotImplementedError

    async def aclose(self) -> None: ...
