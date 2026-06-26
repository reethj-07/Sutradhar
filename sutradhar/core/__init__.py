"""Core runtime: domain types, config, cancellation, bounded queues, clock.

This subpackage is dependency-light (no ML libs) and is safe to import from
anywhere, including tests and tooling.
"""

from __future__ import annotations

from sutradhar.core.cancellation import CancellationToken, OperationCancelled
from sutradhar.core.clock import Clock, MonotonicClock, monotonic_ms
from sutradhar.core.config import Settings, get_settings
from sutradhar.core.errors import (
    ProviderError,
    ProviderTimeout,
    SutradharError,
    TransportClosed,
)
from sutradhar.core.types import (
    AudioChunk,
    AudioFrame,
    LatencyMark,
    LLMResponseEvent,
    Message,
    Role,
    SessionEvent,
    SessionEventType,
    Stage,
    ToolCall,
    ToolResult,
    TranscriptChunk,
    TurnState,
    VADResult,
)

__all__ = [
    "AudioChunk",
    "AudioFrame",
    "CancellationToken",
    "Clock",
    "LLMResponseEvent",
    "LatencyMark",
    "Message",
    "MonotonicClock",
    "OperationCancelled",
    "ProviderError",
    "ProviderTimeout",
    "Role",
    "SessionEvent",
    "SessionEventType",
    "Settings",
    "Stage",
    "SutradharError",
    "ToolCall",
    "ToolResult",
    "TranscriptChunk",
    "TransportClosed",
    "TurnState",
    "VADResult",
    "get_settings",
    "monotonic_ms",
]
