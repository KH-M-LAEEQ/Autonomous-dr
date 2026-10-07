# One entry point for every routine command. If you find yourself typing a long
# command twice, it belongs in here.
.DEFAULT_GOAL := help
SHELL := /bin/bash

# Pull API_PORT (and anything else) out of .env so this file has no port
# number of its own to drift out of sync with core/config.py's Settings --
# `-include` so a clean clone without .env yet still runs `make setup`.
-include .env
export
API_PORT ?= 8001

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "};{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: ## First-time setup: venv, deps, .env, git hooks
	python3 -m venv .venv
	./.venv/bin/pip install --upgrade pip
	./.venv/bin/pip install -e ".[dev]"
	test -f .env || cp .env.example .env
	./.venv/bin/pre-commit install
	cd web && npm install
	@echo ""
	@echo "Done. Now:  make up && make migrate && make verify"

up: ## Start databases (Postgres + Redis + InfluxDB)
	docker compose up -d
	@echo "Waiting for health..."
	@sleep 5 && docker compose ps

up-all: ## Start databases + Celery worker + beat in containers
	docker compose --profile app up -d --build

down: ## Stop containers (data survives)
	docker compose down

nuke: ## Stop containers AND delete all volumes. Destroys your dataset.
	docker compose down -v

api: ## Run the FastAPI app natively with hot reload
	./.venv/bin/uvicorn api.main:app --reload --port $(API_PORT)

worker: ## Run a Celery worker natively
	./.venv/bin/celery -A core.tasks.app worker --loglevel=INFO

beat: ## Run Celery beat natively (the 10s collector poll)
	./.venv/bin/celery -A core.tasks.app beat --loglevel=INFO

web: ## Run the Vite dev server
	cd web && npm run dev

verify: ## Prove this clone is set up correctly. Run this before asking for help.
	./.venv/bin/python scripts/verify.py

hooks: ## Run the pre-commit hooks over the whole repo
	./.venv/bin/pre-commit run --all-files

openapi: ## Export the frozen API contract for the frontend (API must be running)
	curl -s localhost:$(API_PORT)/openapi.json | python3 -m json.tool > docs/api/openapi.json
	@echo "Wrote docs/api/openapi.json -- commit it with the router change."

migrate: ## Apply all database migrations
	./.venv/bin/alembic -c infra/alembic.ini upgrade head

migration: ## Create a new empty migration:  make migration m="add foo"
	./.venv/bin/alembic -c infra/alembic.ini revision -m "$(m)"

test: ## Run the Python test suite with coverage
	./.venv/bin/pytest --cov --cov-report=term-missing

lint: ## Lint + type-check (same commands CI runs)
	./.venv/bin/ruff check .
	./.venv/bin/ruff format --check .
	./.venv/bin/mypy

fmt: ## Auto-format everything
	./.venv/bin/ruff format .
	./.venv/bin/ruff check --fix .

web-build: ## Type-check and build the frontend (same as CI)
	cd web && npm run build

results: ## Regenerate every table and figure in the thesis (Week 31 target)
	@echo "Not implemented until Week 10 -- ml/harness/evaluate.py owns this."

smoke: ## Walk the product end to end; PASS/FAIL per check, stops at the first failure
	python3 scripts/smoke.py

.PHONY: help setup verify hooks openapi up up-all down nuke api worker beat web migrate \
	migration test lint fmt web-build results smoke
