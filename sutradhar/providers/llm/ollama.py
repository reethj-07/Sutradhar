"""Ollama LLM — default, serving Qwen2.5-3B-Instruct Q4_K_M (PRD §7).

Streams chat tokens and tool calls from a local Ollama server over its async
client (CPU + partial GPU offload). Short prompt + token streaming keep LLM
first-token latency down (PRD §8). Accessors are defensive so the adapter works
across ollama-python versions that return either objects or plain dicts.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Sequence
from typing import TYPE_CHECKING, Any

from sutradhar.core.errors import ProviderError
from sutradhar.core.types import LLMResponseEvent, Message, ToolCall
from sutradhar.observability.logging import get_logger

if TYPE_CHECKING:
    from sutradhar.core.config import Settings

_log = get_logger("providers.llm.ollama")


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Read `key` from an object (attribute) or mapping (item)."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class OllamaLLM:
    name = "ollama"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.s = settings.llm
        self.model = self.s.model
        self._client: Any = None

    async def start(self) -> None:
        if self._client is not None:
            return
        from ollama import AsyncClient

        self._client = AsyncClient(host=self.s.base_url)
        # Best-effort warm check; don't hard-fail here (failover handles a down server).
        try:
            await self._client.list()
            _log.info("ollama_ready", model=self.model, host=self.s.base_url)
        except Exception as exc:
            _log.warning("ollama_list_failed", error=str(exc))

    @property
    def _options(self) -> dict[str, Any]:
        return {
            "temperature": self.s.temperature,
            "num_predict": self.s.max_tokens,
            "num_ctx": self.s.num_ctx,
        }

    async def stream(
        self,
        messages: Sequence[Message],
        tools: Sequence[dict[str, Any]] | None = None,
    ) -> AsyncIterator[LLMResponseEvent]:
        if self._client is None:
            raise RuntimeError("OllamaLLM.start() must be called before stream()")
        payload = [m.to_openai() for m in messages]
        try:
            stream = await self._client.chat(
                model=self.model,
                messages=payload,
                tools=list(tools) if tools else None,
                stream=True,
                options=self._options,
            )
            async for chunk in stream:
                msg = _get(chunk, "message", {})
                content = _get(msg, "content", "") or ""
                if content:
                    yield LLMResponseEvent(kind="token", token=content)
                for tc in _get(msg, "tool_calls", []) or []:
                    fn = _get(tc, "function", {})
                    yield LLMResponseEvent(
                        kind="tool_call",
                        tool_call=ToolCall(
                            id=_get(tc, "id", "") or uuid.uuid4().hex[:8],
                            name=_get(fn, "name", "") or "",
                            arguments=dict(_get(fn, "arguments", {}) or {}),
                        ),
                    )
                if _get(chunk, "done", False):
                    yield LLMResponseEvent(
                        kind="done", finish_reason=_get(chunk, "done_reason", "stop")
                    )
                    return
        except Exception as exc:  # surface as a provider error for retry/failover
            raise ProviderError(
                f"ollama chat failed: {exc}", provider=self.name, stage="llm"
            ) from exc

    async def complete(self, messages: Sequence[Message]) -> str:
        if self._client is None:
            await self.start()
        payload = [m.to_openai() for m in messages]
        resp = await self._client.chat(
            model=self.model, messages=payload, stream=False, options=self._options
        )
        return str(_get(_get(resp, "message", {}), "content", "") or "")

    async def aclose(self) -> None:
        self._client = None
