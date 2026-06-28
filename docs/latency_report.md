# Latency Report

**Metric of record:** voice-to-voice latency = end-of-user-speech (endpoint
detected) → first agent audio byte emitted (PRD §8).

> This is a template. Numbers are filled in from M1 onward, measured on the
> target hardware (Windows 11 · GTX 1650 4 GB · 16 GB RAM) and captured
> automatically by `LatencyTracker` → Prometheus → Grafana.

## Targets (PRD §8)

| Stage | P50 target | Notes |
|---|---|---|
| VAD endpoint decision | 50–100 ms | Frame-level, runs continuously |
| STT finalization after endpoint | 150–250 ms | Most already streamed as partials |
| LLM first token | 300–600 ms | CPU 3B; short prompt; KV cache warm; streaming |
| TTS first audio chunk | 100–300 ms | Piper; first-clause synthesis |
| Transport / buffering | 30–80 ms | Small jitter buffer |
| **Total voice-to-voice (P50)** | **≈ 0.8–1.2 s** | Honest target for CPU-LLM on 4 GB |

## Measured (to be filled per milestone)

| Build | Scenario | V2V P50 | V2V P95 | STT | LLM 1st tok | TTS 1st chunk | Notes |
|---|---|---|---|---|---|---|---|
| M1 baseline | — | _tbd_ | _tbd_ | _tbd_ | _tbd_ | _tbd_ | first end-to-end |

## Method

- Marks captured by [`core/latency.py`](../sutradhar/core/latency.py); endpoint and
  first-audio timestamps bound the voice-to-voice clock.
- P50/P95 read from the `sutradhar_voice_to_voice_seconds` Prometheus histogram.
- Eval scenarios (M4) replay fixed audio so numbers are comparable across builds;
  CI fails on regressions beyond threshold (PRD §11, K1).

## Capturing the M1 baseline (on the GTX 1650)

```powershell
.\tasks.ps1 install
ollama pull qwen2.5:3b-instruct-q4_K_M
sutradhar doctor          # confirm CUDA + Ollama + model + Piper voice
sutradhar serve           # then open http://127.0.0.1:8080/client/
```

Have a short spoken exchange (5-10 turns). Each turn logs a `turn_latency` line
with per-stage and `voice_to_voice` numbers (ms); the same values populate the
Prometheus histograms at `/metrics`. Read P50/P95 from Prometheus (or compute
from the logged values) and fill the **Measured** row above. Warm the model with
one throwaway turn first so KV-cache/JIT costs don't skew the first measurement.
