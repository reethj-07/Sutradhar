"""Conversation memory manager (PRD §10).

Combines two horizons behind one object the orchestrator uses to build prompts:

* **Short-term** — a rolling window of the most recent turns kept within the LLM
  context budget (pure in-process; live from M0).
* **Long-term** — semantic recall from a :class:`MemoryStore` of relevant prior
  facts injected into the prompt (wired in M3).
"""

from __future__ import annotations

from collections.abc import Sequence

from sutradhar.core.types import Message
from sutradhar.interfaces.memory import MemoryRecord, MemoryStore


class ConversationMemory:
    """Short-term window + optional long-term store."""

    def __init__(
        self,
        session_id: str,
        *,
        short_term_turns: int = 12,
        store: MemoryStore | None = None,
        retrieve_k: int = 4,
    ) -> None:
        self.session_id = session_id
        self.short_term_turns = short_term_turns
        self.store = store
        self.retrieve_k = retrieve_k

    def window(self, history: Sequence[Message]) -> list[Message]:
        """Most recent messages within the short-term budget, keeping any
        leading system message pinned at the front."""
        if len(history) <= self.short_term_turns:
            return list(history)
        head = [history[0]] if history and history[0].role.value == "system" else []
        tail = list(history[-self.short_term_turns :])
        return head + tail

    async def remember(self, text: str, *, kind: str = "turn") -> None:
        if self.store is not None:
            await self.store.append(self.session_id, text, kind=kind)

    async def recall(self, query: str) -> list[MemoryRecord]:
        if self.store is None:
            return []
        return await self.store.retrieve(self.session_id, query, k=self.retrieve_k)
