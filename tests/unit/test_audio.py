"""Audio helpers: PCM<->float round-trip and resampling invariants."""

from __future__ import annotations

import numpy as np
import pytest

from sutradhar.core.audio import (
    float32_to_pcm16,
    pcm16_to_float32,
    resample,
    resample_pcm16,
    rms,
)


def test_pcm_float_roundtrip() -> None:
    samples = np.array([0.0, 0.5, -0.5, 1.0, -1.0], dtype=np.float32)
    pcm = float32_to_pcm16(samples)
    back = pcm16_to_float32(pcm)
    assert np.allclose(samples, back, atol=1e-4)


def test_empty_audio() -> None:
    assert pcm16_to_float32(b"").size == 0
    assert float32_to_pcm16(np.zeros(0, dtype=np.float32)) == b""
    assert rms(np.zeros(0, dtype=np.float32)) == 0.0


def test_odd_byte_is_trimmed() -> None:
    # 3 bytes => one int16 sample + a dropped stray byte (no crash).
    assert pcm16_to_float32(b"\x00\x10\x7f").size == 1


def test_clipping() -> None:
    loud = np.array([2.0, -2.0], dtype=np.float32)
    back = pcm16_to_float32(float32_to_pcm16(loud))
    assert np.all(back <= 1.0) and np.all(back >= -1.0)


def test_resample_changes_length_proportionally() -> None:
    samples = np.sin(np.linspace(0, 10, 16000, dtype=np.float32))
    down = resample(samples, 16000, 8000)
    assert abs(down.size - 8000) <= 1
    up = resample(samples, 16000, 48000)
    assert abs(up.size - 48000) <= 1


def test_resample_noop_same_rate() -> None:
    samples = np.array([0.1, 0.2, 0.3], dtype=np.float32)
    assert resample(samples, 16000, 16000) is samples or np.array_equal(
        resample(samples, 16000, 16000), samples
    )


def test_resample_pcm16_bytes() -> None:
    pcm = float32_to_pcm16(np.sin(np.linspace(0, 5, 22050, dtype=np.float32)))
    out = resample_pcm16(pcm, 22050, 16000)
    # 22050 -> 16000 should be ~16000 samples => ~32000 bytes.
    assert abs(len(out) // 2 - 16000) <= 2


def test_rms_of_constant() -> None:
    assert rms(np.full(100, 0.5, dtype=np.float32)) == pytest.approx(0.5, abs=1e-6)
