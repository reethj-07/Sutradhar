"""OpenAI/Anthropic-compatible LLM (commercial swap target, PRD §6.3). Wired in M5.

Talks to any OpenAI-compatible /v1/chat/completions endpoint (OpenAI, Together,
vLLM, Sarvam, …) via httpx with SSE streaming. Demonstrates the commercial swap
requires only a new adapter + config (NFR8).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import TYPE_CHECKING, Any

from sutradhar.core.types import LLMResponseEvent, Message

if TYPE_CHECKING:
    from sutradhar.core.config import Settings


class OpenAICompatibleLLM:
    name = "openai-compatible"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.base_url = settings.llm.base_url
        self.api_key = settings.llm.api_key
        self.model = settings.llm.model

    async def start(self) -> None:
        raise NotImplementedError("OpenAICompatibleLLM is wired in M5 (httpx SSE)")

    def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> AsyncIterator[LLMResponseEvent]:  # pragma: no cover - M5
        raise NotImplementedError("OpenAICompatibleLLM is wired in M5")

    async def complete(self, messages: Sequence[Message]) -> str:  # pragma: no cover
        raise NotImplementedError

    async def aclose(self) -> None: ...
