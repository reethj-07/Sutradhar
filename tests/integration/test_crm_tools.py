"""CRM tools exercised against the in-process mock backend (PRD §10).

Uses httpx's ASGI transport so the real tool handlers call the real FastAPI
backend with no network/server — verifying the full tool wiring end to end.
"""

from __future__ import annotations

import json

import httpx
import pytest

from mock_backend.app import create_app
from sutradhar.core.config import Settings
from sutradhar.core.types import ToolCall
from sutradhar.dialogue.tools_crm import build_crm_tools

pytestmark = pytest.mark.integration


async def test_crm_tools_against_backend() -> None:
    app = create_app(":memory:")
    settings = Settings.model_validate({"backend": {"base_url": "http://crm"}})

    # Run the backend lifespan (db init/seed), then drive it via ASGI transport.
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://crm") as client,
    ):
        assert (await client.get("/healthz")).status_code == 200
        reg = build_crm_tools(settings, client=client)

        look = await reg.execute(
            ToolCall(id="1", name="lookup_customer", arguments={"query": "Asha"})
        )
        assert look.ok
        cust = json.loads(look.content)
        assert cust["found"] is True
        cid = cust["customer"]["id"]

        book = await reg.execute(
            ToolCall(
                id="2",
                name="book_slot",
                arguments={"customer_id": cid, "day": "Tuesday", "time": "10:00"},
            )
        )
        assert json.loads(book.content)["booked"] is True

        disp = await reg.execute(
            ToolCall(
                id="3",
                name="update_disposition",
                arguments={"customer_id": cid, "disposition": "booked", "notes": "set for Tue 10"},
            )
        )
        assert json.loads(disp.content)["updated"] is True

        # Invalid disposition -> soft error (ok=False), conversation continues.
        bad = await reg.execute(
            ToolCall(
                id="4",
                name="update_disposition",
                arguments={"customer_id": cid, "disposition": "nope"},
            )
        )
        assert bad.ok is False
