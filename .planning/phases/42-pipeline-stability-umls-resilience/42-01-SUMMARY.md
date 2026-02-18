---
phase: 42-pipeline-stability-umls-resilience
plan: 01
subsystem: infra
tags: [mlflow, docker-compose, gcs, sha256, deduplication, tracing]

# Dependency graph
requires:
  - phase: 40-legacy-cleanup-tooluniverse-grounding
    provides: ToolUniverse-based terminology grounding (replaced UMLS API key pattern)
provides:
  - try/finally span closure guaranteeing MLflow traces never stuck IN_PROGRESS
  - MLFLOW_TRACE_TIMEOUT_SECONDS=300 as safety-net for orphaned traces
  - Upload bind mount persisting data/uploads/ across docker compose restarts
  - SHA-256 content deduplication via .hash-index.json in local_save_file
affects: [43-pipeline-stability-umls-resilience, e2e-tests, docker-deployment]

# Tech tracking
tech-stack:
  added: [hashlib, json (stdlib — no new dependencies)]
  patterns:
    - try/finally inside context manager for guaranteed cleanup
    - SHA-256 content-addressed storage with symlink dedup
    - bind mount over named volume for browsable dev data

key-files:
  created: []
  modified:
    - services/protocol-processor-service/src/protocol_processor/trigger.py
    - infra/docker-compose.yml
    - services/api-service/src/api_service/gcs.py

key-decisions:
  - "try/finally is INSIDE the with mlflow.start_span() block — end_trace() is a no-op if span already closed normally"
  - "MLFLOW_TRACE_TIMEOUT_SECONDS=300 is a safety net only (for process-kill scenarios), not the primary fix"
  - "Bind mount (../data/uploads:/app/uploads) instead of named volume — dev: host directory is browsable"
  - "SHA-256 symlink deduplication preserves URI compatibility while saving disk space"
  - ".env.example has no UMLS_API_KEY — cleanup sub-task was a no-op"

patterns-established:
  - "MLflow trace safety: always capture trace_id before awaiting, wrap await in try/finally with end_trace"
  - "Content-addressed local storage: _content_hash() + .hash-index.json + symlinks for dedup"

requirements-completed: [FIX-B14, FIX-B13]

# Metrics
duration: 3min
completed: 2026-02-18
---

# Phase 42 Plan 01: Pipeline Stability — MLflow Leak Fix + Upload Persistence

**MLflow traces guaranteed closed via try/finally with end_trace(), upload directory persists across container restarts via bind mount with SHA-256 deduplication**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-02-18T12:17:13Z
- **Completed:** 2026-02-18T12:20:22Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- `_run_pipeline()` now captures `trace_id` before `graph.ainvoke()` and wraps it in try/finally with `end_trace()` — MLflow traces can no longer get stuck IN_PROGRESS on exception
- `MLFLOW_TRACE_TIMEOUT_SECONDS=300` added to api service in docker-compose.yml as safety net for process-kill scenarios
- `data/uploads/` bind-mounted into container at `/app/uploads` — files survive `docker compose down/up` cycles
- `local_save_file()` now uses SHA-256 hash index to detect and deduplicate identical PDF content via symlinks

## Task Commits

Each task was committed atomically:

1. **Task 1: MLflow trace leak fix with try/finally span closure** - `2216465` (fix)
2. **Task 2: Upload volume persistence with SHA-256 deduplication** - `5416731` (feat)

## Files Created/Modified

- `services/protocol-processor-service/src/protocol_processor/trigger.py` - Added try/finally with trace_id capture and end_trace() inside MLflow span context manager
- `infra/docker-compose.yml` - Added MLFLOW_TRACE_TIMEOUT_SECONDS=300, LOCAL_UPLOAD_DIR=/app/uploads, bind mount ../data/uploads:/app/uploads
- `services/api-service/src/api_service/gcs.py` - Added hashlib/json imports, _content_hash() function, SHA-256 dedup logic in local_save_file()

## Decisions Made

- `end_trace()` inside finally is a no-op when the span closes normally via context manager __exit__ — safe to always call
- Bind mount chosen over named volume: dev workflow benefits from browsable host directory at data/uploads/
- Docker auto-creates the host bind-mount directory on `docker compose up` — no .gitkeep needed
- .env.example had no UMLS_API_KEY references — cleanup sub-task skipped as planned no-op

## Deviations from Plan

None — plan executed exactly as written. The .env.example UMLS cleanup was explicitly specified as conditional ("if any UMLS_API_KEY references exist") and correctly skipped.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required. Docker bind mount is auto-created on `docker compose up`.

## Next Phase Readiness

- Phase 42-02 (ToolUniverse resilience) can proceed — no dependencies on this plan
- Upload files at data/uploads/ on host machine (gitignored via existing data/ rule in .gitignore)
- MLflow tracing stability fixes gaps B14 and B13 from E2E test report

---
*Phase: 42-pipeline-stability-umls-resilience*
*Completed: 2026-02-18*

## Self-Check: PASSED

All files verified present. All task commits verified in git log.
