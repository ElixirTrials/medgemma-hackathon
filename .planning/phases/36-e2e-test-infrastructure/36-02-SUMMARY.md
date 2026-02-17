---
phase: 36-e2e-test-infrastructure
plan: 02
subsystem: testing
tags: [pytest, e2e, httpx, sqlmodel, docker-compose, upload, cleanup]

# Dependency graph
requires:
  - phase: 36-01
    provides: "E2E conftest with stack detection, auto-skip, authenticated client, DB session"
provides:
  - "upload_test_pdf factory fixture for uploading real PDFs via API upload flow"
  - "e2e_cleanup autouse fixture for deleting all test-created data after each test"
  - "wait_for_pipeline utility for polling protocol status until terminal state"
  - "USE_LOCAL_STORAGE=1 in Docker Compose for local file upload URLs"
  - "Infrastructure smoke test validating upload, API access, and cleanup"
affects: [37-e2e-test-assertions]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Factory fixture pattern: upload_test_pdf returns callable for multiple uploads per test"
    - "Autouse cleanup fixture with CASCADE-aware deletion order"
    - "3-step upload flow: POST /upload -> PUT bytes -> POST /confirm-upload"

key-files:
  created:
    - tests/e2e/test_infrastructure_smoke.py
  modified:
    - infra/docker-compose.yml
    - tests/e2e/conftest.py

key-decisions:
  - "Upload fixture uses the same 3-step flow as the frontend (upload URL, PUT, confirm)"
  - "Cleanup deletes in FK-safe order: entities -> reviews -> audit_log -> criteria -> batches -> outbox -> protocol"
  - "wait_for_pipeline defined as module-level function (not fixture) for flexibility"

patterns-established:
  - "E2E upload pattern: factory fixture returns callable, tracks protocol IDs for cleanup"
  - "E2E cleanup pattern: autouse fixture yields, then deletes all tracked protocols in teardown"

# Metrics
duration: 2min
completed: 2026-02-17
---

# Phase 36 Plan 02: E2E Upload Fixtures and Smoke Test Summary

**Factory fixture for uploading real PDFs via API 3-step flow, autouse cleanup deleting all test data, and smoke test validating the infrastructure end-to-end**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-17T16:59:09Z
- **Completed:** 2026-02-17T17:01:32Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments
- Added USE_LOCAL_STORAGE=1 to Docker Compose api service so upload URLs point to local endpoint
- Built upload_test_pdf factory fixture implementing the full 3-step upload flow (request URL, PUT bytes, confirm)
- Built e2e_cleanup autouse fixture with CASCADE-aware deletion of all test-created protocols and related data
- Added wait_for_pipeline utility for Phase 37 to poll protocol status until terminal state
- Created smoke test with 3 test cases validating upload, custom PDF, and protocol listing

## Task Commits

Each task was committed atomically:

1. **Task 1: Add USE_LOCAL_STORAGE to Docker Compose api service** - `b7df5eb` (chore)
2. **Task 2: Add upload_test_pdf, e2e_cleanup, and wait_for_pipeline to conftest** - `264a16b` (feat)
3. **Task 3: Create infrastructure smoke test** - `a6d8e6c` (feat)

## Files Created/Modified
- `infra/docker-compose.yml` - Added USE_LOCAL_STORAGE=1 to api service environment
- `tests/e2e/conftest.py` - Added upload_test_pdf, _created_protocol_ids, e2e_cleanup, wait_for_pipeline (434 lines total)
- `tests/e2e/test_infrastructure_smoke.py` - Smoke tests: upload, custom PDF, protocol list (51 lines)

## Decisions Made
- Upload fixture uses httpx.put() directly to the upload_url (not through the authenticated client) since the local-upload endpoint doesn't require auth
- Cleanup uses SQLModel delete() statements rather than raw SQL for type safety and consistency with the codebase
- wait_for_pipeline is a module-level function (not a fixture) so it can be imported and used flexibly in Phase 37

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Pre-existing import errors in libs/events-py/tests/ surface when using `-m e2e` flag across all testpaths (same issue documented in 36-01-SUMMARY). Using `tests/e2e/` path directly avoids this. Not in scope.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- All E2E fixtures ready for Phase 37 test assertions
- upload_test_pdf + e2e_cleanup + wait_for_pipeline provide complete lifecycle for E2E tests
- Smoke tests validate infrastructure works; Phase 37 will add pipeline completion and criteria verification tests

---
*Phase: 36-e2e-test-infrastructure*
*Completed: 2026-02-17*
