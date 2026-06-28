"""SQLite schema + seed for the mock CRM (PRD §10 demo vertical).

Embedded, zero-ops store backing the outbound lead-qualification tools. Schema is
created and seeded idempotently on first use. Parameterized queries throughout
(no string-built SQL) — the LLM controls the *arguments*, never the SQL.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

VALID_DISPOSITIONS = (
    "interested",
    "not_interested",
    "callback",
    "booked",
    "wrong_number",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    phone         TEXT NOT NULL,
    company       TEXT,
    company_size  TEXT,
    segment       TEXT,
    disposition   TEXT DEFAULT '',
    notes         TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS slots (
    id        INTEGER PRIMARY KEY,
    day       TEXT NOT NULL,
    time      TEXT NOT NULL,
    booked_by INTEGER REFERENCES customers(id)
);
CREATE TABLE IF NOT EXISTS orders (
    id          INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    item        TEXT NOT NULL,
    status      TEXT NOT NULL,
    eta         TEXT
);
"""

_SEED_CUSTOMERS = [
    (1, "Asha Menon", "+15550101", "Lotus Retail", "50-200", "retail"),
    (2, "Rahul Verma", "+15550102", "Verma Logistics", "200-1000", "logistics"),
    (3, "Priya Nair", "+15550103", "Nair Textiles", "10-50", "manufacturing"),
]
_SEED_SLOTS = [
    (1, "Tuesday", "10:00"),
    (2, "Tuesday", "14:00"),
    (3, "Wednesday", "11:00"),
    (4, "Thursday", "16:00"),
]
_SEED_ORDERS = [
    (1001, 1, "Starter plan", "active", "2026-07-05"),
    (1002, 2, "Pro plan", "shipped", "2026-07-02"),
]


def connect(db_path: str) -> sqlite3.Connection:
    """Open a connection with row access by name and FK enforcement."""
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create tables and seed demo data once (idempotent)."""
    conn.executescript(_SCHEMA)
    cur = conn.execute("SELECT COUNT(*) AS n FROM customers")
    if cur.fetchone()["n"] == 0:
        conn.executemany(
            "INSERT INTO customers (id, name, phone, company, company_size, segment) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            _SEED_CUSTOMERS,
        )
        conn.executemany("INSERT INTO slots (id, day, time) VALUES (?, ?, ?)", _SEED_SLOTS)
        conn.executemany(
            "INSERT INTO orders (id, customer_id, item, status, eta) VALUES (?, ?, ?, ?, ?)",
            _SEED_ORDERS,
        )
        conn.commit()
