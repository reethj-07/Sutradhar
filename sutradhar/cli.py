"""Sutradhar command-line interface (typer).

sutradhar version          show version + resolved provider config
sutradhar serve            run the FastAPI server (health/metrics; M1: /ws)
sutradhar demo             one-command voice demo (M1+)
sutradhar eval run         run the evaluation scenario suite (M4+)
sutradhar doctor           check the local environment (GPU, Ollama, models)
"""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from sutradhar import __version__
from sutradhar.core.config import get_settings

app = typer.Typer(add_completion=False, help="Sutradhar — real-time Voice AI agent platform.")
eval_app = typer.Typer(help="Evaluation suite (M4+).")
app.add_typer(eval_app, name="eval")
console = Console()


@app.command()
def version() -> None:
    """Print version and the resolved provider configuration."""
    s = get_settings()
    table = Table(title=f"Sutradhar v{__version__}", show_header=True)
    table.add_column("Component")
    table.add_column("Provider")
    table.add_column("Detail")
    table.add_row("transport", s.transport.default, f"{s.audio.sample_rate} Hz")
    table.add_row("vad", s.vad.provider, f"thr={s.vad.threshold}")
    table.add_row("stt", s.stt.provider, f"{s.stt.model_size}/{s.stt.device}")
    table.add_row("turn", s.turn.provider, f"silence={s.turn.silence_ms}ms")
    table.add_row("llm", s.llm.provider, s.llm.model)
    table.add_row("tts", s.tts.provider, s.tts.voice)
    table.add_row("memory", s.memory.provider, s.memory.db_path)
    console.print(table)


@app.command()
def serve(
    host: str = typer.Option("", help="Bind host (default from config)."),
    port: int = typer.Option(0, help="Bind port (default from config)."),
) -> None:
    """Run the Sutradhar FastAPI server."""
    import uvicorn

    s = get_settings()
    uvicorn.run(
        "sutradhar.app:create_app",
        factory=True,
        host=host or s.host,
        port=port or s.port,
        log_level=s.log_level.lower(),
        # Disable WebSocket keepalive pings: a CPU turn or a long agent reply can
        # exceed the default 20s window and would otherwise drop the call.
        ws_ping_interval=None,
        ws_ping_timeout=None,
    )


@app.command()
def demo(
    real: bool = typer.Option(
        False, "--real/--stub", help="Use real providers (needs GPU/Ollama) vs stubs."
    ),
) -> None:
    """Run a one-command demo of the streaming pipeline.

    `--stub` (default) drives the real pipeline with dependency-free stubs over a
    loopback transport — no mic/GPU/Ollama needed. `--real` runs the browser
    voice path; launch `sutradhar serve` and open the web client instead.
    """
    if real:
        console.print(
            "[yellow]The real voice demo runs over the browser WebSocket path.[/yellow]\n"
            "Start the server with [bold]sutradhar serve[/bold] and open "
            "[bold]clients/web/index.html[/bold]."
        )
        raise typer.Exit(code=0)

    import asyncio

    from sutradhar.demo import run_stub_demo

    asyncio.run(run_stub_demo(console))
    raise typer.Exit(code=0)


@app.command()
def doctor() -> None:
    """Check the local environment for the full run path."""
    from sutradhar.tools.doctor import run_doctor

    ok = run_doctor(console)
    raise typer.Exit(code=0 if ok else 1)


@eval_app.command("run")
def eval_run() -> None:
    """Run the evaluation scenario suite (implemented in M4)."""
    console.print("[yellow]The evaluation suite is implemented in M4.[/yellow]")
    raise typer.Exit(code=0)


if __name__ == "__main__":  # pragma: no cover
    app()
