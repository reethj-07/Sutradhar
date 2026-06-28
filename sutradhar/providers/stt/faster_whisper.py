"""faster-whisper STT (CTranslate2) on GPU — default transcriber (PRD §7).

faster-whisper is not natively incremental, so we stream by buffering the
utterance and re-transcribing the growing audio on a fixed cadence to emit
partials, then transcribing once more on endpoint for the final. Blocking
inference runs in a worker thread so the event loop keeps serving the pipeline.
The ``small`` int8_float16 model fits the 4 GB GPU alongside nothing else heavy.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

import numpy as np

from sutradhar.core.audio import pcm16_to_float32, resample
from sutradhar.core.types import AudioFrame, TranscriptChunk
from sutradhar.observability.logging import get_logger

if TYPE_CHECKING:
    from sutradhar.core.config import Settings

_log = get_logger("providers.stt.faster_whisper")
_TARGET_SR = 16000


class FasterWhisperSTT:
    name = "faster-whisper"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.s = settings.stt
        self._model: Any = None
        self.emit_partials = self.s.emit_partials
        self.partial_interval_ms = float(self.s.partial_interval_ms)

    async def start(self) -> None:
        if self._model is not None:
            return
        from faster_whisper import WhisperModel

        def load(device: str, compute_type: str) -> Any:
            return WhisperModel(self.s.model_size, device=device, compute_type=compute_type)

        try:
            self._model = await asyncio.to_thread(load, self.s.device, self.s.compute_type)
        except Exception as exc:  # CUDA/cuDNN missing -> fall back to CPU int8
            _log.warning("whisper_gpu_load_failed_falling_back_cpu", error=str(exc))
            self._model = await asyncio.to_thread(load, "cpu", "int8")
        _log.info("faster_whisper_ready", model=self.s.model_size, device=self.s.device)

    def _transcribe_sync(self, samples: np.ndarray) -> str:
        segments, _info = self._model.transcribe(
            samples,
            language=self.s.language,
            beam_size=self.s.beam_size,
            vad_filter=False,
            condition_on_previous_text=False,
        )
        return "".join(seg.text for seg in segments).strip()

    async def _transcribe(self, samples: np.ndarray) -> str:
        if samples.size == 0:
            return ""
        return await asyncio.to_thread(self._transcribe_sync, samples)

    async def stream(self, audio: AsyncIterator[AudioFrame]) -> AsyncIterator[TranscriptChunk]:
        if self._model is None:
            raise RuntimeError("FasterWhisperSTT.start() must be called before stream()")
        parts: list[np.ndarray] = []
        total_ms = 0.0
        last_partial_ms = 0.0

        async for frame in audio:
            s = pcm16_to_float32(frame.pcm)
            if frame.sample_rate != _TARGET_SR:
                s = resample(s, frame.sample_rate, _TARGET_SR)
            parts.append(s)
            total_ms += frame.duration_ms
            # Periodic partials are opt-in (GPU); on CPU we accumulate cheaply and
            # transcribe once at endpoint to avoid O(n^2) re-transcription cost.
            if self.emit_partials and total_ms - last_partial_ms >= self.partial_interval_ms:
                last_partial_ms = total_ms
                text = await self._transcribe(np.concatenate(parts))
                if text:
                    yield TranscriptChunk(text=text, is_final=False, end_ms=total_ms)

        final = await self._transcribe(np.concatenate(parts) if parts else np.zeros(0, np.float32))
        yield TranscriptChunk(text=final, is_final=True, confidence=1.0, end_ms=total_ms)

    async def transcribe(self, pcm: bytes, sample_rate: int) -> str:
        if self._model is None:
            await self.start()
        samples = pcm16_to_float32(pcm)
        if sample_rate != _TARGET_SR:
            samples = resample(samples, sample_rate, _TARGET_SR)
        return await self._transcribe(samples)

    async def aclose(self) -> None:
        self._model = None
