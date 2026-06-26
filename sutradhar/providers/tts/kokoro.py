"""Kokoro-82M TTS — optional higher-quality voice (PRD §7). Wired in M6 (polish)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

from sutradhar.core.types import AudioChunk

if TYPE_CHECKING:
    from sutradhar.core.config import Settings


class KokoroTTS:
    name = "kokoro"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.sample_rate = settings.tts.sample_rate

    async def start(self) -> None:
        raise NotImplementedError("KokoroTTS is wired in M6")

    def stream(self, text: AsyncIterator[str]) -> AsyncIterator[AudioChunk]:  # pragma: no cover
        raise NotImplementedError("KokoroTTS is wired in M6")

    async def synthesize(self, text: str) -> AudioChunk:  # pragma: no cover
        raise NotImplementedError

    async def aclose(self) -> None: ...
