"""Mock CRM FastAPI app (PRD §10). Endpoints fleshed out in M3.

Run with: ``uvicorn mock_backend.app:app --port 8090``.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

app = FastAPI(title="Sutradhar Mock CRM", version="0.1.0")


@app.get("/healthz")
async def healthz() -> dict[str, Any]:
    return {"status": "ok"}


# The lead-qualification tool endpoints (lookup_customer, book_slot,
# get_order_status, update_disposition) backed by SQLite are added in M3.
