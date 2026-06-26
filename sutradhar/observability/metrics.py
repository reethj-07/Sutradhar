"""Prometheus metrics (PRD §12).

Histograms/counters/gauges for stage latency, tokens/sec, endpoint accuracy,
barge-in count, error rates and active sessions — scraped by Prometheus and
visualized in Grafana (PR5). A single registry instance is shared process-wide;
`get_metrics()` returns it. Buckets target the sub-second voice-to-voice budget.
"""

from __future__ import annotations

from functools import lru_cache

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    start_http_server,
)

# Latency buckets (seconds) tuned to the PRD §8 budget: fine-grained under 1.5s.
_LATENCY_BUCKETS = (
    0.02,
    0.05,
    0.1,
    0.15,
    0.2,
    0.3,
    0.4,
    0.6,
    0.8,
    1.0,
    1.2,
    1.5,
    2.0,
    3.0,
    5.0,
)


class Metrics:
    """Container for all Sutradhar metrics, bound to a registry."""

    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        self.registry = registry or CollectorRegistry(auto_describe=True)

        self.stage_latency = Histogram(
            "sutradhar_stage_latency_seconds",
            "Per-stage latency within a turn.",
            labelnames=("stage", "provider"),
            buckets=_LATENCY_BUCKETS,
            registry=self.registry,
        )
        self.voice_to_voice = Histogram(
            "sutradhar_voice_to_voice_seconds",
            "End-of-user-speech to first agent audio byte (metric of record).",
            buckets=_LATENCY_BUCKETS,
            registry=self.registry,
        )
        self.llm_tokens = Counter(
            "sutradhar_llm_tokens_total",
            "LLM tokens generated.",
            labelnames=("provider",),
            registry=self.registry,
        )
        self.barge_in = Counter(
            "sutradhar_barge_in_total",
            "Confirmed barge-in (user interruption) events.",
            registry=self.registry,
        )
        self.endpoint_decisions = Counter(
            "sutradhar_endpoint_decisions_total",
            "Endpoint decisions by outcome (true/false_early/false_late).",
            labelnames=("outcome",),
            registry=self.registry,
        )
        self.errors = Counter(
            "sutradhar_errors_total",
            "Errors by stage and provider.",
            labelnames=("stage", "provider"),
            registry=self.registry,
        )
        self.failovers = Counter(
            "sutradhar_failovers_total",
            "Provider failover activations.",
            labelnames=("stage",),
            registry=self.registry,
        )
        self.active_sessions = Gauge(
            "sutradhar_active_sessions",
            "Currently active conversation sessions.",
            registry=self.registry,
        )
        self.turns = Counter(
            "sutradhar_turns_total",
            "Completed conversation turns.",
            registry=self.registry,
        )

    def observe_stage(self, stage: str, provider: str, seconds: float) -> None:
        self.stage_latency.labels(stage=stage, provider=provider).observe(seconds)

    def serve(self, port: int) -> None:
        """Expose /metrics on the given port (idempotent best-effort)."""
        start_http_server(port, registry=self.registry)


@lru_cache(maxsize=1)
def get_metrics() -> Metrics:
    """Process-wide metrics singleton."""
    return Metrics()
