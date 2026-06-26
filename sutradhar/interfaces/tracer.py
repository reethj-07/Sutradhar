"""Tracer interface — per-turn distributed tracing (PRD §6.3, §12).

A single turn is one trace; each stage (VAD->STT->LLM->TTS) is a span; barge-in
is a span event. The default implementation wraps OpenTelemetry and exports to
Jaeger; a no-op implementation keeps the pipeline dependency-free when tracing
is disabled.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Span(Protocol):
    """An active tracing span."""

    def set_attribute(self, key: str, value: Any) -> None: ...

    def add_event(self, name: str, attributes: dict[str, Any] | None = None) -> None: ...

    def record_exception(self, exc: BaseException) -> None: ...

    def end(self) -> None: ...


@runtime_checkable
class Tracer(Protocol):
    """Creates spans and records events for turns and stages."""

    def span(
        self,
        name: str,
        attributes: dict[str, Any] | None = None,
    ) -> AbstractContextManager[Span]:
        """Open a span as a context manager."""
        ...

    def event(self, name: str, attributes: dict[str, Any] | None = None) -> None:
        """Record an event on the current span."""
        ...
