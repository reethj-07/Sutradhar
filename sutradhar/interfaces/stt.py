"""STT interface — streaming speech-to-text (PRD §6.3).

Default faster-whisper (CTranslate2) on GPU; swaps to Vosk/Moonshine or a
Deepgram stub. `stream()` consumes an async iterator of audio frames and yields
:class:`TranscriptChunk` partials as speech arrives, then a final chunk when the
utterance ends (FR3, PR1: partials within ≤300 ms of speech onset).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from sutradhar.core.types import AudioFrame, TranscriptChunk


@runtime_checkable
class STT(Protocol):
    """Streaming transcriber."""

    name: str

    async def start(self) -> None: ...

    def stream(self, audio: AsyncIterator[AudioFrame]) -> AsyncIterator[TranscriptChunk]:
        """Transcribe a frame stream, yielding partial then final transcripts."""
        ...

    async def transcribe(self, pcm: bytes, sample_rate: int) -> str:
        """One-shot transcription of a complete utterance (eval / fallback)."""
        ...

    async def aclose(self) -> None: ...
