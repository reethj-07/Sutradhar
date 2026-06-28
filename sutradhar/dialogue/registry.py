"""Concrete tool registry (PRD §10).

Holds tools with JSON schemas, renders them for the LLM, and executes calls
against their handlers. `execute()` never raises — a failing tool returns an
`ok=False` result so the orchestrator can feed the error back to the model and
keep the conversation responsive (fail-soft, PRD §13).
"""

from __future__ import annotations

import json
from typing import Any

from sutradhar.core.types import ToolCall, ToolResult
from sutradhar.interfaces.tools import Tool
from sutradhar.observability.logging import get_logger

_log = get_logger("dialogue.registry")


class InMemoryToolRegistry:
    """A simple dict-backed :class:`ToolRegistry`."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def schemas(self) -> list[dict[str, Any]]:
        return [t.to_openai() for t in self._tools.values()]

    @property
    def names(self) -> list[str]:
        return list(self._tools)

    async def execute(self, call: ToolCall) -> ToolResult:
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(
                id=call.id,
                name=call.name,
                content=json.dumps({"error": f"unknown tool '{call.name}'"}),
                ok=False,
            )
        try:
            result = await tool.handler(call.arguments)
        except Exception as exc:  # fail soft, report to the LLM
            _log.warning("tool_failed", tool=call.name, error=str(exc))
            return ToolResult(
                id=call.id,
                name=call.name,
                content=json.dumps({"error": str(exc)}),
                ok=False,
            )
        # Stamp the call's id/name so handlers don't need to know them.
        return ToolResult(id=call.id, name=call.name, content=result.content, ok=result.ok)
