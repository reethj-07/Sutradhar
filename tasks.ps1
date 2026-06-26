<#
  Sutradhar task runner for Windows PowerShell (mirror of the Makefile).
  Usage:  .\tasks.ps1 <target>
  Targets: setup install lint format typecheck test test-cov check run demo eval up down precommit clean help
#>
param(
    [Parameter(Position = 0)]
    [string]$Target = "help"
)

$ErrorActionPreference = "Stop"
$UV = "uv"
function Py { & $UV run @args }

switch ($Target.ToLower()) {
    "setup" {
        & $UV venv --python 3.12
        & $UV pip install -e ".[dev]"
        try { Py pre-commit install } catch { Write-Host "pre-commit hook install skipped" }
        Write-Host "Setup complete. Activate with: .\.venv\Scripts\Activate.ps1"
    }
    "install" { & $UV pip install -e ".[local,dev]" }
    "lint" { Py ruff check sutradhar eval mock_backend tests }
    "format" {
        Py ruff check --fix sutradhar eval mock_backend tests
        Py black sutradhar eval mock_backend tests
        Py ruff format sutradhar eval mock_backend tests
    }
    "typecheck" { Py mypy sutradhar }
    "test" { Py pytest -m "not slow and not gpu" }
    "test-cov" { Py pytest --cov --cov-report=term-missing -m "not slow and not gpu" }
    "check" {
        Py ruff check sutradhar eval mock_backend tests
        Py mypy sutradhar
        Py pytest -m "not slow and not gpu"
    }
    "run" { Py sutradhar serve }
    "demo" { Py sutradhar demo }
    "eval" { Py sutradhar eval run }
    "up" { docker compose -f deploy/docker-compose.yml up -d }
    "down" { docker compose -f deploy/docker-compose.yml down }
    "precommit" { Py pre-commit run --all-files }
    "clean" {
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue `
            .pytest_cache, .mypy_cache, .ruff_cache, htmlcov, .coverage, coverage.xml, dist, build
        Get-ChildItem -Recurse -Directory -Filter __pycache__ -ErrorAction SilentlyContinue |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }
    default {
        Write-Host "Sutradhar tasks:" -ForegroundColor Cyan
        @(
            "setup      Create .venv, install dev deps, install pre-commit",
            "install    Install full local run path (.[local,dev])",
            "lint       Ruff lint",
            "format     Black + ruff autoformat",
            "typecheck  mypy (strict) on the library",
            "test       Run unit tests",
            "test-cov   Run tests with coverage",
            "check      lint + typecheck + test (CI parity)",
            "run        Run the Sutradhar server",
            "demo       Run the one-command demo",
            "eval       Run the evaluation suite",
            "up/down    Docker stack up / down",
            "precommit  Run all pre-commit hooks",
            "clean      Remove caches/artifacts"
        ) | ForEach-Object { Write-Host "  $_" }
    }
}
