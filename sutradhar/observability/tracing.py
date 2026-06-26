"""Tracing (PRD §12). A no-op tracer by default (zero overhead, no Jaeger
needed for local dev/tests) and an OpenTelemetry-backed tracer when
`obs.tracing_enabled` is set, exporting per-turn spans to Jaeger via OTLP.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

from sutradhar.interfaces.tracer import Span, Tracer

if TYPE_CHECKING:
    from sutradhar.core.config import Settings


class _NoopSpan:
    def set_attribute(self, key: str, value: Any) -> None: ...
    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None: ...
    def record_exception(self, exc: BaseException) -> None: ...
    def end(self) -> None: ...


class NoopTracer:
    """Tracer that does nothing — used when tracing is disabled."""

    @contextmanager
    def span(self, name: str, attributes: dict[str, Any] | None = None) -> Iterator[Span]:
        yield _NoopSpan()

    def event(self, name: str, attributes: dict[str, Any] | None = None) -> None: ...


class _OTelSpanAdapter:
    def __init__(self, span: Any) -> None:
        self._span = span

    def set_attribute(self, key: str, value: Any) -> None:
        self._span.set_attribute(key, value)

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        self._span.add_event(name, attributes or {})

    def record_exception(self, exc: BaseException) -> None:
        self._span.record_exception(exc)

    def end(self) -> None:
        self._span.end()


class OTelTracer:
    """OpenTelemetry-backed tracer exporting spans to an OTLP collector (Jaeger)."""

    def __init__(self, service_name: str, otlp_endpoint: str) -> None:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True))
            )
        except Exception:  # pragma: no cover - exporter optional (otlp extra)
            pass
        trace.set_tracer_provider(provider)
        self._tracer = trace.get_tracer("sutradhar")

    @contextmanager
    def span(self, name: str, attributes: dict[str, Any] | None = None) -> Iterator[Span]:
        with self._tracer.start_as_current_span(name, attributes=attributes or {}) as s:
            yield _OTelSpanAdapter(s)

    def event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        from opentelemetry import trace

        current = trace.get_current_span()
        current.add_event(name, attributes or {})


_tracer: Tracer | None = None


def get_tracer(settings: Settings | None = None) -> Tracer:
    """Return the process-wide tracer, building it from settings on first call."""
    global _tracer
    if _tracer is not None:
        return _tracer
    if settings is None:
        from sutradhar.core.config import get_settings

        settings = get_settings()
    if settings.obs.tracing_enabled:
        try:
            _tracer = OTelTracer(settings.obs.service_name, settings.obs.otlp_endpoint)
        except Exception:  # pragma: no cover - fall back to noop if OTel missing
            _tracer = NoopTracer()
    else:
        _tracer = NoopTracer()
    return _tracer


def reset_tracer() -> None:
    """Test hook to drop the cached tracer."""
    global _tracer
    _tracer = None
