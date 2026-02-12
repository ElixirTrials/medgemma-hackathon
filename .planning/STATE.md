# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-10)

**Core value:** Clinical researchers can upload a protocol PDF and get accurately extracted, UMLS-grounded eligibility criteria that they can review and approve in a single workflow
**Current focus:** Phase 7 - Production Hardening

## Current Position

Phase: 7 of 7+3 (Production Hardening)
Plan: 5 of TBD
Status: Phase 7 in progress - Plan 03 complete (MLflow observability integration)
Last activity: 2026-02-12 -- Plan 07-03 complete (41 min, MLflow tracing for all system events)

Progress: [█████████████████░] 98%

## Performance Metrics

**Velocity:**
- Total plans completed: 24
- Average duration: 9.1 min
- Total execution time: 3.6 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-infrastructure-data-models | 2 | 7 min | 3.5 min |
| 02-protocol-upload-storage | 2 | 7 min | 3.5 min |
| 03-criteria-extraction-workflow | 2 | 14 min | 7 min |
| 04-hitl-review-ui | 2 | 7 min | 3.5 min |
| 05-entity-grounding-workflow | 3 | 19 min | 6.3 min |
| 05.1-error-handling-hardening | 1 | 16 min | 16 min |
| 05.2-test-coverage | 3 | 74 min | 24.7 min |
| 05.3-rename-services-and-docs | 3 | 17 min | 5.7 min |
| 06-entity-approval-auth-search | 2 | 16 min | 8 min |
| 07-production-hardening | 4 | 61 min | 15.3 min |

**Recent Trend:**
- Last 5 plans: 07-01 (6 min), 07-02 (12 min), 07-04 (2 min), 07-03 (41 min)
- Trend: Phase 7 observability complete - MLflow tracing integrated across all system layers

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
- [05-03]: MCP grounding with direct UMLS client fallback for resilience when MCP server unavailable
- [05-03]: Helper function extraction to pass ruff C901 complexity (max 10) in extract_entities and validate_confidence
- [05-03]: context_window stored as dict wrapper {"text": "..."} to match Entity model JSON column
- [05.1-01]: Kept local:// path rejection as ValueError in gcs.py (explicit error vs silent ignore)
- [05.1-01]: Used type: ignore for MultiServerMCPClient async context manager due to library typing limitation
- [05.1-01]: queue.py error return already present -- verified rather than modified
- [05.2-01]: Added per-file-ignores for D102/D103 in test files (standard ruff practice)
- [05.2-01]: Used raw PDF bytes for empty PDF test (PyMuPDF cannot save 0-page documents)
- [05.2-01]: UMLS tests use AsyncMock + patch.object(httpx, 'AsyncClient') pattern for httpx mocking
- [05.2-01]: Outbox processor publishes events even with empty handler list (verified actual behavior)
- [05.3-01]: Used git mv to preserve history during service directory rename (agent-a -> extraction)
- [05.3-01]: Renamed Docker service from agent-a to extraction for alignment with implementation name
- [05.3-02]: Used git mv to preserve history during service directory rename (agent-b -> grounding)
- [05.3-02]: Renamed Docker service from agent-b to grounding for alignment with implementation name
- [05.3-03]: Updated only forward-looking references in planning docs (preserved historical decision records)
- [05.3-03]: Replaced template diagrams in PROJECT_OVERVIEW.md with system-specific architecture (extraction/grounding pipeline)
- [05.3-03]: Fixed Dockerfiles missed in 05.3-01 and 05.3-02 as deviation (blocking issue for future builds)
- [06-01]: Router-level auth dependencies protect all endpoints in protocols/reviews/entities/search routers
- [06-01]: Public endpoints: /health, /ready, /, /auth/login, /auth/callback (no auth required)
- [06-01]: FastAPI Header(...) dependency for JWT extraction (422 if missing, 401 if invalid)
- [06-01]: test_client fixture overrides get_current_user so existing tests pass without modification
- [06-01]: PostgreSQL full-text search with GIN index, LIKE fallback for SQLite dev
- [06-01]: Entity approval follows criteria review pattern (Review + AuditLog records)
- [06-02]: Zustand store with localStorage for auth state persistence across page refreshes
- [06-02]: Keep fetchApi duplicated in each hook file (matching existing pattern in useReviews/useProtocols)
- [06-02]: Use Radix Tabs for criteria/entities toggle in ReviewPage (already in dependencies)
- [06-02]: Debounce search input with 300ms delay to avoid excessive API calls
- [06-02]: SNOMED badge with blue medical theme, UMLS CUI as clickable link to external browser
- [06-02]: Show grounding confidence with same 3-tier badge as criteria confidence
- [07-01]: ProtocolStatus enum stored as string in DB (not PostgreSQL enum type) for simplicity
- [07-01]: error_reason field stores human-readable message, metadata_.error stores technical details
- [07-01]: Failed events re-polled via status.in_(['pending', 'failed']) for retry logic
- [07-01]: Lazy archival triggered on get_protocol access (7-day cutoff)
- [07-01]: Used col() wrapper for mypy compatibility with in_() operator
- [07-02]: Per-service circuit breakers (gemini, umls, gcs, vertex_ai) for independent failure handling
- [07-02]: Circuit breaker threshold: 3 consecutive failures, 60s recovery timeout (pybreaker)
- [07-02]: Human-readable error categorization for protocol failure reasons
- [07-02]: Upload endpoint checks circuit breaker state and warns users proactively
- [07-02]: PENDING protocol status indicates delayed processing due to service unavailability
- [07-03]: Use mlflow.start_span (lightweight) vs mlflow.start_run for request/event tracing
- [07-03]: Set log_models=False in mlflow.langchain.autolog to avoid large artifacts
- [07-03]: All MLflow operations wrapped in try/except for safe no-op without MLflow infrastructure
- [07-03]: Skip health/ready endpoints in middleware to reduce monitoring probe noise
- [07-03]: CircuitBreakerListener inheritance for pybreaker compatibility with type: ignore[override]
- [07-04]: Human-readable STATUS_LABELS map for underscore-separated status values (UI consistency)
- [07-04]: Retry button positioned in error alert for contextual action (UX pattern)
- [07-04]: Processing banner for uploaded/extracting states without circuit breaker detection (backend handles it)
- [07-04]: Biome auto-formatting applied to match project style (CI/CD requirement)

### Pending Todos

- [07-02]: Complete retry decorator application on external service calls (GCS, PDF fetch, MCP, Gemini, Vertex AI)

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 1 | Fix mypy errors and ensure pytest passes | 2026-02-11 | 01d8621 | [1-fix-mypy-errors](./quick/1-fix-mypy-errors-and-ensure-pytest-passes/) |

### Blockers/Concerns

- ~~Phase 5 (Grounding) needs research-phase~~ Research complete. UMLS MCP server built (05-01). Agent-B foundation complete (05-02). Graph nodes and assembly complete (05-03). Phase 5 fully done.

## Session Continuity

Last session: 2026-02-12
Stopped at: Completed Phase 7 Plan 03 (MLflow observability integration). All system events traced via MLflow.
Resume file: None
