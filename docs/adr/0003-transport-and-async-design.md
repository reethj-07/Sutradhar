# ADR-0003: WebSocket-default transport and async streaming design

- **Status:** Accepted
- **Date:** 2026-06-26

## Context

We need bidirectional low-latency audio between a browser (and later a
telephony-sim) and the pipeline, on Windows, with natural interruption support.
Two pressures: transport robustness on Windows, and a pipeline that can stream
and cancel at every stage.

## Decision

1. **WebSocket is the default transport.** aiortc/WebRTC can be flaky on Windows
   (PRD §20); WebSocket carrying raw 16 kHz mono PCM frames is robust and simple.
   WebRTC and telephony-sim live behind the same `Transport` interface and are
   opt-in.
2. **asyncio everywhere, stages as independent tasks** communicating over
   **bounded queues** with explicit backpressure (`core/queues.py`). A slow
   consumer applies backpressure instead of leaking memory.
3. **Cooperative cancellation** via a shared `CancellationToken`
   (`core/cancellation.py`) rather than relying solely on `Task.cancel()`: tokens
   are shareable, linkable, and queryable without raising — exactly what barge-in
   needs to stop LLM + TTS within the ≤200 ms budget.
4. **The turn state machine is the single source of truth.** Barge-in reconciles
   against it and records the truncated agent turn, so history never corrupts
   (PRD §9.2, §9.3).

## Consequences

- Robust local dev on Windows; WebRTC remains available without architectural
  cost.
- Backpressure + cancellation are first-class, making the latency budget and
  barge-in correctness testable.
- A little more plumbing than a blocking pipeline — paid back in interruption
  quality and observability.
