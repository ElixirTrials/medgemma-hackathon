---
phase: 34-corpus-comparison-export
plan: 01
subsystem: api
tags: [fastapi, sqlmodel, integrity, metrics, pytest]

# Dependency graph
requires:
  - phase: 33-re-extraction-tooling
    provides: reviews.py router, AuditLog patterns, batch/criteria models
provides:
  - GET /integrity/check endpoint with 4 detection categories + protocol scoping
  - CI test suite (test_integrity.py) with 6 tests covering all categories
  - GET /reviews/batches/{batch_id}/metrics endpoint with 2-query efficiency
affects: [corpus-comparison-export, frontend metrics UI, data trust/compliance]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Read-only integrity check split into 4 focused helper functions to stay under C901=10"
    - "Lazy google.generativeai import inside endpoint to avoid import errors in test env"
    - "Protocol-scoped checks via criteria_ids list passed to each check function"
    - "2-query metrics: bulk criteria load + audit log join, no N+1"

key-files:
  created:
    - services/api-service/src/api_service/integrity.py
    - services/api-service/tests/test_integrity.py
  modified:
    - services/api-service/src/api_service/reviews.py
    - services/api-service/src/api_service/main.py
    - services/api-service/src/api_service/criterion_rerun.py

key-decisions:
  - "integrity.py split into 4 private check functions (_check_orphaned_entities etc.) to satisfy ruff C901 < 10 complexity limit"
  - "criterion_rerun.py google.generativeai import made lazy (inside endpoint) — missing package blocked all test collection (Rule 3 auto-fix)"
  - "Scoping: empty protocol yields empty criteria list, each check returns [] immediately rather than running queries with empty IN clauses"

patterns-established:
  - "IntegrityIssue category uses _IssueCategory type alias to avoid line-length violation on long Literal union"
  - "BatchMetricsResponse.modification_breakdown maps AuditLog schema_version to human-readable keys"

# Metrics
duration: 4min
completed: 2026-02-17
---

# Phase 34 Plan 01: Data Integrity Check and Agreement Metrics Summary

**Read-only integrity check API (4 detection categories, protocol scoping, 6 CI tests) plus 2-query batch agreement metrics endpoint with modification breakdown by schema_version**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-17T10:34:59Z
- **Completed:** 2026-02-17T10:39:00Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- `GET /integrity/check` detects orphaned entities (error), incomplete audit logs (warning), ungrounded entities (warning), and reviews without audit trail (warning)
- Protocol scoping via `?protocol_id=X` filters all 4 checks to entities/criteria in that protocol's batches
- 6 pytest tests pass: one per detection category, clean-DB baseline, protocol-scoped isolation
- `GET /reviews/batches/{batch_id}/metrics` returns approve/reject/modified/pending counts with percentages, `modification_breakdown` by schema_version, and `per_criterion_details` for drill-down — using exactly 2 SQL queries

## Task Commits

Each task was committed atomically:

1. **Task 1: Data integrity check endpoint and CI test suite** - `68d9901` (feat)
2. **Task 2: Agreement metrics endpoint on reviews router** - `ab1d303` (feat)

**Plan metadata:** (docs commit to follow)

## Files Created/Modified

- `services/api-service/src/api_service/integrity.py` - GET /integrity/check with 4 detection categories
- `services/api-service/tests/test_integrity.py` - 6 tests (4 detection + 2 baseline/scoping)
- `services/api-service/src/api_service/reviews.py` - BatchMetricsResponse + GET /batches/{id}/metrics
- `services/api-service/src/api_service/main.py` - integrity_router registered behind auth
- `services/api-service/src/api_service/criterion_rerun.py` - lazy import fix (deviation)

## Decisions Made

- Integrity check split into 4 private helper functions to satisfy ruff C901 complexity limit (< 10)
- Empty `scoped_criteria_ids` list causes each check to return `[]` immediately (avoids empty `IN ()` SQL)
- `_IssueCategory` type alias used for Literal union to avoid E501 line-length violation on the model field

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed eager google.generativeai import in criterion_rerun.py blocking test collection**
- **Found during:** Task 1 (running pytest for test_integrity.py)
- **Issue:** `criterion_rerun.py` imported `google.generativeai` at module level; the package is not installed in the dev/test venv, so `from api_service.main import app` raised `ModuleNotFoundError` and all 6 tests errored at setup
- **Fix:** Removed top-level `import google.generativeai as genai` and `from google.generativeai import types`; added lazy imports inside the `rerun_criterion` endpoint function with a graceful 503 fallback if not installed
- **Files modified:** `services/api-service/src/api_service/criterion_rerun.py`
- **Verification:** All 6 integrity tests pass after fix; ruff clean on criterion_rerun.py
- **Committed in:** `68d9901` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 3 - blocking)
**Impact on plan:** Necessary to unblock test collection. No scope creep.

## Issues Encountered

- ruff C901 (complexity > 10) triggered on the initial `check_integrity` monolithic function — resolved by extracting 4 named helper functions, which also improved readability

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Integrity endpoint and metrics endpoint are deployed behind existing auth
- Frontend can now call `GET /reviews/batches/{batch_id}/metrics` for the progressive disclosure metrics UI
- `GET /integrity/check?protocol_id=X` is ready for the corpus comparison UI

---
*Phase: 34-corpus-comparison-export*
*Completed: 2026-02-17*
