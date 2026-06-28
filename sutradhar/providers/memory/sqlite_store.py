"""SQLite memory store — persistent, retrievable conversation memory (PRD §10).

Persists turns/facts to an embedded SQLite database so memory survives across
turns and sessions (the M3 acceptance: "memory persists across turns"). Retrieval
ranks by lexical overlap with the query — dependency-free and deterministic.

Bounded by design (a real-time voice path can't afford unbounded growth):
* stored text is capped per row;
* retrieval scans only the most recent `_RECENT` rows for the session;
* all sqlite work runs in a worker thread under a lock (the one shared connection
  is reused across sessions), so it never blocks the event loop nor interleaves
  statements on the connection.

The vector path (sqlite-vec + an embedding model) is a drop-in upgrade: add an
embedding function and a `vec0` virtual table for cosine recall; the interface and
call sites are unchanged. All SQL is parameterized.

Note (M3 limitation): retrieval is keyed by `session_id`, which is per
WebSocket connection — so recall is within-call. Cross-call recall (by a stable
caller identity, e.g. phone/customer_id) arrives with telephony in M5.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sutradhar.interfaces.memory import MemoryRecord
from sutradhar.observability.logging import get_logger

if TYPE_CHECKING:
    from sutradhar.core.config import Settings

_log = get_logger("providers.memory.sqlite")

_MAX_TEXT = 2000  # cap stored text per row
_RECENT = 200  # only score the most recent N rows per session on recall

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    text        TEXT NOT NULL,
    kind        TEXT NOT NULL DEFAULT 'turn',
    metadata    TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_memories_session ON memories(session_id);
"""


def _tokens(text: str) -> set[str]:
    return {t for t in (w.strip(".,;:!?\"'").lower() for w in text.split()) if t}


class SqliteMemoryStore:
    name = "sqlite"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db_path = settings.memory.db_path
        self._conn: sqlite3.Connection | None = None
        self._lock = asyncio.Lock()  # serialize access to the one shared connection

    async def start(self) -> None:
        if self._conn is not None:
            return
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        if self.db_path != ":memory:":
            # WAL + busy_timeout make concurrent readers/writers robust on disk.
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA busy_timeout = 3000")
        conn.executescript(_SCHEMA)
        conn.commit()
        self._conn = conn
        _log.info("sqlite_memory_ready", db=self.db_path)

    def _require(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("SqliteMemoryStore.start() must be called first")
        return self._conn

    def _append_sync(self, session_id: str, text: str, kind: str, metadata: dict[str, Any]) -> int:
        conn = self._require()
        cur = conn.execute(
            "INSERT INTO memories (session_id, text, kind, metadata) VALUES (?, ?, ?, ?)",
            (session_id, text[:_MAX_TEXT], kind, json.dumps(metadata)),
        )
        conn.commit()
        return int(cur.lastrowid or 0)

    async def append(
        self,
        session_id: str,
        text: str,
        *,
        kind: str = "turn",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        async with self._lock:
            rowid = await asyncio.to_thread(
                self._append_sync, session_id, text, kind, metadata or {}
            )
        return f"mem-{rowid}"

    def _retrieve_sync(self, session_id: str, q: set[str], k: int) -> list[MemoryRecord]:
        conn = self._require()
        rows = conn.execute(
            "SELECT id, session_id, text, kind, metadata FROM memories "
            "WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, _RECENT),
        ).fetchall()
        scored: list[tuple[int, MemoryRecord]] = []
        for r in rows:
            overlap = len(q & _tokens(r["text"]))
            if overlap > 0:
                scored.append(
                    (
                        overlap,
                        MemoryRecord(
                            id=f"mem-{r['id']}",
                            session_id=r["session_id"],
                            text=r["text"],
                            kind=r["kind"],
                            score=float(overlap),
                            metadata=json.loads(r["metadata"]),
                        ),
                    )
                )
        scored.sort(key=lambda x: x[0], reverse=True)
        return [rec for _, rec in scored[:k]]

    async def retrieve(self, session_id: str, query: str, *, k: int = 4) -> list[MemoryRecord]:
        q = _tokens(query)
        if not q:
            return []
        async with self._lock:
            return await asyncio.to_thread(self._retrieve_sync, session_id, q, k)

    async def aclose(self) -> None:
        async with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
