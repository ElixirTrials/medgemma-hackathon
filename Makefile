# Documentation Makefile for monorepo
SHELL := /bin/bash

.PHONY: help docs-build docs-serve clean create-component create-service docs-openapi kill-processes db-migrate db-revision check check-fix check-with-docs lint lint-fix typecheck test run-dev run-infra run-api run-ui

run-dev:
	@echo "Starting infrastructure + API + UI..."
	@echo "1. Starting DB and MLflow..."
	docker compose -f infra/docker-compose.yml up -d db mlflow
	@echo "2. Waiting for Postgres..."
	@until docker compose -f infra/docker-compose.yml exec db pg_isready -U postgres 2>/dev/null; do sleep 1; done
	@echo "3. Starting API (port 8000) and UI (port 5173)..."
	@set -a && source .env && set +a && \
	trap 'kill 0' EXIT; \
	uv run uvicorn api_service.main:app --reload --host 0.0.0.0 --port 8000 --app-dir services/api-service/src & \
	cd apps/hitl-ui && npm run dev & \
	wait

run-infra:
	@echo "Starting infrastructure services (DB, MLflow)..."
	docker compose -f infra/docker-compose.yml up -d db mlflow

run-api:
	@echo "Starting API service on port 8000..."
	@set -a && source .env && set +a && \
	uv run uvicorn api_service.main:app --reload --host 0.0.0.0 --port 8000 --app-dir services/api-service/src

run-ui:
	@echo "Starting UI dev server..."
	cd apps/hitl-ui && npm run dev

create-component:
	@read -p "Enter component name: " COMPONENT_NAME; \
	./scripts/create-service.sh --lang py "$$COMPONENT_NAME"

create-service:
	@read -p "Enter service name: " NAME; read -p "Language (py|ts) [py]: " LANG; LANG=$${LANG:-py}; \
	./scripts/create-service.sh --lang "$$LANG" "$$NAME"

docs-components-gen:
	@echo "Generating components overview page..."
	uv run python scripts/generate_components_overview.py

docs-nav-update:
	@echo "Updating root navigation..."
	uv run python scripts/update_root_navigation.py

docs-build: docs-nav-update docs-components-gen docs-openapi
	@echo "Building documentation site..."
	uv run python scripts/build_docs.py build -f mkdocs.yml

docs-serve:
	@echo "Serving built documentation site..."
	@if [ ! -d "site" ]; then \
		echo "No built site found. Run 'make docs-build' first."; \
		exit 1; \
	fi
	@echo "Serving from: $(PWD)/site"
	@echo "Available at: http://localhost:8000"
	@echo "Press Ctrl+C to stop"
	@cd site && uv run python -m http.server 8000

docs-openapi:
	@echo "Exporting OpenAPI spec..."
	uv run --project services/api-service python services/api-service/scripts/export_openapi.py

kill-processes:
	@echo "Killing running processes..."
	@./scripts/kill-running-processes.sh

db-revision:
	@echo "Creating new Alembic revision..."
	uv run alembic revision --autogenerate -m "$(msg)"

db-migrate:
	@echo "Applying database migrations..."
	uv run alembic upgrade head

clean:
	@echo "Cleaning build artifacts..."
	rm -rf site/
	rm -rf .cache/
	rm -rf docs/.uv_cache/

# Code Quality Commands
check:
	@echo "Running all checks..."
	@./scripts/check-all.sh

check-fix:
	@echo "Running all checks with auto-fix..."
	@./scripts/check-all.sh --fix

check-with-docs:
	@echo "Running all checks including documentation..."
	@./scripts/check-all.sh --with-docs

lint:
	@echo "Running linters..."
	uv run ruff check .
	@if [ -d "apps/hitl-ui/node_modules" ]; then \
		cd apps/hitl-ui && npm run lint; \
	fi

lint-fix:
	@echo "Running linters with auto-fix..."
	uv run ruff check . --fix
	uv run ruff format .
	@if [ -d "apps/hitl-ui/node_modules" ]; then \
		cd apps/hitl-ui && npm run lint:fix; \
	fi

typecheck:
	@echo "Running type checkers..."
	uv run mypy libs/shared/src services/api-service/src libs/inference/src services/extraction-service/src services/grounding-service/src libs/data-pipeline/src libs/evaluation/src libs/events-py/src libs/model-training/src
	@if [ -d "apps/hitl-ui/node_modules" ]; then \
		cd apps/hitl-ui && npx tsc --noEmit; \
	fi

test:
	@echo "Running tests..."
	uv run pytest services/api-service/tests libs/events-py/tests -q
	@if [ -d "apps/hitl-ui/node_modules" ]; then \
		cd apps/hitl-ui && npm test -- --run; \
	fi

help:
	@echo "ElixirTrials  - Makefile Commands"
	@echo ""
	@echo "Development:"
	@echo "  make run-dev   - Start infra + API + UI (all-in-one)"
	@echo "  make run-infra - Start DB, MLflow only"
	@echo "  make run-api   - Start API service (port 8000)"
	@echo "  make run-ui    - Start UI dev server (port 5173)"
	@echo ""
	@echo "Code Quality:"
	@echo "  make check           - Run linters, type checkers, and tests"
	@echo "  make check-with-docs - Run all checks including doc build"
	@echo "  make check-fix       - Run all checks with auto-fix"
	@echo "  make lint       - Run ruff and Biome (hitl-ui)"
	@echo "  make lint-fix   - Run linters with auto-fix"
	@echo "  make typecheck  - Run mypy and tsc"
	@echo "  make test       - Run pytest and vitest"
	@echo ""
	@echo "Documentation:"
	@echo "  make docs-build - Build documentation site"
	@echo "  make docs-serve - Serve documentation locally"
	@echo ""
	@echo "Database:"
	@echo "  make db-migrate        - Apply database migrations"
	@echo "  make db-revision msg=X - Create new migration"
