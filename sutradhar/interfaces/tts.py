"""TTS interface — streaming text-to-speech (PRD §6.3, §8).

Default Piper (ONNX, very low first-audio latency); Kokoro-82M optional for
higher quality; cloud stubs (ElevenLabs/Cartesia) behind the same interface.
`stream()` accepts an async iterator of text fragments (LLM clauses) and yields
audio chunks, synthesizing the first clause before the full response is ready
(FR5, PR2: first-clause synthesis).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from sutradhar.core.types import AudioChunk


@runtime_checkable
class TTS(Protocol):
    """Streaming speech synthesizer."""

    name: str
    sample_rate: int

    async def start(self) -> None: ...

    def stream(self, text: AsyncIterator[str]) -> AsyncIterator[AudioChunk]:
        """Synthesize a stream of text fragments into a stream of audio chunks."""
        ...

    async def synthesize(self, text: str) -> AudioChunk:
        """Synthesize a complete string into a single chunk (canned phrases)."""
        ...

    async def aclose(self) -> None: ...
