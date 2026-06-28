"""Lead-qualification CRM tools (PRD §10).

Defines the four tools the agent calls during outbound lead qualification, each
with a JSON schema for the LLM and a handler that calls the mock CRM backend over
HTTP. Handlers return a :class:`ToolResult` whose ``content`` is JSON the model
can read; the registry stamps the call id/name. Handlers never raise — a backend
error becomes an ``ok=False`` result so the conversation stays responsive.

`build_crm_tools` accepts an optional pre-built httpx client so tests can target
the backend in-process (ASGI transport); otherwise it uses a short-lived client
per call against ``settings.backend.base_url``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import httpx

from sutradhar.core.types import ToolResult
from sutradhar.dialogue.registry import InMemoryToolRegistry
from sutradhar.interfaces.tools import Tool

if TYPE_CHECKING:
    from sutradhar.core.config import Settings


def build_crm_tools(
    settings: Settings,
    registry: InMemoryToolRegistry | None = None,
    *,
    client: httpx.AsyncClient | None = None,
) -> InMemoryToolRegistry:
    """Register the lead-qualification tools against the configured backend."""
    base = settings.backend.base_url
    reg = registry or InMemoryToolRegistry()

    async def call(path: str, payload: dict[str, Any]) -> ToolResult:
        try:
            if client is not None:
                resp = await client.post(path, json=payload)
            else:
                async with httpx.AsyncClient(base_url=base, timeout=5.0) as c:
                    resp = await c.post(path, json=payload)
            if resp.status_code >= 400:
                return ToolResult(
                    id="", name="", content=json.dumps({"error": resp.text}), ok=False
                )
            return ToolResult(id="", name="", content=resp.text, ok=True)
        except Exception as exc:  # backend down / timeout -> soft error
            return ToolResult(id="", name="", content=json.dumps({"error": str(exc)}), ok=False)

    async def lookup_customer(args: dict[str, Any]) -> ToolResult:
        return await call("/tools/lookup_customer", {"query": str(args.get("query", ""))})

    async def book_slot(args: dict[str, Any]) -> ToolResult:
        return await call(
            "/tools/book_slot",
            {
                "customer_id": args.get("customer_id"),
                "day": str(args.get("day", "")),
                "time": str(args.get("time", "")),
            },
        )

    async def get_order_status(args: dict[str, Any]) -> ToolResult:
        return await call(
            "/tools/get_order_status",
            {"customer_id": args.get("customer_id"), "order_id": args.get("order_id")},
        )

    async def update_disposition(args: dict[str, Any]) -> ToolResult:
        return await call(
            "/tools/update_disposition",
            {
                "customer_id": args.get("customer_id"),
                "disposition": str(args.get("disposition", "")),
                "notes": str(args.get("notes", "")),
            },
        )

    reg.register(
        Tool(
            name="lookup_customer",
            description="Look up a customer by name or phone number before discussing their account.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Customer name or phone number"}
                },
                "required": ["query"],
            },
            handler=lookup_customer,
        )
    )
    reg.register(
        Tool(
            name="book_slot",
            description="Book a follow-up appointment slot for a customer (use an available day/time).",
            parameters={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "integer"},
                    "day": {"type": "string", "description": "e.g. Tuesday"},
                    "time": {"type": "string", "description": "24h HH:MM, e.g. 14:00"},
                },
                "required": ["customer_id", "day", "time"],
            },
            handler=book_slot,
        )
    )
    reg.register(
        Tool(
            name="get_order_status",
            description="Get a customer's order status by customer_id or a specific order_id.",
            parameters={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "integer"},
                    "order_id": {"type": "integer"},
                },
            },
            handler=get_order_status,
        )
    )
    reg.register(
        Tool(
            name="update_disposition",
            description=(
                "Record the call outcome. disposition must be one of: interested, "
                "not_interested, callback, booked, wrong_number."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "customer_id": {"type": "integer"},
                    "disposition": {
                        "type": "string",
                        "enum": [
                            "interested",
                            "not_interested",
                            "callback",
                            "booked",
                            "wrong_number",
                        ],
                    },
                    "notes": {"type": "string"},
                },
                "required": ["customer_id", "disposition"],
            },
            handler=update_disposition,
        )
    )
    return reg
