"""Turn state machine — the single source of truth for one conversation (PRD §9.3, §10).

States: IDLE -> LISTENING -> THINKING -> SPEAKING -> (INTERRUPTED) -> LISTENING.
Every transition is validated, logged and traced. Barge-in correctness depends
on this object: when the user interrupts, the machine records *what was actually
spoken* (the truncated agent turn) so the conversation history stays accurate
and no state is corrupted (PRD §9.2 steps 3 & 5).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from sutradhar.core.errors import SutradharError
from sutradhar.core.types import Message, Role, TurnState
from sutradhar.observability.logging import get_logger

_log = get_logger("dialogue.state")

# Allowed transitions (source -> set of valid destinations).
_TRANSITIONS: dict[TurnState, frozenset[TurnState]] = {
    TurnState.IDLE: frozenset({TurnState.LISTENING, TurnState.CLOSED}),
    TurnState.LISTENING: frozenset({TurnState.THINKING, TurnState.IDLE, TurnState.CLOSED}),
    TurnState.THINKING: frozenset(
        {TurnState.SPEAKING, TurnState.INTERRUPTED, TurnState.LISTENING, TurnState.CLOSED}
    ),
    TurnState.SPEAKING: frozenset(
        {TurnState.INTERRUPTED, TurnState.LISTENING, TurnState.IDLE, TurnState.CLOSED}
    ),
    TurnState.INTERRUPTED: frozenset({TurnState.LISTENING, TurnState.CLOSED}),
    TurnState.CLOSED: frozenset(),
}


class InvalidTransition(SutradharError):
    """Raised when an illegal state transition is attempted."""

    def __init__(self, src: TurnState, dst: TurnState) -> None:
        super().__init__(f"invalid transition {src.value} -> {dst.value}")
        self.src = src
        self.dst = dst


@dataclass(slots=True)
class TurnRecord:
    """An accounting of one agent speaking turn, including any truncation."""

    turn_id: str
    intended_text: str = ""
    spoken_text: str = ""
    interrupted: bool = False

    @property
    def was_truncated(self) -> bool:
        return self.interrupted and self.spoken_text != self.intended_text


@dataclass(slots=True)
class TurnStateMachine:
    """Owns the turn state and the rolling message history for one session."""

    session_id: str
    state: TurnState = TurnState.IDLE
    history: list[Message] = field(default_factory=list)
    current_turn: TurnRecord | None = None
    _listeners: list[Callable[[TurnState, TurnState], None]] = field(default_factory=list)

    # -- transitions -------------------------------------------------------
    def on_transition(self, listener: Callable[[TurnState, TurnState], None]) -> None:
        self._listeners.append(listener)

    def can_transition(self, dst: TurnState) -> bool:
        return dst in _TRANSITIONS[self.state]

    def transition(self, dst: TurnState) -> None:
        if dst == self.state:
            return
        if not self.can_transition(dst):
            raise InvalidTransition(self.state, dst)
        src, self.state = self.state, dst
        _log.debug("turn_transition", session_id=self.session_id, src=src.value, dst=dst.value)
        for listener in self._listeners:
            listener(src, dst)

    # -- turn lifecycle ----------------------------------------------------
    def begin_user_turn(self) -> None:
        self.transition(TurnState.LISTENING)

    def add_user_message(self, text: str) -> None:
        self.history.append(Message(role=Role.USER, content=text))

    def begin_thinking(self) -> None:
        self.transition(TurnState.THINKING)

    def begin_agent_turn(self, turn_id: str, intended_text: str = "") -> None:
        self.current_turn = TurnRecord(turn_id=turn_id, intended_text=intended_text)
        self.transition(TurnState.SPEAKING)

    def append_spoken(self, text: str) -> None:
        """Record audio that has actually been emitted (for truncation accuracy)."""
        if self.current_turn is not None:
            self.current_turn.spoken_text += text

    def complete_agent_turn(self) -> None:
        """Finish a non-interrupted agent turn, committing it to history."""
        if self.current_turn is not None:
            spoken = self.current_turn.spoken_text or self.current_turn.intended_text
            self.history.append(Message(role=Role.ASSISTANT, content=spoken))
            self.current_turn = None
        self.transition(TurnState.LISTENING)

    def barge_in(self) -> TurnRecord:
        """Handle a confirmed user interruption (PRD §9.2).

        Transitions SPEAKING -> INTERRUPTED, commits the *truncated* spoken text
        to history (so context reflects reality), and returns the record. The
        caller is responsible for cancelling in-flight LLM/TTS tasks.
        """
        if self.state is not TurnState.SPEAKING:
            # Idempotent / defensive: only SPEAKING can be barged into.
            raise InvalidTransition(self.state, TurnState.INTERRUPTED)
        self.transition(TurnState.INTERRUPTED)
        record = self.current_turn or TurnRecord(turn_id="unknown")
        record.interrupted = True
        spoken = record.spoken_text.strip()
        if spoken:
            self.history.append(Message(role=Role.ASSISTANT, content=spoken + " —[interrupted]"))
        self.current_turn = None
        self.transition(TurnState.LISTENING)
        return record

    def close(self) -> None:
        self.transition(TurnState.CLOSED)
