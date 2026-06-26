"""MemoryStore interface — short- and long-term conversation memory (PRD §6.3, §10).

Default SQLite + sqlite-vec; swaps to Chroma or Redis. `append()` records turn
facts; `retrieve()` does semantic recall of relevant prior facts (caller
details, prior outcomes) to inject into the prompt (FR7).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class MemoryRecord:
    """A retrievable memory item, optionally with a similarity score."""

    id: str
    session_id: str
    text: str
    kind: str = "turn"  # turn | fact | summary
    score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class MemoryStore(Protocol):
    """Persistent, retrievable conversation memory."""

    name: str

    async def start(self) -> None: ...

    async def append(
        self,
        session_id: str,
        text: str,
        *,
        kind: str = "turn",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Persist a memory item; returns its id."""
        ...

    async def retrieve(
        self,
        session_id: str,
        query: str,
        *,
        k: int = 4,
    ) -> list[MemoryRecord]:
        """Return up to `k` records most relevant to `query`."""
        ...

    async def aclose(self) -> None: ...
