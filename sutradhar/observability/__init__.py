"""Observability: structured logging, Prometheus metrics, OTel tracing (PRD §12).

Every turn produces a trace; every stage emits latency + outcome metrics; logs
are JSON with session/turn IDs for correlation.
"""

from __future__ import annotations

from sutradhar.observability.logging import bind_context, configure_logging, get_logger
from sutradhar.observability.metrics import Metrics, get_metrics
from sutradhar.observability.tracing import NoopTracer, get_tracer

__all__ = [
    "Metrics",
    "NoopTracer",
    "bind_context",
    "configure_logging",
    "get_logger",
    "get_metrics",
    "get_tracer",
]
