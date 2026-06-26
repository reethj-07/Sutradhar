"""Runnable demos of the streaming pipeline.

`run_stub_demo` drives the real `Pipeline` with dependency-free stub providers
over a loopback transport — no microphone, GPU or Ollama required — so the
half-duplex loop and its latency accounting are demonstrable on any machine.
The real voice demo (browser mic -> faster-whisper/Ollama/Piper) runs over the
WebSocket transport via `sutradhar serve`.
"""

from __future__ import annotations

import struct

from rich.console import Console

from sutradhar.core.config import Settings
from sutradhar.core.session import SessionManager
from sutradhar.core.types import AudioFrame
from sutradhar.runtime import build_components, build_pipeline, start_components
from sutradhar.transport.loopback import LoopbackTransport

_SR = 16000
_FRAME_MS = 20
_SAMPLES = _SR * _FRAME_MS // 1000


def _frame(seq: int, amplitude: int) -> AudioFrame:
    pcm = struct.pack(f"<{_SAMPLES}h", *([amplitude] * _SAMPLES))
    return AudioFrame(pcm=pcm, sample_rate=_SR, seq=seq, timestamp_ms=seq * _FRAME_MS)


def _scripted_audio(speech_frames: int = 14, silence_frames: int = 30) -> list[AudioFrame]:
    frames = [_frame(i, 6000) for i in range(speech_frames)]
    frames += [_frame(speech_frames + i, 0) for i in range(silence_frames)]
    return frames


async def run_stub_demo(
    console: Console | None = None, *, utterance: str = "hi, what can you do for me"
) -> None:
    """Run one half-duplex turn end-to-end with stub providers."""
    console = console or Console()
    settings = Settings.model_validate(
        {
            "env": "local",
            "vad": {"provider": "stub", "threshold": 0.02},
            "stt": {"provider": "stub"},
            "turn": {"provider": "stub", "silence_ms": 300},
            "llm": {"provider": "stub"},
            "tts": {"provider": "stub", "sample_rate": _SR},
            "memory": {"provider": "stub"},
        }
    )

    manager = SessionManager(settings)
    session = await manager.create("demo")
    components = build_components(settings)
    components.stt.next_transcript = utterance  # type: ignore[attr-defined]
    await start_components(components)
    transport = LoopbackTransport("demo", _scripted_audio(), sample_rate=_SR)
    pipeline = build_pipeline(session, transport, components=components)

    console.print(
        "[bold cyan]Sutradhar stub demo[/bold cyan] — driving the real pipeline with stubs\n"
    )
    await pipeline.run()

    report = session.latency.current
    history = session.state.history
    user = next((m.content for m in history if m.role.value == "user"), "")
    reply = next((m.content for m in reversed(history) if m.role.value == "assistant"), "")
    console.print(f"[green]caller[/green]  : {user}")
    console.print(f"[magenta]agent[/magenta]   : {reply}")
    console.print(
        f"[yellow]audio out[/yellow]: {transport.total_audio_ms:.0f} ms across {len(transport.sent)} chunks"
    )
    if report is not None and report.voice_to_voice_ms is not None:
        console.print(
            f"[yellow]v2v[/yellow]      : {report.voice_to_voice_ms:.1f} ms (stub providers; not a real latency number)"
        )
    await manager.close("demo")
