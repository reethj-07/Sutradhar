"""Piper TTS (ONNX) — default synthesizer, very low first-audio latency (PRD §7). Wired in M1.

Synthesizes each LLM clause to 16-bit PCM as soon as it arrives (first-clause
synthesis, PR2). Piper is imported in ``start()``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from sutradhar.core.types import AudioChunk

if TYPE_CHECKING:
    from sutradhar.core.config import Settings


class PiperTTS:
    name = "piper"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.sample_rate = settings.tts.sample_rate
        self._voice = None  # piper.PiperVoice, loaded in start()

    async def start(self) -> None:
        raise NotImplementedError("PiperTTS is wired in M1 (PiperVoice load)")

    def stream(self, text: AsyncIterator[str]) -> AsyncIterator[AudioChunk]:  # pragma: no cover
        raise NotImplementedError("PiperTTS is wired in M1")

    async def synthesize(self, text: str) -> AudioChunk:  # pragma: no cover
        raise NotImplementedError

    async def aclose(self) -> None: ...
