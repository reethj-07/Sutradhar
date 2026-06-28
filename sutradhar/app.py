"""FastAPI application: health, readiness, metrics, the voice WebSocket and the
browser client (PRD §12 /healthz /readyz; §16; M1 /ws).

Importing this module is cheap (no ML). Provider models load lazily on the first
WebSocket connection via :class:`SessionRuntime`, so `/healthz` and the static
client are available instantly.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Response, WebSocket
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from sutradhar import __version__
from sutradhar.core.config import Settings, get_settings
from sutradhar.observability.logging import configure_logging, get_logger
from sutradhar.observability.metrics import get_metrics
from sutradhar.observability.tracing import get_tracer
from sutradhar.reliability.health import HealthRegistry
from sutradhar.runtime import SessionRuntime
from sutradhar.transport.websocket import WebSocketTransport

_log = get_logger("app")

_CLIENT_DIR = Path(__file__).resolve().parent.parent / "clients" / "web"
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}


def _origin_allowed(origin: str | None, settings: Settings) -> bool:
    """Allow loopback origins (and a configured allowlist); reject the rest.

    Browsers don't apply same-origin policy to WebSockets, so without this a page
    the user visits could open a session against their local instance (CSWSH).
    A missing Origin (native/non-browser client) is allowed.
    """
    if not origin:
        return True
    if origin in settings.security.allowed_ws_origins:
        return True
    from urllib.parse import urlparse

    host = urlparse(origin).hostname or ""
    return host in _LOOPBACK_HOSTS


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, json_logs=settings.log_json)
    metrics = get_metrics()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.runtime = SessionRuntime(settings)
        # Pre-load + warm provider models at startup (when using real providers)
        # so the first connection is instant. Guarded: if a provider is missing
        # or down, fall back to lazy load on first connection.
        if settings.stt.provider != "stub":
            try:
                await app.state.runtime.ensure_components()
                _log.info("components_prewarmed")
            except Exception as exc:  # degrade to lazy load on first connection
                _log.warning("prewarm_failed_will_load_lazily", error=str(exc))
        yield
        await app.state.runtime.aclose()

    app = FastAPI(title="Sutradhar", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.state.health = HealthRegistry()

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
            content=json.dumps({"ready": ready, "components": statuses}),
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
            "client": "/client/" if _CLIENT_DIR.exists() else None,
            "websocket": "/ws",
        }

    @app.websocket("/ws")
    async def voice_ws(websocket: WebSocket) -> None:
        """Voice session: browser PCM in -> agent PCM out, interruptible (M1/M2)."""
        # Reject cross-site WebSocket hijacking before accepting the handshake.
        if not _origin_allowed(websocket.headers.get("origin"), settings):
            _log.warning("ws_origin_rejected", origin=websocket.headers.get("origin"))
            await websocket.close(code=1008)  # policy violation
            return
        await websocket.accept()
        runtime: SessionRuntime = app.state.runtime
        try:
            await runtime.ensure_components()
        except Exception as exc:  # model load failed — report and bail
            _log.error("component_start_failed", error=str(exc))
            await websocket.send_json({"event": "error", "detail": {"message": str(exc)}})
            await websocket.close()
            return

        try:
            session = await runtime.manager.create()
        except RuntimeError as exc:  # session limit reached — fail gracefully
            _log.warning("session_limit_reached", error=str(exc))
            await websocket.send_json({"event": "error", "detail": {"message": "server busy"}})
            await websocket.close(code=1013)  # try again later
            return
        metrics.active_sessions.inc()
        transport = WebSocketTransport(
            websocket, session.session_id, sample_rate=settings.audio.sample_rate
        )
        pipeline = runtime.build(session, transport, metrics=metrics, tracer=get_tracer(settings))
        _log.info("ws_session_started", session_id=session.session_id)
        try:
            await pipeline.run()
        except Exception as exc:  # never let one session crash the server
            _log.warning("ws_session_error", session_id=session.session_id, error=str(exc))
        finally:
            metrics.active_sessions.dec()
            await runtime.manager.close(session.session_id)
            await transport.close()
            _log.info("ws_session_ended", session_id=session.session_id)

    if _CLIENT_DIR.exists():
        app.mount("/client", StaticFiles(directory=str(_CLIENT_DIR), html=True), name="client")

    _log.info("app_created", version=__version__, env=settings.env)
    return app
