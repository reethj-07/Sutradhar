"""Audio helpers shared by providers and transports.

All audio in Sutradhar is mono 16-bit little-endian PCM on the wire; models work
in float32 [-1, 1]. These helpers convert between the two and resample between
rates (browser 48 kHz / pipeline 16 kHz / Piper 22.05 kHz / telephony 8 kHz).
Resampling is dependency-free linear interpolation (numpy only) — good enough for
speech and avoids pulling scipy/librosa.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

_INT16_MAX = 32767.0


def pcm16_to_float32(pcm: bytes) -> NDArray[np.float32]:
    """Decode little-endian int16 PCM bytes to float32 samples in [-1, 1]."""
    if not pcm:
        return np.zeros(0, dtype=np.float32)
    # Trim a stray odd byte so np.frombuffer never raises.
    if len(pcm) % 2:
        pcm = pcm[:-1]
    ints = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
    return ints / _INT16_MAX


def float32_to_pcm16(samples: NDArray[np.float32]) -> bytes:
    """Encode float32 samples in [-1, 1] to little-endian int16 PCM bytes."""
    if samples.size == 0:
        return b""
    clipped = np.clip(samples, -1.0, 1.0)
    ints = np.round(clipped * _INT16_MAX).astype("<i2")
    return ints.tobytes()


def resample(samples: NDArray[np.float32], src_sr: int, dst_sr: int) -> NDArray[np.float32]:
    """Resample float32 mono audio from `src_sr` to `dst_sr` (linear interpolation)."""
    if src_sr == dst_sr or samples.size == 0:
        return samples.astype(np.float32, copy=False)
    duration = samples.size / float(src_sr)
    dst_n = round(duration * dst_sr)
    if dst_n <= 0:
        return np.zeros(0, dtype=np.float32)
    # Sample positions in the source timeline for each destination sample.
    src_idx = np.linspace(0.0, samples.size - 1, dst_n, dtype=np.float64)
    out = np.interp(src_idx, np.arange(samples.size), samples)
    return out.astype(np.float32)


def resample_pcm16(pcm: bytes, src_sr: int, dst_sr: int) -> bytes:
    """Resample int16 PCM bytes from `src_sr` to `dst_sr`."""
    if src_sr == dst_sr:
        return pcm
    return float32_to_pcm16(resample(pcm16_to_float32(pcm), src_sr, dst_sr))


def rms(samples: NDArray[np.float32]) -> float:
    """Root-mean-square level of float32 audio in [0, 1]."""
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
