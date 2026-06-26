"""Tool registry: schemas, execution, fail-soft (PRD §10, §13)."""

from __future__ import annotations

from sutradhar.core.types import ToolCall, ToolResult
from sutradhar.dialogue.registry import InMemoryToolRegistry
from sutradhar.interfaces.tools import Tool


def _make_tool() -> Tool:
    async def handler(args: dict[str, object]) -> ToolResult:
        return ToolResult(id="x", name="add", content=str(args["a"]), ok=True)

    return Tool(
        name="add",
        description="add numbers",
        parameters={"type": "object", "properties": {"a": {"type": "integer"}}},
        handler=handler,
    )


def test_schemas_render_openai_shape() -> None:
    reg = InMemoryToolRegistry()
    reg.register(_make_tool())
    schemas = reg.schemas()
    assert schemas[0]["type"] == "function"
    assert schemas[0]["function"]["name"] == "add"


async def test_execute_unknown_tool_is_soft_error() -> None:
    reg = InMemoryToolRegistry()
    result = await reg.execute(ToolCall(id="1", name="missing", arguments={}))
    assert result.ok is False
    assert "unknown tool" in result.content


async def test_execute_handler_exception_is_soft_error() -> None:
    reg = InMemoryToolRegistry()

    async def boom(args: dict[str, object]) -> ToolResult:
        raise RuntimeError("kaboom")

    reg.register(Tool("bad", "fails", {"type": "object"}, boom))
    result = await reg.execute(ToolCall(id="1", name="bad", arguments={}))
    assert result.ok is False
    assert "kaboom" in result.content


async def test_execute_success() -> None:
    reg = InMemoryToolRegistry()
    reg.register(_make_tool())
    result = await reg.execute(ToolCall(id="1", name="add", arguments={"a": 5}))
    assert result.ok is True
    assert result.content == "5"
