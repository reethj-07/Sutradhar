"""M1 integration: the /ws voice endpoint answers over the real WebSocket path.

Uses FastAPI's TestClient WebSocket with stub providers (no models, no browser):
send synthetic 16 kHz PCM (speech then silence) and assert the agent streams
PCM audio back. Exercises WebSocketTransport framing + the pipeline end-to-end.
"""

from __future__ import annotations

import struct

import pytest
from fastapi.testclient import TestClient

from sutradhar.app import create_app
from sutradhar.core.config import Settings

pytestmark = pytest.mark.integration

_SR = 16000
_SAMPLES = _SR * 20 // 1000  # 320 samples / 20 ms frame


def _pcm(amplitude: int, frames: int) -> bytes:
    one = struct.pack(f"<{_SAMPLES}h", *([amplitude] * _SAMPLES))
    return one * frames


def _stub_app() -> TestClient:
    settings = Settings.model_validate(
        {
            "env": "ci",
            "vad": {"provider": "stub", "threshold": 0.02},
            "stt": {"provider": "stub"},
            "turn": {"provider": "stub", "silence_ms": 300},
            "llm": {"provider": "stub"},
            "tts": {"provider": "stub", "sample_rate": _SR},
            "memory": {"provider": "stub"},
        }
    )
    return TestClient(create_app(settings))


def test_ws_round_trip_produces_audio() -> None:
    client = _stub_app()
    # `with client` triggers lifespan (SessionRuntime); then open the socket.
    with client, client.websocket_connect("/ws") as ws:
        # ~280 ms speech then ~700 ms silence -> endpoint.
        ws.send_bytes(_pcm(6000, 14))
        ws.send_bytes(_pcm(0, 35))
        data = ws.receive_bytes()
        assert isinstance(data, bytes)
        assert len(data) > 0  # agent streamed audio back
