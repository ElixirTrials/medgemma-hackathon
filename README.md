# ElixirTrials

AI-powered extraction and structuring of clinical trial eligibility criteria from protocol PDFs.

ElixirTrials takes a clinical trial protocol PDF and produces structured, coded eligibility criteria ready for cohort identification. Upload a protocol, and the system extracts inclusion/exclusion criteria, grounds medical entities to standard terminologies, builds expression trees, and presents everything for human review.

## Key Capabilities

- **Gemini-powered extraction** -- LLM reads the PDF and extracts inclusion/exclusion criteria with confidence scores
- **Multi-terminology grounding** -- entities are linked to SNOMED CT, LOINC, RxNorm, ICD-10 via UMLS and OMOP CDM
- **Expression tree structuring** -- criteria are decomposed into atomic conditions with AND/OR/NOT logic
- **Ordinal scale resolution** -- detects ordinal scales (e.g. NYHA class, ECOG) and maps to OMOP unit concepts
- **Human-in-the-loop review** -- clinicians review, approve, or modify AI-generated criteria in a split-pane UI
- **Standard exports** -- output in OHDSI CIRCE JSON, FHIR R4 Group, and OMOP CDM evaluation SQL

## Architecture

```
hitl-ui (React/Vite)
    |
    | HTTP
    v
api-service (FastAPI) ----> PostgreSQL
    |
    | outbox event
    v
protocol-processor-service (LangGraph)
    |
    |---> Gemini 2.5 Flash (extraction, structuring, ordinal resolution)
    |---> UMLS API + OMOP CDM (terminology grounding)
    |---> MLflow (experiment tracking)
```

The processing pipeline is a 7-node LangGraph StateGraph:

**ingest** -> **extract** -> **parse** -> **ground** -> **persist** -> **structure** -> **ordinal_resolve**

Each node is checkpointed to PostgreSQL, so failed runs can be retried from the last successful step.

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Docker & Docker Compose
- A [Google AI Studio API key](https://aistudio.google.com/apikey) for Gemini
- A [UMLS API key](https://uts.nlm.nih.gov/uts/signup-login) for terminology grounding

### Setup

```bash
# 1. Clone the repo
git clone https://github.com/noahdolevelixir/medgemma-hackathon.git
cd medgemma-hackathon

# 2. Install dependencies
uv sync
cd apps/hitl-ui && npm install && cd ../..

# 3. Configure environment
cp .env.example .env
# Edit .env -- set GOOGLE_API_KEY and UMLS_API_KEY at minimum

# 4. Start everything (DB + MLflow + API + UI)
make run-dev
```

The UI opens at [http://localhost:3000](http://localhost:3000) and the API at [http://localhost:8000](http://localhost:8000).

### Verify API Access

```bash
make verify-gemini    # Test Gemini API connectivity
```

## Project Structure

```
medgemma-hackathon/
  services/
    api-service/             # FastAPI -- upload, review, export endpoints
    protocol-processor-service/  # LangGraph pipeline -- extraction through structuring
  libs/
    shared/                  # SQLModel domain models, shared utilities
    inference/               # Model loading and inference helpers
    data-pipeline/           # Data loading and transformation
    evaluation/              # Quality evaluation framework
    events-py/               # Event system (transactional outbox)
    model-training/          # Fine-tuning utilities
  apps/
    hitl-ui/                 # React + Vite -- review dashboard
  infra/                     # Docker Compose, deployment config
  docs/                      # MkDocs documentation site
```

## Development

### Common Commands

| Command | Description |
|---------|-------------|
| `make run-dev` | Start DB + MLflow + API + UI (all-in-one) |
| `make run-api` | Start API service only |
| `make run-ui` | Start UI dev server only |
| `make check` | Run linters, type checkers, and tests |
| `make check-fix` | Run all checks with auto-fix |
| `make lint-fix` | Auto-fix lint issues (ruff + Biome) |
| `make typecheck` | Run mypy and tsc |
| `make test` | Run pytest and vitest |
| `make docs-build` | Build documentation site |
| `make docs-serve` | Serve docs at localhost:8000 |
| `make db-migrate` | Apply database migrations |
| `make db-revision msg="..."` | Create a new Alembic migration |

### Authentication

ElixirTrials supports two Gemini backends:

- **Gemini Developer API** (default) -- set `GOOGLE_API_KEY` in `.env`
- **Vertex AI** -- for MedGemma; requires GCP project, ADC, and `VERTEX_ENDPOINT_ID`

Google OAuth is available for UI login but optional for local development. See the [auth guide](docs/development/gemini-vertex-auth.md) for details.

### Running with Docker

```bash
docker compose -f infra/docker-compose.yml up
```

## Documentation

Full documentation is available as a local MkDocs site:

```bash
make docs-build && make docs-serve
```

This includes architecture diagrams, data model references, user journey walkthroughs, a code tour, and API documentation.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| LLM | Gemini 2.5 Flash (Google AI / Vertex AI) |
| Pipeline | LangGraph with PostgreSQL checkpointing |
| API | FastAPI + SQLModel + Alembic |
| Database | PostgreSQL |
| Frontend | React 18 + Vite + Tailwind CSS + Radix UI |
| Terminology | UMLS API, OMOP CDM |
| Tracking | MLflow |
| Docs | MkDocs |

## License

This project was built for the [Google MedGemma Hackathon](https://cloud.google.com/blog/topics/healthcare-life-sciences/medgemma-hackathon).
