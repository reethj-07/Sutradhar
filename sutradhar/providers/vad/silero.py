"""Silero VAD (ONNX via onnxruntime) — default voice-activity detector (PRD §7).

Runs the tiny Silero v5 VAD model on CPU. The model needs fixed 512-sample
windows at 16 kHz, so incoming frames (any size) are buffered and the model runs
once a window is available; the last probability is held for intermediate frames.
The ~1.8 MB ONNX is downloaded once to a local cache (no torch dependency).
"""

from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from sutradhar.core.audio import pcm16_to_float32
from sutradhar.core.types import AudioFrame, VADResult
from sutradhar.observability.logging import get_logger

if TYPE_CHECKING:
    from sutradhar.core.config import Settings

_log = get_logger("providers.vad.silero")

# Official Silero v5 ONNX model (small; CPU). Cached under ./models on first run.
_MODEL_URL = "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx"
_WINDOW = 512  # samples required by the v5 model at 16 kHz


class SileroVAD:
    name = "silero"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.threshold = settings.vad.threshold
        self.sample_rate = 16000  # Silero v5 supports 8k/16k; pipeline uses 16k
        self._model_path = Path("models") / "silero_vad.onnx"
        self._session: Any = None
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._buffer = np.zeros(0, dtype=np.float32)
        self._last_prob = 0.0

    def _ensure_model(self) -> None:
        if self._model_path.exists():
            return
        self._model_path.parent.mkdir(parents=True, exist_ok=True)
        _log.info("downloading_silero_vad", url=_MODEL_URL, dest=str(self._model_path))
        urllib.request.urlretrieve(_MODEL_URL, self._model_path)

    async def start(self) -> None:
        if self._session is not None:
            return
        import onnxruntime as ort

        self._ensure_model()
        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self._session = ort.InferenceSession(
            str(self._model_path),
            sess_options=opts,
            providers=["CPUExecutionProvider"],
        )
        _log.info("silero_vad_ready", threshold=self.threshold)

    def _infer(self, window: np.ndarray) -> float:
        inputs = {
            "input": window.reshape(1, -1).astype(np.float32),
            "state": self._state,
            "sr": np.array(self.sample_rate, dtype=np.int64),
        }
        out, self._state = self._session.run(None, inputs)
        return float(out[0][0])

    def detect(self, frame: AudioFrame) -> VADResult:
        if self._session is None:
            raise RuntimeError("SileroVAD.start() must be called before detect()")
        samples = pcm16_to_float32(frame.pcm)
        self._buffer = np.concatenate([self._buffer, samples])
        # Consume as many full windows as we have; keep the last probability.
        while self._buffer.size >= _WINDOW:
            self._last_prob = self._infer(self._buffer[:_WINDOW])
            self._buffer = self._buffer[_WINDOW:]
        return VADResult(
            is_speech=self._last_prob >= self.threshold,
            probability=self._last_prob,
            timestamp_ms=frame.timestamp_ms,
        )

    def reset(self) -> None:
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._buffer = np.zeros(0, dtype=np.float32)
        self._last_prob = 0.0

    async def aclose(self) -> None:
        self._session = None
