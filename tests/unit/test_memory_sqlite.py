"""SqliteMemoryStore: persistence + retrieval (PRD §10)."""

from __future__ import annotations

from sutradhar.core.config import Settings
from sutradhar.providers.memory.sqlite_store import SqliteMemoryStore


def _store() -> SqliteMemoryStore:
    return SqliteMemoryStore(Settings.model_validate({"memory": {"db_path": ":memory:"}}))


async def test_append_and_retrieve_by_overlap() -> None:
    store = _store()
    await store.start()
    await store.append("s1", "caller prefers morning appointments")
    await store.append("s1", "the weather is pleasant today")
    await store.append("s1", "caller asked about the pro plan pricing")

    hits = await store.retrieve("s1", "what plan pricing did they want", k=2)
    assert hits
    assert "pricing" in hits[0].text
    await store.aclose()


async def test_retrieval_is_session_scoped() -> None:
    store = _store()
    await store.start()
    await store.append("s1", "secret one")
    await store.append("s2", "secret two")
    hits = await store.retrieve("s1", "secret")
    assert all(h.session_id == "s1" for h in hits)
    await store.aclose()


async def test_persists_across_reopen(tmp_path: object) -> None:
    db = str(tmp_path) + "/mem.db"  # type: ignore[operator]
    s1 = SqliteMemoryStore(Settings.model_validate({"memory": {"db_path": db}}))
    await s1.start()
    await s1.append("sess", "booked a slot for Tuesday")
    await s1.aclose()

    s2 = SqliteMemoryStore(Settings.model_validate({"memory": {"db_path": db}}))
    await s2.start()
    hits = await s2.retrieve("sess", "when is the slot booked")
    assert hits and "Tuesday" in hits[0].text
    await s2.aclose()


async def test_no_query_tokens_returns_empty() -> None:
    store = _store()
    await store.start()
    await store.append("s1", "something")
    assert await store.retrieve("s1", "   ") == []
    await store.aclose()
