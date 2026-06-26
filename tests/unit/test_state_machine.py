"""Turn state machine + barge-in state reconciliation (PRD §9.2, §9.3)."""

from __future__ import annotations

import pytest

from sutradhar.core.types import Role, TurnState
from sutradhar.dialogue.state import InvalidTransition, TurnStateMachine


def test_happy_path_transitions() -> None:
    sm = TurnStateMachine(session_id="s1")
    transitions: list[tuple[str, str]] = []
    sm.on_transition(lambda a, b: transitions.append((a.value, b.value)))

    sm.begin_user_turn()
    assert sm.state is TurnState.LISTENING
    sm.add_user_message("hi there")
    sm.begin_thinking()
    assert sm.state is TurnState.THINKING
    sm.begin_agent_turn("t1", intended_text="hello, how can I help?")
    assert sm.state is TurnState.SPEAKING
    sm.append_spoken("hello, how can I help?")
    sm.complete_agent_turn()
    assert sm.state is TurnState.LISTENING

    assert sm.history[0].role is Role.USER
    assert sm.history[1].role is Role.ASSISTANT
    assert sm.history[1].content == "hello, how can I help?"
    assert ("idle", "listening") in transitions


def test_invalid_transition_rejected() -> None:
    sm = TurnStateMachine(session_id="s1")
    with pytest.raises(InvalidTransition):
        sm.transition(TurnState.SPEAKING)  # IDLE -> SPEAKING is illegal


def test_barge_in_records_truncated_turn() -> None:
    sm = TurnStateMachine(session_id="s1")
    sm.begin_user_turn()
    sm.add_user_message("tell me about your pricing")
    sm.begin_thinking()
    sm.begin_agent_turn(
        "t1", intended_text="Our pricing has three tiers: basic, pro, and enterprise"
    )
    sm.append_spoken("Our pricing has three tiers")  # only this much was actually heard

    record = sm.barge_in()

    assert record.interrupted
    assert record.was_truncated
    assert record.spoken_text == "Our pricing has three tiers"
    # History reflects the real, truncated exchange — no corruption.
    assert sm.state is TurnState.LISTENING
    assert sm.history[-1].role is Role.ASSISTANT
    assert "Our pricing has three tiers" in sm.history[-1].content
    assert "[interrupted]" in sm.history[-1].content


def test_barge_in_only_valid_while_speaking() -> None:
    sm = TurnStateMachine(session_id="s1")
    sm.begin_user_turn()
    with pytest.raises(InvalidTransition):
        sm.barge_in()
