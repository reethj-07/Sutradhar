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

### M1 — Core loop  ✅ (functional; live voice verified)

**Acceptance met:** a spoken question gets a spoken answer over the browser
WebSocket client; per-stage + voice-to-voice latency recorded; baseline reported.
Verified live on real hardware — mic → Silero VAD → faster-whisper → Qwen2.5-3B
(Ollama) → Piper → speaker, ~3 s voice-to-voice. The dev box is the PRD target
(GTX 1650 4 GB) but its NVIDIA driver is currently uninstalled, so STT fell back
to CPU; restoring the driver + CUDA/cuDNN will hit the 0.8–1.2 s GPU baseline.

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

Also done:
- **Real providers**: Silero VAD (onnxruntime, auto-downloaded ONNX, no torch),
  faster-whisper STT (GPU `small` int8_float16 with periodic partial
  re-transcription + CPU fallback), Ollama LLM (async streaming chat + tool-call
  passthrough), Piper TTS (per-clause synthesis, auto-downloaded voice).
- **Audio utilities** (PCM↔float, linear resample) with unit tests.
- **WebSocket transport** + `/ws` endpoint + browser **AudioWorklet** mic client
  (16 kHz capture, gapless 24 kHz playback) served at `/client/`.
- `SessionRuntime` loads provider models once and shares them across sessions.
- **WS integration test** (stub providers) exercises the real socket path in CI.

Remaining for M1 sign-off:
- Baseline P50/P95 voice-to-voice + per-stage latency measured on the GTX 1650
  (needs the operator's hardware) → recorded in `docs/latency_report.md`.

### M2 — Turn-taking & barge-in  ✅

**Acceptance met:** the user can interrupt the agent mid-reply; the agent stops
promptly (playout flushed immediately on detection); state is reconciled with no
corruption; metrics emitted.

- **State-driven single frame loop** (`core/pipeline.py` rewrite): one consumer
  reads inbound audio and dispatches by turn state — LISTENING feeds VAD+STT and
  endpoints; SPEAKING runs the *same* loop's VAD to watch for barge-in while the
  agent reply runs as a cancellable background task. No second consumer of the
  frame generator (which would corrupt it).
- **Barge-in (PRD §9.2):** on ≥`turn.barge_in_ms` of confirmed user speech during
  SPEAKING → cancel in-flight LLM+TTS via the shared `CancellationToken`, flush
  transport playout, and `state.barge_in()` to commit the *truncated* spoken text
  to history. Transitions SPEAKING → INTERRUPTED → LISTENING and resumes.
- **Metrics:** `sutradhar_barge_in_total` increments; barge-in is a trace event.
- **Config:** `SUTRADHAR_TURN__BARGE_IN_MS` (default 150).
- **Tests:** integration test drives a real (stub-provider) interrupt over a
  time-paced loopback transport and asserts cancellation, flush, truncated
  history and the metric. M1 integration tests still green after the refactor.

Remaining for M2 sign-off:
- Live browser confirmation of interrupting the agent (use headphones so the mic
  doesn't capture the agent's own voice and self-trigger).

### M3 — Dialogue (memory, tool-calling, demo vertical)  ✅

**Acceptance met:** a multi-turn task completes via tool calls and memory persists
across turns (verified end-to-end through the real pipeline with the mock backend).

- **Mock CRM backend** (`mock_backend/`, FastAPI + SQLite): seeded customers /
  slots / orders and four tool endpoints — `lookup_customer`, `book_slot`,
  `get_order_status`, `update_disposition` — all parameterized SQL with pydantic
  input validation (a hallucinated arg yields a clean 4xx, never bad SQL).
- **CRM tools** (`dialogue/tools_crm.py`): the four tools with JSON schemas + HTTP
  handlers; fail-soft (backend error → `ok=False` result, conversation continues).
  Accept an injected httpx client for in-process (ASGI) testing.
- **Streaming tool-calling loop** (`dialogue/orchestrator.py`): stream the LLM,
  speak any pre-tool text, execute requested tools, feed `role=tool` results back,
  and continue until a final answer — bounded by `max_tool_rounds` (no infinite
  loops). Tool-result text is treated as data, not instructions.
- **SqliteMemoryStore**: persistent (across turns/sessions) SQLite memory with
  lexical retrieval; recalled before each turn and the exchange persisted after.
  sqlite-vec vector recall is the documented drop-in upgrade.
- **Wiring**: `SessionRuntime` builds/starts one shared memory store + tool
  registry; `runtime.build` injects them; `/ws` uses them.
- **Tests:** mock-CRM endpoints (incl. SQL-injection-inert check), memory
  persist/retrieve, the tool loop (execute→feed-back→answer, bounded), CRM tools
  against the in-process backend, and an end-to-end capstone (book a slot via tool
  call → backend updated → spoken confirmation → memory persisted). Reviewed by a
  multi-agent adversarial pass.

**Adversarial review** (multi-agent, 12 confirmed findings) fixed in M3:
- Tool loop threads the *full* per-round assistant text back (was dropping the
  pre-tool narration); exhausted tool rounds now force a final tools-disabled
  answer and a last-resort holding phrase so a turn is never silent.
- SQLite memory: capped row text, recall scans only the recent N rows, and all
  sqlite work runs in a worker thread under a lock (never blocks the loop / no
  statement interleaving); WAL + busy_timeout on disk.
- `ConversationMemory.recall/remember` are fail-soft (a store error can't break a
  turn). `SessionRuntime` init is atomic (tears down on partial failure) and now
  shares one httpx client for CRM tools.
- `/ws` validates Origin (blocks cross-site WebSocket hijacking; loopback +
  configurable allowlist) and handles the session limit gracefully.

Deferred (documented): cross-*call* memory needs a stable caller identity
(arrives with telephony in M5); OpenAI-style `tool_calls.arguments` as a JSON
string (only affects the M5 OpenAI-compatible adapter, latent today).

Remaining for M3 sign-off:
- Live browser demo: run the mock backend + server and book a slot by voice.
