# Documentation Makefile for monorepo
SHELL := /bin/bash

.PHONY: help docs-build docs-serve clean create-component create-service docs-openapi kill-processes db-migrate db-revision check check-fix check-with-docs lint lint-fix typecheck test run-dev run-infra run-mlflow run-api run-ui setup-adc verify-gemini quality-eval quality-eval-fresh

run-dev:
	@docker info >/dev/null 2>&1 || { echo "Docker is not running. Start Docker Desktop (or the Docker daemon), then run: make run-dev"; exit 1; }
	@echo "Starting infrastructure + API + UI..."
	@echo "1. Activating gcloud profile..."
	@GCLOUD_PROFILE=$$(grep '^GCLOUD_PROFILE=' .env | cut -d= -f2); \
	if [ -n "$$GCLOUD_PROFILE" ]; then \
		gcloud config configurations activate $$GCLOUD_PROFILE; \
	else \
		echo "GCLOUD_PROFILE not set in .env, skipping"; \
	fi
	@echo "2. Starting DB..."
	docker compose -f infra/docker-compose.yml up -d db
	@echo "3. Waiting for Postgres..."
	@until docker compose -f infra/docker-compose.yml exec db pg_isready -U postgres 2>/dev/null; do sleep 1; done
	@echo "4. Starting local MLflow server..."
	@mkdir -p .mlflow
	@echo "5. Finding available ports and starting API + UI + MLflow..."
	@if [ ! -d "apps/hitl-ui/node_modules" ]; then \
		echo "  Installing hitl-ui dependencies (npm install)..."; \
		cd apps/hitl-ui && npm install && cd ../..; \
	fi
	@set -a && source .env && set +a && \
	API_PORT=8000; \
	while lsof -i :$$API_PORT >/dev/null 2>&1; do API_PORT=$$((API_PORT+1)); done; \
	echo "  API on port $$API_PORT (UI will use VITE_API_URL=http://localhost:$$API_PORT)"; \
	export VITE_API_URL="http://localhost:$$API_PORT"; \
	export LOCAL_UPLOAD_DIR="$${LOCAL_UPLOAD_DIR:-$$(pwd)/uploads}"; \
	trap 'kill 0' EXIT; \
	uv run mlflow server --host 0.0.0.0 --port 5001 --backend-store-uri sqlite:///.mlflow/mlflow.db --artifacts-destination .mlflow/artifacts & \
	uv run uvicorn api_service.main:app --reload --host 0.0.0.0 --port $$API_PORT --app-dir services/api-service/src & \
	cd apps/hitl-ui && npm run dev & \
	wait

run-infra:
	@echo "Starting infrastructure services (DB + local MLflow)..."
	@docker info >/dev/null 2>&1 || { echo "Docker is not running. Start Docker Desktop (or the Docker daemon), then run: make run-infra"; exit 1; }
	docker compose -f infra/docker-compose.yml up -d db
	@mkdir -p .mlflow
	@echo "Starting local MLflow server on port 5001 (foreground)..."
	@echo "  Use Ctrl+C to stop. DB will keep running in Docker."
	uv run mlflow server --host 0.0.0.0 --port 5001 --backend-store-uri sqlite:///.mlflow/mlflow.db --artifacts-destination .mlflow/artifacts

run-mlflow:
	@echo "Starting local MLflow server on port 5001..."
	@mkdir -p .mlflow
	uv run mlflow server --host 0.0.0.0 --port 5001 --backend-store-uri sqlite:///.mlflow/mlflow.db --artifacts-destination .mlflow/artifacts

run-api:
	@GCLOUD_PROFILE=$$(grep '^GCLOUD_PROFILE=' .env | cut -d= -f2); \
	if [ -n "$$GCLOUD_PROFILE" ]; then \
		echo "Activating gcloud profile $$GCLOUD_PROFILE..."; \
		gcloud config configurations activate $$GCLOUD_PROFILE; \
	fi; \
	API_PORT=8000; \
	while lsof -i :$$API_PORT >/dev/null 2>&1; do API_PORT=$$((API_PORT+1)); done; \
	echo "Starting API service on port $$API_PORT..."; \
	set -a && source .env && set +a && \
	export LOCAL_UPLOAD_DIR="$${LOCAL_UPLOAD_DIR:-$$(pwd)/uploads}"; \
	uv run uvicorn api_service.main:app --reload --host 0.0.0.0 --port $$API_PORT --app-dir services/api-service/src

run-ui:
	@echo "Starting UI dev server..."
	cd apps/hitl-ui && npm run dev

# Set Application Default Credentials quota project from .env (GCP_PROJECT_ID or GOOGLE_CLOUD_QUOTA_PROJECT).
# Run once after gcloud auth application-default login. Required for Vertex AI and GCS when using user ADC.
setup-adc:
	@chmod +x scripts/setup-gcloud-adc.sh 2>/dev/null || true
	@./scripts/setup-gcloud-adc.sh

# Verify Gemini API access (GOOGLE_API_KEY in .env). Uses same client as extraction service.
verify-gemini:
	uv run python scripts/verify_gemini_access.py

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

db-clear-protocols:
	@echo "Clearing all protocols, criteria, and related data from the database..."
	@set -a && . ./.env && set +a && uv run --project services/api-service python services/api-service/scripts/clear_protocols_and_criteria.py

mlflow-clear:
	@echo "Deleting all MLflow runs/traces..."
	@set -a && . ./.env && set +a && uv run --group dev python scripts/clear_mlflow_traces.py

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

# Quality Evaluation
quality-eval:  ## Run quality evaluation on sample PDFs (requires Docker Compose stack)
	uv run python scripts/quality_eval.py

quality-eval-fresh:  ## Run quality evaluation with fresh pipeline runs
	uv run python scripts/quality_eval.py --fresh

help:
	@echo "ElixirTrials  - Makefile Commands"
	@echo ""
	@echo "Development (local):"
	@echo "  make run-dev     - Start DB + local MLflow + API + UI (all-in-one)"
	@echo "  make run-infra   - Start DB + local MLflow (run API/UI separately)"
	@echo "  make run-mlflow  - Start local MLflow only (port 5001)"
	@echo "  make run-api     - Start API service (port 8000)"
	@echo "  make run-ui      - Start UI dev server (port 3000)"
	@echo ""
	@echo "Production (Docker):"
	@echo "  docker compose -f infra/docker-compose.yml up  - Full stack with Docker MLflow"
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
	@echo "  make db-migrate          - Apply database migrations"
	@echo "  make db-revision msg=X   - Create new migration"
	@echo "  make db-clear-protocols  - Remove all protocols, criteria, and related data"
	@echo ""
	@echo "MLflow:"
	@echo "  make mlflow-clear - Delete all MLflow runs/traces"
	@echo ""
	@echo "Quality Evaluation:"
	@echo "  make quality-eval       - Run quality evaluation on sample PDFs"
	@echo "  make quality-eval-fresh - Re-upload PDFs and run fresh evaluation"
