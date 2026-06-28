# Sutradhar — living TODO

Milestone-gated per PRD §17. Each milestone must meet its acceptance criteria
before the next begins. `[x]` done · `[~]` in progress · `[ ]` pending.

## M0 — Scaffold  ✅ (acceptance: setup works on Windows; CI green; interfaces defined)
- [x] Repo structure (PRD §16), packaging (uv + pyproject), extras
- [x] pydantic-settings config + `.env.example`
- [x] Core interfaces (Transport/VAD/STT/TurnDetector/LLM/TTS/Memory/Tools/Tracer)
- [x] Core primitives: types, cancellation, queues, clock, latency, session, pipeline skel
- [x] Dialogue: state machine, tool registry, memory window, prompts
- [x] Observability skeleton (logging/metrics/tracing) + reliability primitives
- [x] Stub providers (all interfaces) + config-driven factory
- [x] FastAPI app (`/healthz` `/readyz` `/metrics`) + CLI + `doctor`
- [x] CI, pre-commit, Makefile/tasks.ps1, README/CHANGELOG/ADRs
- [x] Unit tests green; ruff/black/mypy clean

## M1 — Core loop  ✅  (acceptance met: spoken Q → spoken A live; latency recorded)
<!-- Live-verified in browser: mic -> Silero -> faster-whisper -> Qwen2.5-3B -> Piper -> speaker,
     ~3s voice-to-voice on CPU. GPU baseline (GTX 1650) still to capture. -->

- [x] Silero VAD (onnxruntime, CPU) — real `detect()` with auto-downloaded ONNX
- [x] faster-whisper STT (GPU, int8_float16) — streaming partials + final (+CPU fallback)
- [x] Ollama LLM (Qwen2.5-3B) — streaming tokens + tool-call parsing
- [x] Piper TTS — first-clause streaming synthesis (auto-downloaded voice)
- [x] WebSocket transport (server) + browser AudioWorklet mic client + playback
- [x] Pipeline: bounded-queue stage wiring; half-duplex loop
- [x] LatencyTracker wired through stages (voice-to-voice + per-stage)
- [x] Integration tests: stub loopback + real `/ws` socket path; `sutradhar demo`
- [ ] Baseline P50/P95 captured on GTX 1650 and written to docs/latency_report.md (needs hardware)

## M2 — Turn-taking & barge-in  (acceptance: interrupt; stop ≤200 ms; no corruption; metrics)
- [ ] Semantic endpoint classifier (replace M0 heuristic) behind TurnDetector
- [ ] Barge-in: VAD-during-SPEAKING → cancel LLM+TTS, flush, reconcile state
- [ ] webrtcvad swap; endpoint accuracy metrics (false-early/false-late)
- [ ] Barge-in latency + correctness tests

## M3 — Dialogue  (acceptance: multi-turn task via tools; memory persists)
- [ ] SQLite + sqlite-vec memory store (real)
- [ ] Mock CRM backend (lookup_customer/book_slot/get_order_status/update_disposition)
- [ ] Orchestrator tool-call loop; memory injection; finalize demo vertical

## M4 — Evaluation  (acceptance: `make eval` runs scenarios; CI regression gate)
- [ ] Synthetic caller simulator (LLM persona → TTS → pipeline)
- [ ] ASR-noise / adversarial injection
- [ ] LLM-as-judge scoring (rubrics); latency eval (P50/P95)
- [ ] ≥10 scenarios; regression gate enabled in CI

## M5 — Transport & reliability  (acceptance: telephony-sim; kill provider survives; ceiling)
- [ ] Telephony-sim transport (8 kHz, SIP-like lifecycle, jitter buffer)
- [ ] aiortc WebRTC transport (optional)
- [ ] OpenAI-compatible LLM adapter (commercial swap)
- [ ] Failover/degradation wired into the live pipeline; provider-kill test
- [ ] Load test; document concurrency ceiling

## M6 — Ops & polish  (acceptance: `docker compose up` full stack; dashboards; demo)
- [ ] Grafana dashboards (latency, tokens/s, barge-in, endpoint accuracy) as JSON
- [ ] Docker Compose full stack finalized; one-command demo + script
- [ ] Latency report with measured numbers; ADRs; Kokoro TTS option
