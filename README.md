<p align="center">
  <img src="docs/img/elixirtrials-logo.png" alt="ElixirTrials logo" width="280" />
</p>

<h1 align="center">ElixirTrials</h1>

<p align="center">
  AI-powered extraction and structuring of clinical trial eligibility criteria<br/>
  using <strong>MedGemma 4B-IT</strong> and <strong>Gemini 2.5 Flash</strong>
</p>

<p align="center">
  <a href="https://noahdolevelixir.github.io/medgemma-hackathon/">Documentation</a> &bull;
  <a href="#medgemma--hai-def-integration">MedGemma Integration</a> &bull;
  <a href="#agentic-workflow">Agentic Workflow</a> &bull;
  <a href="#quick-start">Quick Start</a> &bull;
  <a href="#architecture">Architecture</a> &bull;
  <a href="#reproducibility">Reproducibility</a>
</p>

<p align="center">
  <a href="https://noahdolevelixir.github.io/medgemma-hackathon/"><img alt="Docs" src="https://img.shields.io/badge/docs-GitHub%20Pages-8ca0e0.svg" /></a>
  <img alt="License" src="https://img.shields.io/badge/license-Apache%202.0-blue.svg" />
  <img alt="Python" src="https://img.shields.io/badge/python-3.12+-blue.svg" />
  <img alt="MedGemma" src="https://img.shields.io/badge/HAI--DEF-MedGemma%204B--IT-green.svg" />
  <img alt="Docker" src="https://img.shields.io/badge/docker-compose-2496ED.svg" />
</p>

---

## Competition Submission

**MedGemma Impact Challenge** | [Kaggle Competition Page](https://www.kaggle.com/competitions/med-gemma-impact-challenge)

- **Team**: Noah Dolev & Maxime Gendre
- **Special Award Track**: Agentic Workflow Prize
- **HAI-DEF Model**: MedGemma 4B-IT (`google/medgemma-4b-it`)
- **Code**: This repository
- **Docs**: See [`MEDGEMMA_INTEGRATION.md`](MEDGEMMA_INTEGRATION.md) and [`AGENTIC_WORKFLOW.md`](AGENTIC_WORKFLOW.md)

---

## What It Does

ElixirTrials takes a clinical trial protocol PDF and turns it into structured, coded eligibility criteria ready for cohort identification. The system extracts inclusion and exclusion criteria, grounds medical entities to standard terminologies, builds expression trees, and presents outputs for human review.

**The problem**: Clinical trial eligibility criteria are buried in unstructured PDF protocols. Manual extraction takes 40+ hours per trial. With 300,000+ active trials on ClinicalTrials.gov, this bottleneck delays cohort identification for observational studies and trial matching.

**The solution**: An end-to-end AI pipeline that automates extraction, grounding, and structuring in minutes rather than days.

---

## MedGemma & HAI-DEF Integration

ElixirTrials uses a **two-model architecture** that leverages the strengths of two HAI-DEF models:

| Model | Role | Why |
|-------|------|-----|
| **MedGemma 4B-IT** (`google/medgemma-4b-it`) | Medical reasoning agent | Biomedical domain expertise for evaluating terminology candidates and making grounding decisions |
| **Gemini 2.5 Flash** | Structured output + extraction | Fast, reliable structured output parsing and PDF criteria extraction |

**How MedGemma is used:**

1. **Entity grounding decisions** &mdash; MedGemma evaluates terminology candidates returned by the TerminologyRouter and selects the best match for each medical entity, providing confidence scores and clinical reasoning.

2. **Agentic retry loop** &mdash; When initial grounding confidence is low (< 0.5), MedGemma enters a 3-question reasoning loop:
   - **Q1**: Is this a valid medical criterion (or should it be skipped)?
   - **Q2**: Is this a derived entity that maps to a more standard concept?
   - **Q3**: Can this entity be rephrased for better terminology search?

3. **Expert review routing** &mdash; After 3 failed attempts, entities are routed to human expert review as a safety valve.

**Why MedGemma over alternatives**: MedGemma's biomedical training provides domain-specific understanding that general-purpose models lack. Its open-weight design enables local deployment with 4-bit quantization on a single GPU, preserving patient data privacy.

See [`MEDGEMMA_INTEGRATION.md`](MEDGEMMA_INTEGRATION.md) for a full code-level map of where MedGemma is used.

---

## Agentic Workflow

ElixirTrials implements a fully agentic AI pipeline using LangGraph with MedGemma as the autonomous decision-making agent.

```text
                    7-Node LangGraph Pipeline
  ┌─────────────────────────────────────────────────────┐
  │                                                     │
  │  ingest → extract → parse → ground → persist →      │
  │                              │       structure →     │
  │                              │       ordinal_resolve │
  │                              │                       │
  │                    ┌─────────┴──────────┐           │
  │                    │  MedGemma Agent    │           │
  │                    │  Decision Loop     │           │
  │                    │                    │           │
  │                    │  TerminologyRouter │           │
  │                    │  + OMOP Mapper     │           │
  │                    │  + Agentic Retry   │           │
  │                    └────────────────────┘           │
  └─────────────────────────────────────────────────────┘
                            │
                            ▼
                    HITL Review Interface
                    (Clinician approval)
```

**Agentic properties:**

- **Autonomous multi-step processing**: 7 LangGraph nodes with conditional routing and error recovery
- **AI decision-making**: MedGemma selects best terminology match from candidates with confidence scoring
- **Tool use**: TerminologyRouter (UMLS, SNOMED CT, LOINC, RxNorm, ICD-10, HPO), OMOP CDM mapper, ToolUniverse SDK
- **Feedback loops**: 3-question reasoning retry when confidence < 0.5, with query reformulation
- **Human-in-the-loop**: Clinician review interface as the final quality gate
- **Error routing**: Expert review escalation when agentic attempts are exhausted

See [`AGENTIC_WORKFLOW.md`](AGENTIC_WORKFLOW.md) for detailed mapping to agentic workflow criteria.

---

## Key Capabilities

- **MedGemma-powered grounding**: Medical entity grounding with agentic reasoning and retry
- **Gemini-powered extraction**: Reads protocol PDFs and extracts inclusion/exclusion criteria with confidence signals
- **Multi-terminology grounding**: Links entities to SNOMED CT, LOINC, RxNorm, ICD-10, and HPO through UMLS and OMOP CDM
- **Dual grounding with reconciliation**: Parallel TerminologyRouter + OMOP mapper with fuzzy agreement checking
- **Expression tree structuring**: Decomposes free-text criteria into atomic conditions with AND/OR/NOT logic
- **Ordinal scale resolution**: Detects scales (NYHA, ECOG, etc.) and maps values to OMOP unit concepts
- **Human-in-the-loop review**: Clinician review, approval, and correction in a split-pane UI
- **Standards-ready exports**: OHDSI CIRCE JSON, FHIR R4 Group, and OMOP CDM evaluation SQL
- **Full audit trail**: Every MedGemma decision, API call, and routing choice is logged

---

## Architecture

```text
hitl-ui (React/Vite)
    |
    | HTTP
    v
api-service (FastAPI) ───────────────> PostgreSQL
    |
    | outbox event
    v
protocol-processor-service (LangGraph)
    |
    |──> MedGemma 4B-IT (medical reasoning, agentic grounding)
    |──> Gemini 2.5 Flash (extraction, structuring, ordinal resolution)
    |──> TerminologyRouter (UMLS, SNOMED, LOINC, RxNorm, ICD-10, HPO)
    |──> OMOP CDM (concept mapping, reconciliation)
    |──> MLflow (experiment tracking, tracing)
```

The processing pipeline runs as a **7-node LangGraph StateGraph**:

`ingest → extract → parse → ground → persist → structure → ordinal_resolve`

Each node is checkpointed to PostgreSQL so failed runs can resume from the last successful step.

---

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- Docker and Docker Compose
- [Google AI Studio API key](https://aistudio.google.com/apikey) for Gemini
- [UMLS API key](https://uts.nlm.nih.gov/uts/signup-login) for terminology grounding
- MedGemma access: either a Vertex AI endpoint or an NVIDIA GPU with 8 GB+ VRAM

### Setup

```bash
# 1) Clone
git clone https://github.com/ElixirTrials/medgemma-hackathon.git
cd medgemma-hackathon

# 2) Install dependencies
uv sync
cd apps/hitl-ui && npm install && cd ../..

# 3) Configure environment
cp .env.example .env
# Set GOOGLE_API_KEY, UMLS_API_KEY, and MedGemma backend (see .env.example)

# 4) Start local stack (DB + MLflow + API + UI)
make run-dev
```

- UI: [http://localhost:3000](http://localhost:3000)
- API: [http://localhost:8000](http://localhost:8000)

### Verify Connectivity

```bash
make verify-gemini
```

---

## Reproducibility

### Option A: Docker Compose (Recommended)

```bash
# Full stack in one command
docker compose -f infra/docker-compose.yml up --build
```

This starts: PostgreSQL, API service (with migrations), UI (nginx), MLflow, and Pub/Sub emulator.

### Option B: Local Development

```bash
make run-dev
```

### MedGemma Backend Options

| Backend | Config | Requirements |
|---------|--------|-------------|
| **Vertex AI** (recommended) | `MODEL_BACKEND=vertex` | GCP project, Vertex AI endpoint, ADC |
| **Local GPU** | `MODEL_BACKEND=local` | NVIDIA GPU (8 GB+ VRAM), torch, bitsandbytes |

See `.env.example` for detailed configuration.

---

## Project Structure

```text
medgemma-hackathon/
  services/
    api-service/                   # FastAPI upload, review, export endpoints
    protocol-processor-service/    # LangGraph extraction/grounding/structuring pipeline
  libs/
    shared/                        # SQLModel domain models and shared utilities
    inference/                     # MedGemma model loading (Vertex AI + local GPU)
    data-pipeline/                 # Data loading and transformation
    evaluation/                    # Quality evaluation framework
    events-py/                     # Transactional outbox/event system
    model-training/                # Fine-tuning utilities
  apps/
    hitl-ui/                       # React + Vite clinician review interface
  infra/                           # Docker Compose and deployment config
  docs/                            # MkDocs documentation site
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Medical Reasoning | **MedGemma 4B-IT** (HAI-DEF, via Vertex AI or local GPU) |
| Extraction & Structuring | **Gemini 2.5 Flash** (Google AI / Vertex AI) |
| Pipeline | LangGraph with PostgreSQL checkpointing |
| API | FastAPI + SQLModel + Alembic |
| Database | PostgreSQL 16 |
| Frontend | React 18 + Vite + Tailwind CSS + Radix UI |
| Terminology | UMLS API + OMOP CDM + ToolUniverse SDK |
| Tracking | MLflow |
| Docs | MkDocs |

---

## Development

| Command | Purpose |
|---------|---------|
| `make run-dev` | Start DB + MLflow + API + UI |
| `make check` | Run lint, type-checking, and tests |
| `make lint-fix` | Auto-fix lint issues (`ruff` + `biome`) |
| `make test` | Run `pytest` and `vitest` |
| `make docs-build` | Build docs site |
| `make quality-eval` | Run quality evaluation on sample PDFs |

---

## Documentation

**[Full documentation (GitHub Pages)](https://noahdolevelixir.github.io/medgemma-hackathon/)** — architecture, data models, user journeys, code tour, and API reference.

To build and serve the docs locally:

```bash
make docs-build && make docs-serve
```

The docs site is deployed to GitHub Pages when `docs/`, `mkdocs.yml`, or component docs change on `main`. To enable: **Settings → Pages → Source**: "Deploy from a branch" → branch **gh-pages**, folder **/ (root)**. Run the "Deploy Documentation" workflow from the Actions tab for the first deploy.

---

## License

Apache 2.0. See [LICENSE](LICENSE).

Built for the [MedGemma Impact Challenge](https://www.kaggle.com/competitions/med-gemma-impact-challenge) on Kaggle.
