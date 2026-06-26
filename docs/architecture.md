# Architecture

This document summarizes how Sutradhar is put together. The authoritative
specification is [PRD.md](PRD.md) / [PRD.pdf](PRD.pdf); this is the engineer's
map of the code.

## Principles (PRD §6.1)

- **Streaming-first** — every stage emits incrementally (STT partials, LLM
  tokens, TTS audio chunks) so audio starts before the full response exists.
- **Interface-driven** — components depend on abstractions in
  [`sutradhar/interfaces`](../sutradhar/interfaces), never concrete providers.
- **Single source of truth** — the [turn state machine](../sutradhar/dialogue/state.py)
  owns turn state; components are stateless where possible.
- **Cancellable by design** — every in-flight op takes a
  [`CancellationToken`](../sutradhar/core/cancellation.py) (barge-in).
- **Observable by default** — every turn is a trace; every stage emits latency +
  outcome metrics.
- **Fail soft** — a component failure degrades the conversation; it never crashes
  the session.

## Layered view (PRD §6.2)

| Layer | Code | Responsibility |
|---|---|---|
| Transport | `transport/` | Move audio frames in/out of a session |
| Session | `core/session.py` | Lifecycle, per-session isolation, cleanup |
| Pipeline | `core/pipeline.py`, `providers/` | The streaming STT→LLM→TTS loop |
| Dialogue | `dialogue/` | State machine, prompts, memory, tool registry |
| Observability | `observability/` | Tracing, metrics, structured logs |
| Reliability | `reliability/` | Failover, retries, circuit breakers, health |
| Eval | `eval/` | Caller simulator, noise, judges, regression suite |

## Data flow (one turn)

```
                       bounded queues (backpressure + cancellation)
mic frames ─▶ VAD ─▶ STT(partials/final) ─▶ TurnDetector ─▶ Orchestrator
                                                                 │  stream tokens
                                                                 ▼
                                          clause buffer ─▶ TTS ─▶ audio chunks ─▶ speaker
```

- **Voice-to-voice latency** is measured from *endpoint detected* (end of user
  speech) to *first agent audio byte* — see [`core/latency.py`](../sutradhar/core/latency.py).
- **Barge-in**: while `SPEAKING`, the VAD keeps watching the inbound channel. On
  confirmed user speech the turn engine cancels the shared `CancellationToken`
  (stopping LLM + TTS), the transport flushes buffered audio, and the state
  machine commits the *truncated* spoken text to history (`TurnStateMachine.barge_in`).

## Swapping a component

1. Implement the relevant Protocol in `sutradhar/interfaces/` under
   `sutradhar/providers/<kind>/<name>.py`.
2. Add a branch in the `build_<kind>` factory in
   [`sutradhar/providers/__init__.py`](../sutradhar/providers/__init__.py).
3. Select it via config: `SUTRADHAR_<KIND>__PROVIDER=<name>`.

No pipeline/orchestration code changes — that is the whole point (NFR2, NFR8).

## Interface ⇄ implementation map

| Interface | Default (local-OSS) | Swap / stub |
|---|---|---|
| Transport | WebSocket, Telephony-sim | WebRTC, real SIP |
| VAD | Silero | webrtcvad, **stub** |
| STT | faster-whisper | Vosk/Moonshine, Deepgram, **stub** |
| TurnDetector | hybrid (acoustic+semantic) | vad_pause, **stub** |
| LLM | Ollama (Qwen2.5-3B) | OpenAI-compatible, **stub** |
| TTS | Piper | Kokoro, ElevenLabs/Cartesia, **stub** |
| MemoryStore | SQLite + sqlite-vec | Chroma, Redis, **stub** |
| Tracer | OpenTelemetry | NoopTracer |

The **stub** implementations ([`providers/stub.py`](../sutradhar/providers/stub.py))
are dependency-free, deterministic, and used by the test suite and CI.
