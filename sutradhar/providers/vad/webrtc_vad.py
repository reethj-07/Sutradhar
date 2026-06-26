"""webrtcvad — alternative VAD implementation (swap target, PRD §6.3). Wired in M2."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sutradhar.core.types import AudioFrame, VADResult

if TYPE_CHECKING:
    from sutradhar.core.config import Settings


class WebRtcVAD:
    name = "webrtcvad"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._vad = None  # webrtcvad.Vad, loaded in start()

    async def start(self) -> None:
        raise NotImplementedError("WebRtcVAD is wired in M2")

    def detect(self, frame: AudioFrame) -> VADResult:  # pragma: no cover - M2
        raise NotImplementedError

    def reset(self) -> None: ...

    async def aclose(self) -> None: ...
