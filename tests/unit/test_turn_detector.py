"""Hybrid endpointing: acoustic + semantic fusion (PRD §9.1)."""

from __future__ import annotations

from sutradhar.core.config import Settings
from sutradhar.interfaces.turn import TurnContext
from sutradhar.providers.turn.detector import HybridTurnDetector


def _ctx(
    transcript: str, *, is_speech: bool, silence_ms: float, utt_ms: float = 2000
) -> TurnContext:
    return TurnContext(
        transcript=transcript,
        is_speech=is_speech,
        last_vad=None,
        trailing_silence_ms=silence_ms,
        utterance_ms=utt_ms,
    )


def test_no_endpoint_while_speaking() -> None:
    det = HybridTurnDetector(Settings(turn={"provider": "hybrid"}))
    d = det.observe(_ctx("I would like to", is_speech=True, silence_ms=0))
    assert d.endpoint is False


def test_endpoint_on_silence_and_complete_sentence() -> None:
    det = HybridTurnDetector(Settings(turn={"provider": "hybrid", "silence_ms": 400}))
    d = det.observe(_ctx("yes that works for me", is_speech=False, silence_ms=500))
    assert d.endpoint is True
    assert d.acoustic is True
    assert d.semantic is True


def test_no_premature_endpoint_on_trailing_connective() -> None:
    # "... and" implies more is coming; even with silence we should wait.
    det = HybridTurnDetector(Settings(turn={"provider": "hybrid", "silence_ms": 400}))
    d = det.observe(_ctx("I want the pro plan and", is_speech=False, silence_ms=500))
    assert d.endpoint is False
    assert d.semantic is False


def test_terminal_punctuation_endpoints_on_short_pause() -> None:
    det = HybridTurnDetector(Settings(turn={"provider": "hybrid", "silence_ms": 400}))
    d = det.observe(_ctx("book me a slot tomorrow.", is_speech=False, silence_ms=220))
    assert d.endpoint is True


def test_max_utterance_forces_endpoint() -> None:
    det = HybridTurnDetector(Settings(turn={"provider": "hybrid", "max_utterance_ms": 1000}))
    d = det.observe(_ctx("still going on and", is_speech=True, silence_ms=0, utt_ms=1500))
    assert d.endpoint is True
    assert d.reason == "max_utterance"


def test_vad_pause_mode_ignores_semantics() -> None:
    det = HybridTurnDetector(Settings(turn={"provider": "vad_pause", "silence_ms": 400}))
    # trailing connective would block hybrid, but vad_pause only checks silence.
    d = det.observe(_ctx("I want the pro plan and", is_speech=False, silence_ms=500))
    assert d.endpoint is True
    assert d.semantic is False
