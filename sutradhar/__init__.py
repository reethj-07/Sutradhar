"""Sutradhar — an open-source, low-latency real-time Voice AI agent platform.

The name is Sanskrit for the *sutradhar*: the orchestrator who "holds the
strings" of a performance. This package is that orchestrator for a streaming
Speech-to-Text -> LLM -> Text-to-Speech voice pipeline with a custom
turn-taking / barge-in engine, provider-swappable components, evaluation,
observability and fault tolerance.

Public surface is intentionally small at import time and free of heavy ML
dependencies; concrete providers are imported lazily from
:mod:`sutradhar.providers` only when selected via configuration.
"""

from __future__ import annotations

__version__ = "0.1.0"
__author__ = "Reeth Jain"

__all__ = ["__author__", "__version__"]
