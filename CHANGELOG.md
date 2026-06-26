# Changelog

All notable changes to Sutradhar are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); this project predates
its first tagged release, so everything lives under *Unreleased* by milestone.

## [Unreleased]

### M0 — Scaffold  ✅

- Repository scaffold matching PRD §16: `core/`, `interfaces/`, `providers/`,
  `transport/`, `dialogue/`, `observability/`, `reliability/`, `tools/`, plus
  `eval/`, `clients/web/`, `mock_backend/`, `deploy/`, `tests/`, `docs/`.
- Packaging with **uv** + hatchling (`pyproject.toml`): light base deps, heavy ML
  providers behind optional extras (`stt`, `tts`, `llm`, `vad`, `memory`,
  `webrtc`, `local`, `dev`).
- Typed configuration via **pydantic-settings** (`SUTRADHAR_*`, nested `__`) with
  `.env.example`; every provider selectable by config (FR13).
- **Core interfaces** (Protocols) for Transport, VAD, STT, TurnDetector, LLM, TTS,
  MemoryStore, ToolRegistry and Tracer (PRD §6.3).
- **Core runtime primitives**: domain types, cooperative `CancellationToken`
  (barge-in backbone), bounded backpressure queues, monotonic clock, per-turn
  `LatencyTracker` (voice-to-voice = metric of record), `SessionManager`.
- **Dialogue**: turn state machine (single source of truth, with barge-in
  truncation accounting), in-memory tool registry, short-term memory window,
  lead-qualification prompt.
- **Turn detection**: hybrid acoustic + (heuristic) semantic endpointer live;
  `vad_pause` mode; smart-turn classifier slated for M2.
- **Observability skeleton**: structlog (JSON/console), Prometheus metrics
  (stage latency, voice-to-voice, tokens, barge-in, endpoints, failovers,
  active sessions), OpenTelemetry tracer with a no-op default.
- **Reliability**: retries with backoff, per-stage timeouts, circuit breaker,
  failover chain, health registry.
- **Dependency-free stub providers** for every interface (the cloud-swap target
  + a hermetic test/CI substrate + a way to exercise the pipeline before models).
- **FastAPI app**: `/healthz`, `/readyz`, `/metrics`, `/`; **CLI** (`sutradhar
  version | serve | demo | doctor | eval run`); `doctor` environment check.
- **CI** (GitHub Actions: ruff, black, mypy strict, pytest on 3.11 & 3.12),
  **pre-commit** (ruff/black/mypy), `Makefile` + `tasks.ps1`.
- **Docs**: README, architecture overview, ADR-0001/0002/0003, latency report
  template, PRD (md + pdf).
- **Tests**: unit coverage for config, types, cancellation, queues, reliability,
  state machine, turn detector, tool registry, latency, stubs, factory and the
  app endpoints.

### M1 — Core loop  🚧 (in progress)

Done:
- **Streaming half-duplex `Pipeline`** wiring Transport → VAD → STT →
  TurnDetector → Orchestrator(LLM) → TTS → Transport over bounded queues, with
  STT running as its own task so partials are available during the utterance and
  the turn detector endpoints on the fused signal.
- **`DialogueOrchestrator.respond`**: streams the LLM and splits tokens into
  TTS-ready clauses (first-clause synthesis), cancellation-aware for M2 barge-in.
- **Per-stage + voice-to-voice latency** captured per turn via `LatencyTracker`.
- **Loopback transport** + composition root (`runtime.build_pipeline`) + a
  no-hardware **`sutradhar demo`** that drives the real pipeline with stubs.
- **Integration tests** proving the spoken→spoken loop end-to-end (endpoint →
  transcript → streamed reply → audio out) with no models. Fixed a real
  concurrency bug (producer not yielding to the STT pump) found by the test.
- Stub STT now streams incremental partials; `append_spoken` reassembles clauses
  with natural spacing.

Next:
- Real providers (Silero VAD, faster-whisper STT on GPU, Ollama LLM, Piper TTS).
- WebSocket transport + browser AudioWorklet mic client + `/ws` wiring.
- Baseline P50/P95 latency report measured on the GTX 1650.
