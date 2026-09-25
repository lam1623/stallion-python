# Stallion developer tasks. `make help` lists them.
PY ?= python3
VENV ?= .venv
BIN := $(VENV)/bin
NPM := npm --prefix frontend

.DEFAULT_GOAL := help
.PHONY: help install build run serve dev-api dev-ui test lint format typecheck check wheel docker clean

help: ## Show this help
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*## "} {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

$(BIN)/python:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip

install: $(BIN)/python ## Install backend (editable, dev + desktop extras) and frontend deps
	$(BIN)/pip install -e ".[dev,desktop]"
	$(NPM) ci

build: ## Build the web UI into stallion/web/dist
	$(NPM) run build

run: build ## Launch the desktop app
	$(BIN)/stallion

serve: build ## Run the web server on http://localhost:8000
	$(BIN)/stallion serve --open

dev-api: ## Backend with a fixed dev token (pair with `make dev-ui`)
	STALLION_TOKEN=dev $(BIN)/stallion serve --port 8000 --log-level debug

dev-ui: ## Vite dev server with hot reload on http://localhost:5173/auth?token=dev
	$(NPM) run dev

test: ## Run the Python test-suite (uses real ffmpeg when installed)
	$(BIN)/pytest -q

lint: ## Ruff lint + format check
	$(BIN)/ruff check stallion tests
	$(BIN)/ruff format --check stallion tests

format: ## Auto-format Python code
	$(BIN)/ruff format stallion tests
	$(BIN)/ruff check --fix stallion tests

typecheck: ## mypy + TypeScript
	$(BIN)/mypy
	$(NPM) run typecheck

check: lint typecheck test ## Everything CI runs

wheel: build ## Build a wheel with the UI embedded into dist/
	$(BIN)/pip wheel --no-deps -w dist .

docker: ## Build the Docker image
	docker build -t stallion:latest .

clean: ## Remove build artifacts and caches
	rm -rf dist build stallion/web/dist .pytest_cache .mypy_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
