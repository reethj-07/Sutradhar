"""Reliability primitives (PRD §13): timeouts, retries with backoff, circuit
breakers, provider failover, graceful degradation and health surfacing.

These keep a session running under partial failure — a component failure
degrades the conversation, it never crashes the session (NFR6).
"""

from __future__ import annotations

from sutradhar.reliability.circuit_breaker import CircuitBreaker, CircuitState
from sutradhar.reliability.failover import FailoverChain
from sutradhar.reliability.health import HealthRegistry, HealthStatus
from sutradhar.reliability.retries import retry_async, with_timeout

__all__ = [
    "CircuitBreaker",
    "CircuitState",
    "FailoverChain",
    "HealthRegistry",
    "HealthStatus",
    "retry_async",
    "with_timeout",
]
