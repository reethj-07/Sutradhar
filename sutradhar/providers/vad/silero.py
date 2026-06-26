"""Silero VAD (ONNX) — default voice-activity detector (PRD §7). Wired in M1.

Loads the Silero VAD ONNX model via onnxruntime (CPU), runs it on 30 ms frames
and returns a speech probability. Heavy imports are deferred to ``start()`` so
importing this module never pulls onnxruntime.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sutradhar.core.types import AudioFrame, VADResult

if TYPE_CHECKING:
    from sutradhar.core.config import Settings


class SileroVAD:
    name = "silero"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.threshold = settings.vad.threshold
        self._session = None  # onnxruntime.InferenceSession, loaded in start()

    async def start(self) -> None:
        raise NotImplementedError("SileroVAD is wired in M1 (onnxruntime model load)")

    def detect(self, frame: AudioFrame) -> VADResult:  # pragma: no cover - M1
        raise NotImplementedError

    def reset(self) -> None: ...

    async def aclose(self) -> None: ...
