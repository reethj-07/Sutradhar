# ADR-0004: Barge-in via a single state-driven frame loop

- **Status:** Accepted
- **Date:** 2026-06-28

## Context

Barge-in (PRD §9.2) requires monitoring the inbound audio for user speech *while
the agent is speaking*, then cancelling the in-flight LLM + TTS within the ≤200 ms
budget and reconciling state. The M1 pipeline was half-duplex: `_listen()` then
`_respond()` ran sequentially, and nothing read inbound frames during the agent's
reply, so there was no way to detect an interruption.

The obvious approach — spawn a second task that reads frames during SPEAKING —
breaks on a subtle point: the inbound frames come from a single async generator
(`transport.recv_audio()`). Two concurrent consumers, or cancelling a task that
is suspended in the generator's `__anext__`, corrupts/finalizes the generator, so
the next listen phase gets a dead stream.

## Decision

Use **one consumer**: a single state-machine-driven frame loop in `Pipeline.run()`
that dispatches each frame by `TurnState`.

- **LISTENING** — feed VAD + STT (STT runs as its own pump task fed by a bounded
  queue); the turn detector decides the endpoint. On endpoint, launch the agent
  reply as a **cancellable background task** and switch to SPEAKING.
- **SPEAKING** — the same loop keeps running VAD on each inbound frame. After
  `turn.barge_in_ms` of confirmed speech it cancels the reply's shared
  `CancellationToken` (which unwinds the LLM stream and TTS), flushes transport
  playout, and calls `state.barge_in()` to commit the *truncated* spoken text to
  history — then returns to LISTENING.

The frame generator is therefore never read by two tasks and never has a pending
`__anext__` cancelled. The cancellable unit is the agent reply task, not the
frame reader.

## Consequences

- Barge-in detection and the listen loop share one VAD pass; no generator
  corruption; clean cancellation semantics.
- The ~`barge_in_ms` of audio consumed while confirming the interruption is not
  fed to the next utterance's STT (a small, acceptable loss; can be buffered
  later if needed).
- Stop latency is dominated by the confirmation window, not the cancellation:
  the flush is immediate, so the agent goes quiet right after detection.
- Echo matters: on speakers the mic can hear the agent and self-trigger;
  headphones (or robust echo cancellation) are recommended until full-duplex /
  echo handling lands.
