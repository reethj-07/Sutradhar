"""Short-term memory window keeps the system prompt pinned (PRD §10)."""

from __future__ import annotations

from sutradhar.core.types import Message, Role
from sutradhar.dialogue.memory import ConversationMemory


def _history(n: int) -> list[Message]:
    msgs = [Message(role=Role.SYSTEM, content="system")]
    for i in range(n):
        msgs.append(Message(role=Role.USER, content=f"u{i}"))
        msgs.append(Message(role=Role.ASSISTANT, content=f"a{i}"))
    return msgs


def test_window_returns_all_when_under_budget() -> None:
    mem = ConversationMemory("s1", short_term_turns=12)
    hist = _history(2)  # 1 system + 4 messages
    assert mem.window(hist) == hist


def test_window_truncates_and_pins_system() -> None:
    mem = ConversationMemory("s1", short_term_turns=4)
    hist = _history(10)  # 21 messages total
    win = mem.window(hist)
    assert win[0].role is Role.SYSTEM  # pinned
    assert len(win) == 5  # system + last 4
    assert win[-1].content == "a9"


async def test_recall_without_store_is_empty() -> None:
    mem = ConversationMemory("s1")
    assert await mem.recall("anything") == []
