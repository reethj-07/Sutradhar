# ADR-0002: Model placement on a 4 GB GPU

- **Status:** Accepted
- **Date:** 2026-06-26

## Context

The target machine is a Windows 11 laptop with an NVIDIA GTX 1650 (**4 GB
VRAM**) and 16 GB RAM. The 4 GB budget is the dominant constraint (PRD §7, §20):
STT and a 7B LLM cannot both live on the GPU, and naive placement either OOMs or
serializes badly.

## Decision

Deliberate, measured placement:

- **STT on GPU.** faster-whisper `small` at `int8_float16` (~0.5–1 GB VRAM) is
  the latency-critical, GPU-friendly stage. It stays on CUDA.
- **LLM on CPU + partial GPU offload.** Qwen2.5-3B-Instruct `Q4_K_M` via Ollama.
  A 3B Q4 model streams tokens fast enough on CPU with 16 GB RAM, supports
  tool-calling, and leaves the GPU for STT. Partial offload is opportunistic.
- **TTS on CPU.** Piper (ONNX) has very low first-audio latency on CPU and needs
  no VRAM.
- **VAD / turn detection on CPU.** Silero + a lightweight semantic classifier.
- **Colab is for experimentation only** — never in the local run path (NG, §20).

## Consequences

- The voice-to-voice P50 target is an honest **≈ 0.8–1.2 s** (CPU-LLM bound),
  not a fantasy sub-300 ms number.
- LLM first-token latency is the biggest lever; we mitigate with short prompts,
  KV-cache warmth, token streaming and first-clause TTS (PRD §8, §20).
- Everything sits behind interfaces, so a bigger GPU or a cloud LLM is a config
  swap, not a rewrite.
