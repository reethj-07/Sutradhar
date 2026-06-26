"""Latency tracker: voice-to-voice is the metric of record (PRD §8, K1)."""

from __future__ import annotations

import pytest

from sutradhar.core.clock import FakeClock
from sutradhar.core.latency import LatencyTracker
from sutradhar.core.types import Stage


def test_stage_timing_with_fake_clock() -> None:
    clock = FakeClock()
    lt = LatencyTracker(clock=clock)
    lt.begin_turn("t1")

    lt.start_stage(Stage.STT)
    clock.tick(180)
    lt.end_stage(Stage.STT, provider="faster-whisper")

    report = lt.current
    assert report is not None
    assert report.marks[Stage.STT].elapsed_ms == pytest.approx(180)


def test_voice_to_voice_computation() -> None:
    clock = FakeClock()
    lt = LatencyTracker(clock=clock)
    lt.begin_turn("t1")

    lt.mark_endpoint()  # t = 0
    clock.tick(900)
    lt.mark_first_audio()  # t = 900
    clock.tick(500)
    lt.mark_first_audio()  # ignored — only first byte counts

    report = lt.end_turn()
    assert report is not None
    assert report.voice_to_voice_ms == pytest.approx(900)
    assert report.as_dict()["voice_to_voice"] == pytest.approx(900)


def test_stage_context_manager() -> None:
    clock = FakeClock()
    lt = LatencyTracker(clock=clock)
    lt.begin_turn("t1")
    with lt.stage(Stage.LLM, provider="ollama"):
        clock.tick(420)
    assert lt.current is not None
    assert lt.current.marks[Stage.LLM].elapsed_ms == pytest.approx(420)
