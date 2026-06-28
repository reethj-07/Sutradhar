"""Piper TTS (ONNX) — default synthesizer, very low first-audio latency (PRD §7).

Synthesizes each clause from the orchestrator as soon as it arrives (first-clause
synthesis, PR2). The voice model (~25-60 MB) is downloaded once to a local cache.
Blocking synthesis runs in a worker thread. Output is 16-bit PCM at the voice's
native sample rate; the transport resamples to the wire/playback rate.
"""

from __future__ import annotations

import asyncio
import urllib.request
from collections.abc import AsyncIterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sutradhar.core.types import AudioChunk
from sutradhar.observability.logging import get_logger

if TYPE_CHECKING:
    from sutradhar.core.config import Settings

_log = get_logger("providers.tts.piper")
_HF_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"


class PiperTTS:
    name = "piper"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.voice_name = settings.tts.voice
        self.sample_rate = settings.tts.sample_rate
        self._voice: Any = None
        self._model_path = Path("models") / f"{self.voice_name}.onnx"

    def _voice_urls(self) -> tuple[str, str]:
        # e.g. "en_US-amy-medium" -> en/en_US/amy/medium/en_US-amy-medium.onnx
        lang_code, name, quality = self.voice_name.split("-", 2)
        family = lang_code.split("_")[0]
        stem = f"{_HF_BASE}/{family}/{lang_code}/{name}/{quality}/{self.voice_name}.onnx"
        return stem, stem + ".json"

    def _ensure_voice(self) -> None:
        cfg = self._model_path.with_suffix(".onnx.json")
        if self._model_path.exists() and cfg.exists():
            return
        self._model_path.parent.mkdir(parents=True, exist_ok=True)
        model_url, cfg_url = self._voice_urls()
        _log.info("downloading_piper_voice", voice=self.voice_name)
        urllib.request.urlretrieve(model_url, self._model_path)
        urllib.request.urlretrieve(cfg_url, cfg)

    async def start(self) -> None:
        if self._voice is not None:
            return
        from piper import PiperVoice

        self._ensure_voice()
        self._voice = await asyncio.to_thread(PiperVoice.load, str(self._model_path))
        cfg = getattr(self._voice, "config", None)
        sr = getattr(cfg, "sample_rate", None)
        if sr:
            self.sample_rate = int(sr)
        _log.info("piper_ready", voice=self.voice_name, sample_rate=self.sample_rate)

    def _synth_sync(self, text: str) -> bytes:
        voice = self._voice
        # piper 1.2.x: synthesize_stream_raw -> iterator of int16 PCM byte chunks.
        if hasattr(voice, "synthesize_stream_raw"):
            return b"".join(voice.synthesize_stream_raw(text))
        # piper 1.3+: synthesize -> iterator of AudioChunk with int16 bytes.
        out = bytearray()
        for chunk in voice.synthesize(text):
            data = getattr(chunk, "audio_int16_bytes", None)
            if data is None:
                data = bytes(getattr(chunk, "audio", b""))
            out.extend(data)
        return bytes(out)

    async def _synth(self, text: str) -> bytes:
        return await asyncio.to_thread(self._synth_sync, text)

    async def stream(self, text: AsyncIterator[str]) -> AsyncIterator[AudioChunk]:
        if self._voice is None:
            raise RuntimeError("PiperTTS.start() must be called before stream()")
        seq = 0
        async for fragment in text:
            if not fragment.strip():
                continue
            pcm = await self._synth(fragment)
            if pcm:
                yield AudioChunk(pcm=pcm, sample_rate=self.sample_rate, seq=seq, text=fragment)
                seq += 1
        yield AudioChunk(pcm=b"", sample_rate=self.sample_rate, seq=seq, is_final=True)

    async def synthesize(self, text: str) -> AudioChunk:
        if self._voice is None:
            await self.start()
        return AudioChunk(pcm=await self._synth(text), sample_rate=self.sample_rate, text=text)

    async def aclose(self) -> None:
        self._voice = None
