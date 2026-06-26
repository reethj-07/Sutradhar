"""VAD interface — per-frame voice activity detection (PRD §6.3).

Default Silero (ONNX); swap target webrtcvad. The detector is fed fixed-size
frames and returns a speech probability per frame. It is intentionally cheap
and stateful only across a single utterance (`reset()` between turns).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from sutradhar.core.types import AudioFrame, VADResult


@runtime_checkable
class VAD(Protocol):
    """Voice-activity detector operating on individual audio frames."""

    name: str

    async def start(self) -> None: ...

    def detect(self, frame: AudioFrame) -> VADResult:
        """Classify one frame as speech/non-speech with a probability."""
        ...

    def reset(self) -> None:
        """Clear any internal state between utterances."""
        ...

    async def aclose(self) -> None: ...
