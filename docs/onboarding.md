# Onboarding

Get ElixirTrials running locally in under 10 minutes.

## Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.12+ | Backend services |
| uv | latest | Python package manager (replaces pip/venv) |
| Node.js | 18+ | Frontend UI |
| Docker | latest | PostgreSQL database |
| gcloud CLI | latest | GCP authentication (optional for local dev) |

## 1. Clone and Install

```bash
git clone https://github.com/noahdolevelixir/medgemma-hackathon.git
cd medgemma-hackathon
uv sync                    # Install all Python dependencies
cd apps/hitl-ui && npm install && cd ../..
```

## 2. Environment Configuration

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

| Variable | Required | Source |
|----------|----------|--------|
| `GOOGLE_API_KEY` | Yes | [Google AI Studio](https://aistudio.google.com/apikey) |
| `UMLS_API_KEY` | Yes | [UMLS Sign Up](https://uts.nlm.nih.gov/uts/signup-login) |
| `GEMINI_MODEL_NAME` | No | Defaults to `gemini-2.5-flash` |
| `MODEL_BACKEND` | No | `vertex` for Vertex AI, omit for Gemini Developer API |
| `GCP_PROJECT_ID` | If Vertex | Your GCP project ID |
| `GCP_REGION` | If Vertex | e.g., `europe-west4` |
| `VERTEX_ENDPOINT_ID` | If Vertex | MedGemma endpoint ID |
| `GOOGLE_CLIENT_ID` | No | OAuth login (dev works without) |
| `GOOGLE_CLIENT_SECRET` | No | OAuth login (dev works without) |
| `MLFLOW_TRACKING_URI` | No | Defaults to `http://localhost:5001` |

## 3. Start the Dev Stack

```bash
make run-dev
```

This starts:

- **PostgreSQL** on port 5432 (Docker)
- **MLflow** on port 5001 (local)
- **API service** on port 8000 (uvicorn with hot-reload)
- **UI** on port 3000 (Vite dev server)

Alternatively, start components individually:

```bash
make run-infra    # DB + MLflow only
make run-api      # API service only
make run-ui       # UI only
```

## 4. Verify

1. Open [http://localhost:3000](http://localhost:3000) — you should see the HITL UI
2. Check [http://localhost:8000/health](http://localhost:8000/health) — should return `{"status": "healthy"}`
3. Check [http://localhost:5001](http://localhost:5001) — MLflow dashboard

## 5. Upload a Protocol

1. Click **Upload Protocol** in the UI
2. Drop a clinical trial protocol PDF (max 50 MB)
3. The pipeline runs automatically: extract → parse → ground → structure
4. Review extracted criteria in the HITL review page

## Project Structure

```
medgemma-hackathon/
├── apps/hitl-ui/              # React + Vite frontend
├── services/
│   ├── api-service/           # FastAPI backend (REST + outbox)
│   └── protocol-processor-service/  # LangGraph pipeline
├── libs/
│   ├── shared/                # SQLModel data models
│   ├── events-py/             # Outbox processor + event contracts
│   ├── inference/             # Model inference utilities
│   ├── evaluation/            # Quality evaluation
│   ├── data-pipeline/         # Data loading utilities
│   └── model-training/        # Fine-tuning scripts
├── infra/                     # Docker Compose, OMOP vocab
├── scripts/                   # Dev tooling, migrations
├── docs/                      # This documentation
├── Makefile                   # All dev commands
└── mkdocs.yml                 # Docs site config
```

## Common Commands

```bash
make help          # Show all available commands
make check         # Run linters + type checkers + tests
make lint-fix      # Auto-fix lint issues
make test          # Run all tests
make docs-build    # Build documentation site
make docs-serve    # Serve docs at http://localhost:8000
```
