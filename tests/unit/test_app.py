"""Operational endpoints work at M0 (PRD §12: /healthz, /readyz, /metrics)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from sutradhar.app import create_app
from sutradhar.core.config import Settings


def _client() -> TestClient:
    # Stub providers => the lifespan skips model pre-warm, keeping these
    # operational-endpoint tests fast and model-free (CI-safe).
    settings = Settings.model_validate(
        {
            "env": "ci",
            "vad": {"provider": "stub"},
            "stt": {"provider": "stub"},
            "turn": {"provider": "stub"},
            "llm": {"provider": "stub"},
            "tts": {"provider": "stub"},
            "memory": {"provider": "stub"},
        }
    )
    return TestClient(create_app(settings))


def test_healthz() -> None:
    with _client() as client:
        resp = client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


def test_readyz_ok_with_no_critical_components() -> None:
    # No probes registered => trivially ready.
    with _client() as client:
        resp = client.get("/readyz")
        assert resp.status_code == 200
        assert resp.json()["ready"] is True


def test_metrics_exposes_prometheus() -> None:
    with _client() as client:
        resp = client.get("/metrics")
        assert resp.status_code == 200
        assert "sutradhar_" in resp.text


def test_index_reports_providers() -> None:
    with _client() as client:
        body = client.get("/").json()
        assert body["service"] == "sutradhar"
        assert "vad" in body["providers"]


def test_ws_origin_policy() -> None:
    """Loopback/no-origin allowed; cross-site origins rejected (CSWSH guard)."""
    from sutradhar.app import _origin_allowed
    from sutradhar.core.config import Settings

    s = Settings.model_validate({"security": {"allowed_ws_origins": ["https://ops.example.com"]}})
    assert _origin_allowed(None, s) is True  # native client
    assert _origin_allowed("http://127.0.0.1:8080", s) is True  # loopback
    assert _origin_allowed("http://localhost:5173", s) is True  # loopback
    assert _origin_allowed("https://ops.example.com", s) is True  # allowlisted
    assert _origin_allowed("https://evil.example.com", s) is False  # cross-site
