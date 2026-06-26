"""FastAPI application: health, readiness, metrics and (from M1) the WebSocket
voice endpoint (PRD §12 /healthz /readyz; §16).

Importing this module is cheap (no ML). The app exposes operational endpoints
from M0 so the scaffold is demonstrably runnable; the `/ws` voice endpoint is
attached in M1.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from sutradhar import __version__
from sutradhar.core.config import Settings, get_settings
from sutradhar.observability.logging import configure_logging, get_logger
from sutradhar.observability.metrics import get_metrics
from sutradhar.reliability.health import HealthRegistry

_log = get_logger("app")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, json_logs=settings.log_json)

    app = FastAPI(title="Sutradhar", version=__version__)
    app.state.settings = settings
    app.state.health = HealthRegistry()
    metrics = get_metrics()

    @app.get("/healthz")
    async def healthz() -> dict[str, Any]:
        """Liveness: the process is up."""
        return {"status": "ok", "version": __version__}

    @app.get("/readyz")
    async def readyz() -> Response:
        """Readiness: all critical components report healthy."""
        registry: HealthRegistry = app.state.health
        ready = await registry.ready()
        statuses = {s.name: s.state.value for s in await registry.check()}
        return Response(
            content=__import__("json").dumps({"ready": ready, "components": statuses}),
            media_type="application/json",
            status_code=200 if ready else 503,
        )

    @app.get("/metrics")
    async def metrics_endpoint() -> Response:
        """Prometheus scrape endpoint."""
        return Response(generate_latest(metrics.registry), media_type=CONTENT_TYPE_LATEST)

    @app.get("/")
    async def index() -> dict[str, Any]:
        return {
            "service": "sutradhar",
            "version": __version__,
            "transport_default": settings.transport.default,
            "providers": {
                "vad": settings.vad.provider,
                "stt": settings.stt.provider,
                "llm": settings.llm.provider,
                "tts": settings.tts.provider,
            },
            "note": "Voice WebSocket endpoint /ws is attached in M1.",
        }

    _log.info("app_created", version=__version__, env=settings.env)
    return app
