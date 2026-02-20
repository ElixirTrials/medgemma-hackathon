<p align="center">
  <img src="docs/img/elixirtrials-logo.png" alt="ElixirTrials logo" width="280" />
</p>

<h1 align="center">ElixirTrials</h1>

<p align="center">
  AI-powered extraction and structuring of clinical trial eligibility criteria from protocol PDFs.
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#development">Development</a> •
  <a href="#documentation">Documentation</a>
</p>

---

## What It Does

ElixirTrials takes a clinical trial protocol PDF and turns it into structured, coded eligibility criteria ready for cohort identification. The system extracts inclusion and exclusion criteria, grounds medical entities to standard terminologies, builds expression trees, and presents outputs for human review.

## Key Capabilities

- **Gemini-powered extraction**: Reads protocol PDFs and extracts inclusion/exclusion criteria with confidence signals.
- **Multi-terminology grounding**: Links entities to SNOMED CT, LOINC, RxNorm, and ICD-10 through UMLS and OMOP CDM.
- **Expression tree structuring**: Decomposes free-text criteria into atomic conditions with AND/OR/NOT logic.
- **Ordinal scale resolution**: Detects scales (for example, NYHA and ECOG) and maps values to OMOP unit concepts.
- **Human-in-the-loop review**: Enables clinician review, approval, and correction in a split-pane UI.
- **Standards-ready exports**: Produces OHDSI CIRCE JSON, FHIR R4 Group, and OMOP CDM evaluation SQL.

## Architecture

```text
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

The processing pipeline runs as a 7-node LangGraph `StateGraph`:

`ingest -> extract -> parse -> ground -> persist -> structure -> ordinal_resolve`

Each node is checkpointed to PostgreSQL so failed runs can resume from the last successful step.

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Docker and Docker Compose
- [Google AI Studio API key](https://aistudio.google.com/apikey) for Gemini
- [UMLS API key](https://uts.nlm.nih.gov/uts/signup-login) for terminology grounding

### Setup

```bash
# 1) Clone
git clone https://github.com/noahdolevelixir/medgemma-hackathon.git
cd medgemma-hackathon

# 2) Install dependencies
uv sync
cd apps/hitl-ui && npm install && cd ../..

# 3) Configure environment
cp .env.example .env
# Set GOOGLE_API_KEY and UMLS_API_KEY at minimum

# 4) Start local stack (DB + MLflow + API + UI)
make run-dev
```

- UI: [http://localhost:3000](http://localhost:3000)
- API: [http://localhost:8000](http://localhost:8000)

### Verify Connectivity

```bash
make verify-gemini
```

## Project Structure

```text
medgemma-hackathon/
  services/
    api-service/                   # FastAPI upload, review, export endpoints
    protocol-processor-service/    # LangGraph extraction/grounding/structuring pipeline
  libs/
    shared/                        # SQLModel domain models and shared utilities
    inference/                     # Inference and model helpers
    data-pipeline/                 # Data loading and transformation
    evaluation/                    # Quality evaluation framework
    events-py/                     # Transactional outbox/event system
    model-training/                # Fine-tuning utilities
  apps/
    hitl-ui/                       # React + Vite review interface
  infra/                           # Docker Compose and deployment config
  docs/                            # MkDocs site and engineering docs
```

## Development

### Common Commands

| Command | Purpose |
|---------|---------|
| `make run-dev` | Start DB + MLflow + API + UI |
| `make run-api` | Start API service only |
| `make run-ui` | Start UI only |
| `make check` | Run lint, type-checking, and tests |
| `make check-fix` | Run checks with available auto-fixes |
| `make lint-fix` | Auto-fix lint issues (`ruff` + `biome`) |
| `make typecheck` | Run `mypy` and `tsc` |
| `make test` | Run `pytest` and `vitest` |
| `make docs-build` | Build docs site |
| `make docs-serve` | Serve docs locally |
| `make db-migrate` | Apply database migrations |
| `make db-revision msg="..."` | Create an Alembic migration |

### Authentication Backends

ElixirTrials supports two Gemini backends:

- **Gemini Developer API** (default): set `GOOGLE_API_KEY` in `.env`
- **Vertex AI** (for MedGemma): configure GCP project, ADC, and `VERTEX_ENDPOINT_ID`

Google OAuth for UI login is available but optional in local development. See `docs/development/gemini-vertex-auth.md`.

### Run With Docker

```bash
docker compose -f infra/docker-compose.yml up
```

## Documentation

Build and serve the docs site locally:

```bash
make docs-build && make docs-serve
```

The docs include architecture diagrams, data model references, user journeys, a code tour, and API documentation.

## Tech Stack

| Layer | Technology |
|-------|------------|
| LLM | Gemini 2.5 Flash (Google AI / Vertex AI) |
| Pipeline | LangGraph with PostgreSQL checkpointing |
| API | FastAPI + SQLModel + Alembic |
| Database | PostgreSQL |
| Frontend | React 18 + Vite + Tailwind CSS + Radix UI |
| Terminology | UMLS API + OMOP CDM |
| Tracking | MLflow |
| Docs | MkDocs |

## License

Built for the [Google MedGemma Hackathon](https://cloud.google.com/blog/topics/healthcare-life-sciences/medgemma-hackathon).
