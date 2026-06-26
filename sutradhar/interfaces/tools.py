"""Tool-calling interface (PRD §6.3, §10).

A `ToolRegistry` holds `Tool`s — functions with JSON schemas the LLM can call.
The orchestrator exposes the schemas to the LLM, executes requested calls
against the mock backend, and feeds results back into the stream (FR8).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from sutradhar.core.types import ToolCall, ToolResult

ToolHandler = Callable[[dict[str, Any]], Awaitable[ToolResult]]


@dataclass(frozen=True, slots=True)
class Tool:
    """A callable tool exposed to the LLM."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema for the arguments object
    handler: ToolHandler

    def to_openai(self) -> dict[str, Any]:
        """Render as an OpenAI/Ollama `tools` entry."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@runtime_checkable
class ToolRegistry(Protocol):
    """Registry of tools available to the dialogue orchestrator."""

    def register(self, tool: Tool) -> None: ...

    def get(self, name: str) -> Tool | None: ...

    def schemas(self) -> list[dict[str, Any]]:
        """All registered tools rendered as LLM tool schemas."""
        ...

    async def execute(self, call: ToolCall) -> ToolResult:
        """Execute a tool call, returning its result (never raising)."""
        ...
