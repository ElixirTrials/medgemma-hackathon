# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-10)

**Core value:** Clinical researchers can upload a protocol PDF and get accurately extracted, UMLS-grounded eligibility criteria that they can review and approve in a single workflow
**Current focus:** Phase 5 - Entity Grounding Workflow

## Current Position

Phase: 5 of 7 (Entity Grounding Workflow)
Plan: 2 of 3 in current phase
Status: In Progress
Last activity: 2026-02-11 -- Completed 05-02-PLAN.md (Agent-B foundation: state, schemas, prompts, trigger, UMLS client)

Progress: [██████████████] 83%

## Performance Metrics

**Velocity:**
- Total plans completed: 10
- Average duration: 4.3 min
- Total execution time: 0.72 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-infrastructure-data-models | 2 | 7 min | 3.5 min |
| 02-protocol-upload-storage | 2 | 7 min | 3.5 min |
| 03-criteria-extraction-workflow | 2 | 14 min | 7 min |
| 04-hitl-review-ui | 2 | 7 min | 3.5 min |
| 05-entity-grounding-workflow | 2 | 11 min | 5.5 min |

**Recent Trend:**
- Last 5 plans: 04-01 (3 min), 04-02 (4 min), 05-01 (5 min), 05-02 (6 min)
- Trend: Steady pace, agent-b foundation complete

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
- [03-02]: Graph nodes import from api-service for DB access -- intentional cross-service integration glue
- [03-02]: Added langchain-google-vertexai to root pyproject.toml for workspace-wide availability
- [03-02]: Parse node uses pure Python post-processing (no LLM) for assertion refinement and dedup
- [03-02]: Conditional error routing after ingest and extract; parse->queue always proceeds
- [04-01]: Extracted batch status update and action application into helper functions to pass ruff C901 complexity check
- [04-01]: Used col() wrapper for SQLModel column ordering and IS NOT NULL checks for type safety
- [04-01]: PDF URL staleTime set to 50 minutes (URL expires in 60) to prevent stale signed URLs
- [04-02]: Used useBatchList with client-side filter for batch info in ReviewPage (no single-batch endpoint needed)
- [04-02]: Confidence badge thresholds: >=0.85 high (green), >=0.7 medium (yellow), <0.7 low (red)
- [04-02]: Default sort is confidence ascending (lowest first) to surface items needing most attention
- [05-01]: Mock client returns canned diabetes results (C0011849, SNOMED 73211009) for dev without UMLS credentials
- [05-01]: Tools instantiate client per-request via factory (not module-level) so mock/real is env-determined at call time
- [05-01]: Tiered grounding: exact match (0.95) -> word search (0.75) -> expert review (0.0) with clear method labels
- [05-02]: Replaced AgentState with GroundingState TypedDict (8 fields) following Phase 3 ExtractionState pattern
- [05-02]: UMLS client mock mode returns True/placeholder SNOMED when no API key set for local dev
- [05-02]: Entity schemas use 2-level nesting max (Batch -> Result -> Entity) matching Phase 3 constraint
- [05-02]: Preserved placeholder graph topology; real 4-node graph deferred to 05-03

### Pending Todos

None yet.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 1 | Fix mypy errors and ensure pytest passes | 2026-02-11 | 01d8621 | [1-fix-mypy-errors](./quick/1-fix-mypy-errors-and-ensure-pytest-passes/) |

### Blockers/Concerns

- ~~Phase 5 (Grounding) needs research-phase~~ Research complete. UMLS MCP server built (05-01). Agent-B foundation complete (05-02). Graph nodes and assembly remaining (05-03).

## Session Continuity

Last session: 2026-02-11
Stopped at: Completed 05-02-PLAN.md (Agent-B foundation)
Resume file: None
