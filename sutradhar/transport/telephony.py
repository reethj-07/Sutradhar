"""Simulated telephony transport (PRD §5, §17 M5).

Runs the *same* agent over a telephony-like channel: 8 kHz mono PCM (µ-law-style
narrowband), a SIP-like session lifecycle (INVITE/ANSWER/BYE modeled as events),
and a jitter buffer — with no paid carrier. Demonstrates the dual-transport claim
without PSTN. Wired in M5.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sutradhar.core.types import AudioChunk, AudioFrame, SessionEvent


class TelephonySimTransport:
    name = "telephony_sim"

    def __init__(self, session_id: str, sample_rate: int = 8000) -> None:
        self.session_id = session_id
        self.sample_rate = sample_rate

    def recv_audio(self) -> AsyncIterator[AudioFrame]:  # pragma: no cover - M5
        raise NotImplementedError("TelephonySimTransport is wired in M5")

    async def send_audio(self, chunk: AudioChunk) -> None:  # pragma: no cover - M5
        raise NotImplementedError

    async def flush(self) -> None: ...

    def events(self) -> AsyncIterator[SessionEvent]:  # pragma: no cover - M5
        raise NotImplementedError("TelephonySimTransport is wired in M5")

    async def close(self) -> None: ...
