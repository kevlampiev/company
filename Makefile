.DEFAULT_GOAL := help

.PHONY: help install init-env test test-cov lint fmt typecheck check up down logs ps

help:  ## list available targets
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install:  ## sync host venv (creates backend/.venv, installs runtime+dev deps)
	cd backend && uv sync

init-env:  ## write a fresh .env at repo root with random secrets
	cd backend && uv run python -m scripts.init_env

test:  ## run the pytest suite (requires Docker daemon for testcontainers)
	cd backend && uv run pytest tests/ -v

test-cov:  ## run tests with coverage report
	cd backend && uv run pytest tests/ --cov=app --cov-report=term-missing

lint:  ## ruff check
	cd backend && uv run ruff check .

fmt:  ## ruff format + ruff --fix
	cd backend && uv run ruff format . && uv run ruff check --fix .

typecheck:  ## mypy on the application package
	cd backend && uv run mypy app/

check: lint typecheck test-cov  ## the "before-push" target: lint + typecheck + tests-with-coverage-threshold

up:  ## docker compose up -d --build (full stack)
	docker compose up -d --build

down:  ## docker compose down (volumes preserved)
	docker compose down

logs:  ## tail logs from all containers
	docker compose logs -f

ps:  ## list compose containers
	docker compose ps
