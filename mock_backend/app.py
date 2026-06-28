"""Mock CRM FastAPI app (PRD §10 demo vertical: outbound lead qualification).

Exposes the tools the agent calls: ``lookup_customer``, ``book_slot``,
``get_order_status``, ``update_disposition``. Backed by SQLite (``mock_backend.db``).
Run standalone: ``uvicorn mock_backend.app:app --port 8090``.

All queries are parameterized; inputs are validated with pydantic so a
hallucinated tool argument yields a clean error, never malformed SQL.
"""

from __future__ import annotations

import os
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from mock_backend.db import VALID_DISPOSITIONS, connect, init_db

_DEFAULT_DB = os.environ.get("CRM_DB_PATH", "data/crm.db")


class LookupCustomer(BaseModel):
    query: str = Field(..., description="Customer name (partial ok) or phone number")


class BookSlot(BaseModel):
    customer_id: int
    day: str
    time: str


class GetOrderStatus(BaseModel):
    customer_id: int | None = None
    order_id: int | None = None


class UpdateDisposition(BaseModel):
    customer_id: int
    disposition: str
    notes: str = ""


def create_app(db_path: str = _DEFAULT_DB) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        conn = connect(db_path)
        init_db(conn)
        app.state.conn = conn
        yield
        conn.close()

    app = FastAPI(title="Sutradhar Mock CRM", version="0.1.0", lifespan=lifespan)

    def db() -> sqlite3.Connection:
        return app.state.conn  # type: ignore[no-any-return]

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/customers")
    async def list_customers() -> list[dict[str, Any]]:
        rows = db().execute("SELECT * FROM customers ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    @app.post("/tools/lookup_customer")
    async def lookup_customer(body: LookupCustomer) -> dict[str, Any]:
        q = body.query.strip()
        row = (
            db()
            .execute(
                "SELECT * FROM customers WHERE phone = ? OR name LIKE ? ORDER BY id LIMIT 1",
                (q, f"%{q}%"),
            )
            .fetchone()
        )
        if row is None:
            return {"found": False, "query": q}
        return {"found": True, "customer": dict(row)}

    @app.post("/tools/book_slot")
    async def book_slot(body: BookSlot) -> dict[str, Any]:
        conn = db()
        cust = conn.execute("SELECT id FROM customers WHERE id = ?", (body.customer_id,)).fetchone()
        if cust is None:
            raise HTTPException(status_code=404, detail=f"unknown customer {body.customer_id}")
        slot = conn.execute(
            "SELECT * FROM slots WHERE day = ? AND time = ? AND booked_by IS NULL",
            (body.day, body.time),
        ).fetchone()
        if slot is None:
            free = conn.execute(
                "SELECT day, time FROM slots WHERE booked_by IS NULL ORDER BY id"
            ).fetchall()
            return {
                "booked": False,
                "reason": "slot_unavailable",
                "available": [dict(s) for s in free],
            }
        conn.execute("UPDATE slots SET booked_by = ? WHERE id = ?", (body.customer_id, slot["id"]))
        conn.commit()
        return {"booked": True, "day": body.day, "time": body.time}

    @app.post("/tools/get_order_status")
    async def get_order_status(body: GetOrderStatus) -> dict[str, Any]:
        if body.order_id is not None:
            rows = db().execute("SELECT * FROM orders WHERE id = ?", (body.order_id,)).fetchall()
        elif body.customer_id is not None:
            rows = (
                db()
                .execute("SELECT * FROM orders WHERE customer_id = ?", (body.customer_id,))
                .fetchall()
            )
        else:
            raise HTTPException(status_code=422, detail="order_id or customer_id required")
        return {"orders": [dict(r) for r in rows]}

    @app.post("/tools/update_disposition")
    async def update_disposition(body: UpdateDisposition) -> dict[str, Any]:
        if body.disposition not in VALID_DISPOSITIONS:
            raise HTTPException(
                status_code=422,
                detail=f"invalid disposition; expected one of {list(VALID_DISPOSITIONS)}",
            )
        conn = db()
        cur = conn.execute(
            "UPDATE customers SET disposition = ?, notes = ? WHERE id = ?",
            (body.disposition, body.notes, body.customer_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"unknown customer {body.customer_id}")
        return {"updated": True, "customer_id": body.customer_id, "disposition": body.disposition}

    return app


app = create_app()
