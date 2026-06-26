# Sutradhar task runner (GNU make). On Windows, either install make
# (`winget install GnuWin32.Make` or via Git for Windows), or use the
# PowerShell-native equivalent: `.\tasks.ps1 <target>`. Both wrap `uv`.

UV ?= uv
PY := $(UV) run

.DEFAULT_GOAL := help

.PHONY: help setup install lint format typecheck test test-cov check run demo \
        eval up down logs clean precommit

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: ## Create venv (.venv), install package + dev extras, install pre-commit
	$(UV) venv --python 3.12
	$(UV) pip install -e ".[dev]"
	-$(PY) pre-commit install
	@echo "Setup complete. Activate with: .\\.venv\\Scripts\\activate"

install: ## Install the full local run path extras (models pulled on first use)
	$(UV) pip install -e ".[local,dev]"

lint: ## Ruff lint
	$(PY) ruff check sutradhar eval mock_backend tests

format: ## Black + ruff autoformat
	$(PY) ruff check --fix sutradhar eval mock_backend tests
	$(PY) black sutradhar eval mock_backend tests
	$(PY) ruff format sutradhar eval mock_backend tests

typecheck: ## mypy (strict) on the library
	$(PY) mypy sutradhar

test: ## Run unit tests
	$(PY) pytest -m "not slow and not gpu"

test-cov: ## Run tests with coverage
	$(PY) pytest --cov --cov-report=term-missing -m "not slow and not gpu"

check: lint typecheck test ## Lint + typecheck + test (what CI runs)

run: ## Run the Sutradhar server (browser WS client)
	$(PY) sutradhar serve

demo: ## Run the one-command demo (M1+: spoken Q -> spoken A)
	$(PY) sutradhar demo

eval: ## Run the evaluation scenario suite (M4+)
	$(PY) sutradhar eval run

up: ## Bring up the full Docker stack (M6: app, ollama, jaeger, prom, grafana)
	docker compose -f deploy/docker-compose.yml up -d

down: ## Tear down the Docker stack
	docker compose -f deploy/docker-compose.yml down

logs: ## Tail the Docker stack logs
	docker compose -f deploy/docker-compose.yml logs -f

precommit: ## Run all pre-commit hooks on all files
	$(PY) pre-commit run --all-files

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml dist build
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
