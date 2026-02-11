# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-10)

**Core value:** Clinical researchers can upload a protocol PDF and get accurately extracted, UMLS-grounded eligibility criteria that they can review and approve in a single workflow
**Current focus:** Phase 3 - Criteria Extraction Workflow

## Current Position

Phase: 3 of 7 (Criteria Extraction Workflow) -- IN PROGRESS
Plan: 1 of 2 in current phase (Plan 1 complete)
Status: Active
Last activity: 2026-02-11 -- Completed 03-01-PLAN.md (extraction workflow foundation)

Progress: [█████░░░░░] 42%

## Performance Metrics

**Velocity:**
- Total plans completed: 5
- Average duration: 3.6 min
- Total execution time: 0.30 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-infrastructure-data-models | 2 | 7 min | 3.5 min |
| 02-protocol-upload-storage | 2 | 7 min | 3.5 min |
| 03-criteria-extraction-workflow | 1 | 5 min | 5 min |

**Recent Trend:**
- Last 5 plans: 01-02 (4 min), 02-01 (3 min), 02-02 (4 min), 03-01 (5 min)
- Trend: Steady

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: 7-phase structure derived from requirements (standard depth). Phases 3 and 5 flagged for research-phase before planning.
- [Roadmap]: Phase 5 depends on Phase 3 (not Phase 4), enabling partial overlap of Phases 4 and 5.
- [01-01]: Used helper functions for DRY timestamp columns instead of inline sa_column definitions
- [01-01]: Migration uses sa.JSON() for SQLite dev compat; models retain JSONB for PostgreSQL runtime
- [01-01]: Updated alembic.ini sys.path to include shared lib paths for cross-package imports
- [01-02]: events-py depends on shared and sqlmodel to import OutboxEvent model directly
- [01-02]: OutboxProcessor uses FOR UPDATE SKIP LOCKED on PostgreSQL, simple SELECT fallback for SQLite
- [01-02]: Agent services use Docker Compose profiles (agents) to avoid starting by default
- [02-01]: GCS mock fallback returns localhost URLs when GCS_BUCKET_NAME not set for local dev
- [02-01]: Quality scoring: 70% text extractability + 20% page count + 10% encoding bonus
- [02-01]: Confirm-upload accepts optional base64 PDF bytes; quality scoring skipped if not provided
- [02-02]: Reused fetchApi pattern in useProtocols.ts for consistency with useApi.ts
- [02-02]: Drop zone uses semantic button element for a11y compliance (biome useSemanticElements)
- [02-02]: Upload flow: signed URL -> PUT to GCS -> confirm-upload (no base64 for browser uploads)
- [03-01]: Replaced AgentState with ExtractionState TypedDict (7 typed fields for graph data flow)
- [03-01]: Kept Pydantic nesting to max 2 levels to avoid ChatVertexAI serialization issues
- [03-01]: Used asyncio.run() in trigger handler to bridge sync outbox to async graph
- [03-01]: PDF parser self-contained in agent-a-service with no dependency on api-service

### Pending Todos

None yet.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 1 | Fix mypy errors and ensure pytest passes | 2026-02-11 | 01d8621 | [1-fix-mypy-errors](./quick/1-fix-mypy-errors-and-ensure-pytest-passes/) |

### Blockers/Concerns

- Phase 5 (Grounding) needs research-phase: UMLS MCP server deployment, MedGemma on Vertex AI, MedCAT model selection

## Session Continuity

Last session: 2026-02-11
Stopped at: Completed 03-01-PLAN.md
Resume file: None
