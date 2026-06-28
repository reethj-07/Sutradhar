# Sutradhar

> *Sanskrit for the orchestrator who "holds the strings."*

A production-grade, **100% open-source, low-latency real-time Voice AI agent platform** — the engine that powers natural spoken conversations between a human and an AI agent over a phone-like channel. It streams audio in, runs **STT → LLM → TTS** with a custom **turn-taking / barge-in engine**, manages conversation state, memory and tool-calling, handles interruptions naturally, and streams audio back — with first-class **evaluation, observability, fault tolerance and deployment**.

It is deliberately *not* a generic voice assistant demo. It reads like the core of a real Voice-AI startup product, and is engineered to run entirely on a single developer machine (**Windows 11 · NVIDIA GTX 1650 4 GB VRAM · 16 GB RAM**) on a free/OSS stack — with every component behind a clean interface so it can be swapped for a commercial provider without changing the architecture.

See [docs/PRD.md](docs/PRD.md) for the full specification (the authoritative source is [docs/PRD.pdf](docs/PRD.pdf)).

---

## Hero differentiators

1. **Turn-taking & barge-in engine** — VAD + semantic endpointing + predictive turn detection, plus natural interruption handling that cancels in-flight speech and reconciles state.
2. **Provider-agnostic, swappable architecture** — STT, LLM, TTS, VAD, turn-detector and transport all behind interfaces, each with ≥2 implementations (local-OSS + cloud-stub).
3. **Built-in evaluation + observability suite** — synthetic-caller simulation, ASR-noise/adversarial injection, LLM-as-judge scoring, per-turn latency tracing, regression testing in CI.
4. **Pluggable transport** — browser (WebSocket/WebRTC) and simulated telephony (8 kHz, SIP-like lifecycle), behind one interface, with no paid carrier.
5. **Measured, optimized low latency** — an explicit, instrumented voice-to-voice latency budget with reported numbers.

## The locked stack (tuned for 4 GB VRAM)

| Concern | Choice | Placement | Why |
|---|---|---|---|
| STT | faster-whisper `small` `int8_float16` | **GPU** | Fast, accurate, ~0.5–1 GB VRAM; streams partials |
| LLM | Qwen2.5-3B-Instruct `Q4_K_M` via Ollama | **CPU + partial GPU offload** | 7B won't fit alongside STT; 3B streams fast on 16 GB RAM; tool-calling |
| TTS | Piper (default) · Kokoro-82M (optional) | **CPU** | Piper = very low first-audio latency |
| VAD | Silero (ONNX) | CPU | Tiny, accurate, low-latency |
| Turn detection | Silero pause + lightweight semantic classifier | CPU | Predictive endpointing without big VRAM cost |
| Transport | WebSocket (default) · aiortc WebRTC · telephony-sim | CPU | Robust on Windows |
| Memory | SQLite + sqlite-vec | CPU | Embedded, zero-ops, retrievable |
| Observability | OpenTelemetry/Jaeger · Prometheus/Grafana · structlog | Docker | Per-turn traces + dashboards |

**Latency budget (P50 target): ≈ 0.8–1.2 s voice-to-voice** (end-of-user-speech → first agent audio byte).

---

## Quickstart (Windows 11)

Prerequisites: [Python 3.11/3.12](https://www.python.org/), [uv](https://docs.astral.sh/uv/), and (for the full run path) [Ollama](https://ollama.com/) + an NVIDIA GPU. `uv` will fetch the right Python for you.

```powershell
# 1. Set up the dev environment (creates .venv, installs base + dev deps, pre-commit)
.\tasks.ps1 setup          # or:  make setup   (if you have GNU make)

# 2. Verify the scaffold (lint + types + tests — what CI runs)
.\tasks.ps1 check

# 3. Inspect config and try the no-hardware demo (real pipeline, stub providers)
.\.venv\Scripts\Activate.ps1
sutradhar version          # prints the provider table
sutradhar demo             # drives the real pipeline end-to-end with stubs (no GPU/Ollama)
sutradhar doctor           # checks GPU/Ollama/models for the full voice path
```

Visit `http://127.0.0.1:8080/healthz`, `/readyz`, `/metrics`, and `/` (provider summary).

> **Config:** copy `.env.example` → `.env` to override any provider/latency setting without touching code. Every setting is namespaced `SUTRADHAR_…` (nested with `__`), e.g. `SUTRADHAR_STT__MODEL_SIZE=base`.

### The full local voice path (real STT/LLM/TTS)

```powershell
.\tasks.ps1 install                       # faster-whisper, piper, onnxruntime, ollama client, sqlite-vec
winget install Ollama.Ollama              # if not already installed
ollama pull qwen2.5:3b-instruct-q4_K_M    # the default LLM
sutradhar doctor                          # confirm GPU + Ollama + model are ready
sutradhar serve                           # FastAPI + voice WebSocket on :8080
# then open the browser mic client:
start http://127.0.0.1:8080/client/
```

Click **Start talking**, allow the mic, ask a question, then pause — Silero VAD +
the turn engine detect your endpoint, faster-whisper transcribes (GPU), Qwen2.5-3B
(Ollama) streams a reply clause-by-clause, and Piper speaks it back. The Silero VAD
ONNX (~2 MB) and the Piper voice download to `./models/` on first run; the LLM is
served by Ollama. Per-stage and **voice-to-voice** latency are logged per turn and
exposed at `/metrics`.

---

## Architecture

```
Caller audio ─▶ Transport ─▶ Session Manager ─▶ [ VAD ─▶ STT ─▶ Turn Engine ─▶
              (WS/WebRTC/        │               Dialogue Orchestrator ─▶ LLM ─▶ TTS ] ─▶ Transport
               Telephony)        │                       │
                                 ▼                        ▼
                          Conversation State        Tool Registry + Memory
                                 │                        │
                  Observability (traces/metrics/logs) + Reliability (failover/degradation)
```

Each pipeline stage is an independent async component communicating over **bounded queues** with explicit **backpressure** and **cancellation**. The **Conversation State Machine** is the single source of truth that barge-in reconciles against. Everything is configurable and swappable. See [docs/architecture.md](docs/architecture.md) and the [ADRs](docs/adr/).

## Repository layout

```
sutradhar/
  core/            # config, domain types, cancellation, bounded queues, latency, session, pipeline
  interfaces/      # Protocols: Transport, VAD, STT, TurnDetector, LLM, TTS, Memory, Tools, Tracer
  providers/
    stt/ tts/ llm/ vad/ turn/ memory/   # local-OSS impls + the dependency-free `stub.py`
  transport/       # websocket, webrtc, telephony-sim
  dialogue/        # state machine, orchestrator, tool registry, memory, prompts
  observability/   # tracing, metrics, logging
  reliability/     # failover, circuit breaker, retries, degradation, health
  tools/           # `doctor` environment check
eval/              # simulator, noise injection, judges, scenario suite (M4)
clients/web/       # browser mic client
mock_backend/      # FastAPI + SQLite demo CRM (lead qualification vertical)
deploy/            # docker compose, prometheus, grafana, Dockerfile
tests/             # unit, integration, load
docs/              # PRD, architecture, ADRs, latency report
```

## Demo vertical

**Outbound lead qualification** (the surface area the target employers build): a FastAPI + SQLite mock CRM with tools like `lookup_customer`, `book_slot`, `get_order_status`, `update_disposition`. Wired in M3.

## Roadmap

| Milestone | Deliverable | Status |
|---|---|---|
| **M0** | Scaffold, packaging, config, interfaces, observability/reliability skeleton, CI, docs | ✅ done |
| **M1** | Half-duplex streaming loop (mic→VAD→STT→LLM→TTS→speaker) over browser WS + latency | ✅ built · ⏳ baseline on GPU |
| **M2** | Turn-taking + barge-in (semantic endpointing, cancellation, state reconciliation) | ⬜ |
| **M3** | Dialogue: state machine, memory, tool-calling, demo vertical + mock backend | ⬜ |
| **M4** | Evaluation: synthetic callers, ASR-noise, LLM-judge, CI regression gate | ⬜ |
| **M5** | Transport & reliability: telephony-sim, failover, load test | ⬜ |
| **M6** | Ops & polish: Grafana dashboards, Docker Compose, ADRs, latency report, demo | ⬜ |

Progress is tracked in [TODO.md](TODO.md) and [CHANGELOG.md](CHANGELOG.md).

## Development

```powershell
.\tasks.ps1 lint           # ruff
.\tasks.ps1 typecheck      # mypy (strict)
.\tasks.ps1 test           # pytest (unit; no models)
.\tasks.ps1 format         # ruff + black autoformat
.\tasks.ps1 precommit      # run all pre-commit hooks
```

CI (GitHub Actions) runs lint, format-check, strict mypy and the unit suite on Python 3.11 & 3.12 — no ML wheels required, so it stays fast and green.

## License

[MIT](LICENSE) · © 2026 Reeth Jain. 100% free/open-source in the default run path.
