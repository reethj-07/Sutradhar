"""SQLite + sqlite-vec memory store — default long-term memory (PRD §10). Wired in M3.

Embedded, zero-ops, retrievable memory: turns/facts are embedded and stored in
a sqlite-vec virtual table for cosine-similarity recall. Imports are deferred to
``start()``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sutradhar.interfaces.memory import MemoryRecord

if TYPE_CHECKING:
    from sutradhar.core.config import Settings


class SqliteMemoryStore:
    name = "sqlite"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.db_path = settings.memory.db_path
        self._conn = None  # sqlite3.Connection, opened in start()

    async def start(self) -> None:
        raise NotImplementedError("SqliteMemoryStore is wired in M3 (sqlite-vec)")

    async def append(
        self,
        session_id: str,
        text: str,
        *,
        kind: str = "turn",
        metadata: dict[str, Any] | None = None,
    ) -> str:  # pragma: no cover - M3
        raise NotImplementedError

    async def retrieve(
        self, session_id: str, query: str, *, k: int = 4
    ) -> list[MemoryRecord]:  # pragma: no cover - M3
        raise NotImplementedError

    async def aclose(self) -> None: ...
