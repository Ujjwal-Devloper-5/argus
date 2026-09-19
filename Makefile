.PHONY: install install-gpu dev run test lint format docker-build clean help

PYTHON := python
VENV := .venv
PIP := $(VENV)/bin/pip

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install CPU dependencies
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -e ".[dev]"
	cp -n .env.example .env || true
	cp -n config/config.example.yaml config/config.yaml || true
	@echo "✅ Argus installed. Edit .env and config/config.yaml to configure."

install-gpu: ## Install GPU (CUDA) dependencies
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -e ".[gpu,dev]"
	@echo "✅ Argus GPU installed."

dev: ## Run in development mode with hot reload
	$(VENV)/bin/streamlit run argus/dashboard/app.py --server.runOnSave true &
	$(VENV)/bin/python -m argus.core.pipeline

run: ## Run Argus
	$(VENV)/bin/python -m argus

enroll: ## Enroll a new known face (usage: make enroll NAME="John")
	$(VENV)/bin/python scripts/enroll_face.py --name "$(NAME)"

test: ## Run test suite
	$(VENV)/bin/pytest tests/ -v --cov=argus --cov-report=term-missing

lint: ## Run linter
	$(VENV)/bin/ruff check argus/ tests/
	$(VENV)/bin/mypy argus/

format: ## Format code
	$(VENV)/bin/ruff format argus/ tests/

docker-build: ## Build CPU Docker image
	docker build -t argus:latest -f docker/Dockerfile .

docker-build-gpu: ## Build GPU Docker image
	docker build -t argus:gpu -f docker/Dockerfile.gpu .

docker-up: ## Start with Docker Compose (CPU)
	docker compose up -d

docker-up-gpu: ## Start with Docker Compose (GPU)
	docker compose -f docker-compose.gpu.yml up -d

docker-logs: ## Show Docker logs
	docker compose logs -f argus

docker-down: ## Stop Docker Compose
	docker compose down

clean: ## Clean build artifacts
	rm -rf .venv __pycache__ .pytest_cache .ruff_cache dist build *.egg-info
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

test-stream: ## Test camera connection (usage: make test-stream URL="rtsp://...")
	$(VENV)/bin/python scripts/test_stream.py --url "$(URL)"
