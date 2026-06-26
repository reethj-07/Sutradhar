"""Shared pytest fixtures and test configuration for Sutradhar."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

# Tests must never depend on a developer's local .env.
os.environ.setdefault("SUTRADHAR_ENV", "ci")


@pytest.fixture
def fake_clock() -> object:
    from sutradhar.core.clock import FakeClock

    return FakeClock()


@pytest.fixture
def settings_stub() -> Iterator[object]:
    """Settings with every provider forced to the dependency-free stub."""
    from sutradhar.core.config import Settings

    s = Settings(
        vad={"provider": "stub"},
        stt={"provider": "stub"},
        turn={"provider": "stub"},
        llm={"provider": "stub"},
        tts={"provider": "stub"},
        memory={"provider": "stub"},
    )
    yield s
