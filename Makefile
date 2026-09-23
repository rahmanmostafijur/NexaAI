# NexaAI Agent developer commands (Linux, macOS, WSL). Windows: use ./tasks.ps1 <target>.
.DEFAULT_GOAL := help
BACKEND := cd backend &&
FRONTEND := cd frontend &&

.PHONY: help up down logs dev dev-backend dev-frontend install migrate seed reseed test test-backend \
        test-frontend coverage lint format evaluate evaluate-full

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-16s %s\n", $$1, $$2}'

up: ## Build and start the full stack in Docker (http://localhost:3000)
	docker compose up --build -d

down: ## Stop the Docker stack
	docker compose down

logs: ## Follow backend logs
	docker compose logs -f backend

install: ## Install backend and frontend dependencies for local development
	$(BACKEND) uv sync
	$(FRONTEND) npm ci

dev: ## Run Postgres in Docker, backend and frontend locally with hot reload
	docker compose up -d postgres
	$(MAKE) migrate
	$(MAKE) -j2 dev-backend dev-frontend

dev-backend:
	$(BACKEND) uv run uvicorn app.main:app --reload --port 8000

dev-frontend:
	$(FRONTEND) npm run dev

migrate: ## Apply database migrations
	$(BACKEND) uv run alembic upgrade head

seed: ## Seed demo data and knowledge base (idempotent)
	$(BACKEND) uv run python -m scripts.seed

reseed: ## Wipe and regenerate demo data and knowledge base
	$(BACKEND) uv run python -m scripts.seed --reset

test: test-backend test-frontend ## Run all tests

test-backend: ## Backend unit + integration tests (needs Postgres for integration)
	$(BACKEND) uv run pytest

test-frontend: ## Frontend tests
	$(FRONTEND) npm test

coverage: ## Backend tests with coverage report
	$(BACKEND) uv run pytest --cov=app --cov-report=term-missing

lint: ## Lint backend (ruff) and frontend (eslint, tsc)
	$(BACKEND) uv run ruff check .
	$(BACKEND) uv run ruff format --check .
	$(FRONTEND) npm run lint
	$(FRONTEND) npm run typecheck

format: ## Format backend and frontend code
	$(BACKEND) uv run ruff check --fix .
	$(BACKEND) uv run ruff format .
	$(FRONTEND) npm run format

evaluate: ## Offline evaluation (no LLM): heuristic routing, retrieval, gold SQL
	$(BACKEND) uv run python evaluate_agent.py --mode offline
	$(BACKEND) uv run python evaluate_agent.py --mode offline --dataset holdout

evaluate-full: ## Full agent evaluation with the configured LLM
	$(BACKEND) uv run python evaluate_agent.py --mode full
