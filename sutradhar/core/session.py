"""Session lifecycle + manager (PRD §6.2).

A `Session` owns one conversation's resources (transport, state machine, latency
tracker) with per-session isolation: one session's failure cannot take down
others, and resources are cleaned up deterministically on completion or failure
(PRD §13). The full streaming pipeline is attached in M1.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field

from sutradhar.core.config import Settings, get_settings
from sutradhar.core.latency import LatencyTracker
from sutradhar.dialogue.state import TurnStateMachine
from sutradhar.observability.logging import bind_context, clear_context, get_logger

_log = get_logger("core.session")


@dataclass(slots=True)
class Session:
    """One live conversation."""

    session_id: str
    settings: Settings
    state: TurnStateMachine
    latency: LatencyTracker
    _closed: bool = field(default=False)

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self.state.state.value != "closed":
                self.state.close()
        finally:
            clear_context()
            _log.info("session_closed", session_id=self.session_id)


class SessionManager:
    """Creates, tracks and tears down sessions with bounded concurrency."""

    def __init__(self, settings: Settings | None = None, *, max_sessions: int = 8) -> None:
        self.settings = settings or get_settings()
        self.max_sessions = max_sessions
        self._sessions: dict[str, Session] = {}
        self._lock = asyncio.Lock()

    @property
    def active(self) -> int:
        return len(self._sessions)

    async def create(self, session_id: str | None = None) -> Session:
        async with self._lock:
            if len(self._sessions) >= self.max_sessions:
                raise RuntimeError(f"session limit reached ({self.max_sessions})")
            sid = session_id or uuid.uuid4().hex[:12]
            bind_context(session_id=sid)
            session = Session(
                session_id=sid,
                settings=self.settings,
                state=TurnStateMachine(session_id=sid),
                latency=LatencyTracker(),
            )
            self._sessions[sid] = session
            _log.info("session_created", session_id=sid, active=len(self._sessions))
            return session

    async def close(self, session_id: str) -> None:
        async with self._lock:
            session = self._sessions.pop(session_id, None)
        if session is not None:
            await session.aclose()

    async def close_all(self) -> None:
        for sid in list(self._sessions):
            await self.close(sid)
