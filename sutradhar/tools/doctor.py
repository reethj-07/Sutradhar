"""`sutradhar doctor` — verify the local run path on the target hardware (PRD §7).

Checks Python version, optional ML deps, CUDA/GPU availability, the Ollama
server, and the configured model — printing a green/red table so the operator
knows what is ready. Read-only and dependency-light: every optional import is
guarded so `doctor` runs even on a bare base install.
"""

from __future__ import annotations

import importlib.util
import shutil
import sys
from collections.abc import Iterable

import httpx
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from sutradhar.core.config import get_settings


def _has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _check_cuda() -> tuple[bool, str]:
    if not _has_module("onnxruntime"):
        return False, "onnxruntime not installed (pip install -e .[vad])"
    try:
        import onnxruntime as ort

        providers: Iterable[str] = ort.get_available_providers()
        if "CUDAExecutionProvider" in providers:
            return True, "CUDAExecutionProvider available"
        return False, f"CPU only ({', '.join(providers)})"
    except Exception as exc:
        return False, str(exc)


def _check_ollama(base_url: str, model: str) -> tuple[bool, str]:
    try:
        resp = httpx.get(f"{base_url}/api/tags", timeout=2.0)
        resp.raise_for_status()
        tags = [m.get("name", "") for m in resp.json().get("models", [])]
        if any(model.split(":")[0] in t for t in tags):
            return True, f"server up; model '{model}' present"
        return False, f"server up; model '{model}' NOT pulled (ollama pull {model})"
    except Exception as exc:
        return False, f"unreachable at {base_url} ({exc})"


def run_doctor(console: Console | None = None) -> bool:
    console = console or Console()
    s = get_settings()
    rows: list[tuple[str, bool, str]] = []

    py_ok = sys.version_info >= (3, 11)
    rows.append(("python>=3.11", py_ok, sys.version.split()[0]))

    for label, mod, extra in [
        ("faster-whisper (STT)", "faster_whisper", "stt"),
        ("onnxruntime (VAD/TTS)", "onnxruntime", "vad"),
        ("piper-tts (TTS)", "piper", "tts"),
        ("ollama client (LLM)", "ollama", "llm"),
        ("sqlite-vec (memory)", "sqlite_vec", "memory"),
    ]:
        present = _has_module(mod)
        rows.append((label, present, "installed" if present else f"pip install -e .[{extra}]"))

    cuda_ok, cuda_msg = _check_cuda()
    rows.append(("CUDA / GPU", cuda_ok, cuda_msg))

    rows.append(("ffmpeg on PATH", shutil.which("ffmpeg") is not None, "for audio decode"))

    ollama_ok, ollama_msg = _check_ollama(s.llm.base_url, s.llm.model)
    rows.append(("Ollama server + model", ollama_ok, ollama_msg))

    table = Table(title="Sutradhar environment check", show_header=True)
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")
    for label, ok, detail in rows:
        # `escape` so detail text like ".[stt]" isn't swallowed as Rich markup.
        status = "[green]OK[/green]" if ok else "[red]MISSING[/red]"
        table.add_row(label, status, escape(detail))
    console.print(table)

    # Only the base run path (python) is strictly required for M0.
    return py_ok
