# Architecture Overview

ElixirTrials is a monorepo containing three runtime components and several shared libraries, all orchestrated through an event-driven pipeline.

## Core Principles

1. **Consolidated pipeline** — All processing (extraction, grounding, structuring) runs in a single `protocol-processor-service` via LangGraph. The earlier two-service split (`extraction-service` + `grounding-service`) is legacy.
2. **Event-driven trigger** — Processing starts from a `protocol_uploaded` outbox event. There is no `criteria_extracted` cross-service event.
3. **Error accumulation** — Individual entity/criterion failures don't crash the pipeline. Partial results are preserved alongside errors.
4. **Human-in-the-loop** — All AI outputs go through a review step before being considered final.

## Runtime Components

| Component | Tech | Port | Role |
|-----------|------|------|------|
| `hitl-ui` | React + Vite + Radix | 3000 | Upload PDFs, review criteria, manage protocols |
| `api-service` | FastAPI + SQLModel | 8000 | REST API, outbox processor, export endpoints |
| `protocol-processor-service` | LangGraph + Gemini | (in-process) | 7-node extraction/grounding/structuring pipeline |

## Shared Libraries

| Library | Purpose |
|---------|---------|
| `libs/shared` | SQLModel domain models (`Protocol`, `Criteria`, `Entity`, etc.) |
| `libs/events-py` | Transactional outbox processor and domain event contracts |
| `libs/inference` | Model inference utilities |
| `libs/evaluation` | Quality evaluation framework |
| `libs/data-pipeline` | Data loading helpers |
| `libs/model-training` | Fine-tuning scripts |

## Infrastructure

| Service | Tech | Purpose |
|---------|------|---------|
| PostgreSQL | 16-alpine | Application database + LangGraph checkpoints |
| MLflow | v3.9.0 | Experiment tracking, trace observability |
| OMOP Vocab DB | PostgreSQL | Optional OMOP vocabulary for concept resolution |
| Pub/Sub Emulator | GCP emulator | Not actively used (outbox pattern preferred) |

See [System Architecture](system-architecture.md) for diagrams and [Data Models](data-models.md) for the schema.
