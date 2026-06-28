"""Mock CRM backend endpoints (PRD §10 demo vertical)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from mock_backend.app import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(":memory:"))


def test_healthz(client: TestClient) -> None:
    with client:
        assert client.get("/healthz").json()["status"] == "ok"


def test_lookup_customer_by_name_and_phone(client: TestClient) -> None:
    with client:
        by_name = client.post("/tools/lookup_customer", json={"query": "Asha"}).json()
        assert by_name["found"] is True
        assert by_name["customer"]["name"] == "Asha Menon"
        cid = by_name["customer"]["id"]
        by_phone = client.post("/tools/lookup_customer", json={"query": "+15550101"}).json()
        assert by_phone["customer"]["id"] == cid


def test_lookup_customer_not_found(client: TestClient) -> None:
    with client:
        res = client.post("/tools/lookup_customer", json={"query": "Nobody"}).json()
        assert res["found"] is False


def test_book_slot_and_double_book(client: TestClient) -> None:
    with client:
        ok = client.post(
            "/tools/book_slot", json={"customer_id": 1, "day": "Tuesday", "time": "10:00"}
        ).json()
        assert ok["booked"] is True
        # same slot is now taken -> not booked, offers alternatives
        again = client.post(
            "/tools/book_slot", json={"customer_id": 2, "day": "Tuesday", "time": "10:00"}
        ).json()
        assert again["booked"] is False
        assert again["available"]


def test_book_slot_unknown_customer(client: TestClient) -> None:
    with client:
        resp = client.post(
            "/tools/book_slot", json={"customer_id": 999, "day": "Tuesday", "time": "10:00"}
        )
        assert resp.status_code == 404


def test_get_order_status(client: TestClient) -> None:
    with client:
        res = client.post("/tools/get_order_status", json={"customer_id": 1}).json()
        assert res["orders"][0]["status"] == "active"


def test_update_disposition_valid_and_invalid(client: TestClient) -> None:
    with client:
        ok = client.post(
            "/tools/update_disposition",
            json={"customer_id": 1, "disposition": "interested", "notes": "keen"},
        ).json()
        assert ok["updated"] is True
        bad = client.post(
            "/tools/update_disposition",
            json={"customer_id": 1, "disposition": "totally-made-up"},
        )
        assert bad.status_code == 422


def test_sql_injection_is_inert(client: TestClient) -> None:
    # Parameterized queries: a SQL-ish query string is treated as data, not code.
    with client:
        res = client.post(
            "/tools/lookup_customer", json={"query": "'; DROP TABLE customers;--"}
        ).json()
        assert res["found"] is False
        # table still intact
        assert client.get("/customers").json()
