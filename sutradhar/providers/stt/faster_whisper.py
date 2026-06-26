"""faster-whisper STT (CTranslate2) on GPU — default transcriber (PRD §7). Wired in M1.

Streaming strategy (M1): maintain a rolling audio buffer, run ``small``
int8_float16 inference on the GPU over a sliding window to emit partials, and
finalize on endpoint. ``faster_whisper`` is imported inside ``start()`` so this
module imports without CUDA present.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from sutradhar.core.types import AudioFrame, TranscriptChunk

if TYPE_CHECKING:
    from sutradhar.core.config import Settings


class FasterWhisperSTT:
    name = "faster-whisper"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model = None  # faster_whisper.WhisperModel, loaded in start()

    async def start(self) -> None:
        raise NotImplementedError("FasterWhisperSTT is wired in M1 (WhisperModel load on GPU)")

    def stream(
        self, audio: AsyncIterator[AudioFrame]
    ) -> AsyncIterator[TranscriptChunk]:  # pragma: no cover - M1
        raise NotImplementedError("FasterWhisperSTT is wired in M1")

    async def transcribe(self, pcm: bytes, sample_rate: int) -> str:  # pragma: no cover
        raise NotImplementedError

    async def aclose(self) -> None: ...
