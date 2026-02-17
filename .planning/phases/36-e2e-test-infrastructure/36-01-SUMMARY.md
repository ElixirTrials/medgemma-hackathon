---
phase: 36-e2e-test-infrastructure
plan: 01
subsystem: testing
tags: [pytest, e2e, httpx, jwt, sqlmodel, docker-compose]

# Dependency graph
requires: []
provides:
  - "E2E test package (tests/e2e/) with pytest discovery"
  - "Docker Compose stack detection with auto-skip when unavailable"
  - "Authenticated httpx client fixture (e2e_api_client)"
  - "Direct PostgreSQL session fixture (e2e_db_session)"
  - "Zero-overhead guard: _wants_e2e() prevents health checks on non-e2e runs"
affects: [36-02, 37-e2e-test-assertions]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "pytest_configure + pytest_collection_modifyitems for conditional skip"
    - "_wants_e2e() guard pattern to avoid health-check overhead on non-e2e runs"
    - "JWT test token generation matching API auth (PyJWT HS256)"

key-files:
  created:
    - tests/e2e/__init__.py
    - tests/e2e/conftest.py
  modified:
    - pyproject.toml

key-decisions:
  - "No root tests/__init__.py to avoid namespace collision with service test packages"
  - "Guard _check_stack() behind _wants_e2e() so uv run pytest has zero e2e overhead"
  - "e2e_db_session does NOT auto-rollback -- cleanup deferred to Plan 02"

patterns-established:
  - "E2E fixture naming: e2e_ prefix for all E2E-specific fixtures"
  - "Stack detection: session-scoped check, collection-time skip via marker"

# Metrics
duration: 3min
completed: 2026-02-17
---

# Phase 36 Plan 01: E2E Test Infrastructure Summary

**E2E pytest conftest with Docker Compose stack detection, auto-skip on unavailable stack, authenticated httpx client, and direct DB session fixtures**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-17T16:54:45Z
- **Completed:** 2026-02-17T16:57:16Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Created tests/e2e/ package discoverable by pytest via updated testpaths
- Built Docker Compose detection that checks both API health endpoint and PostgreSQL connectivity
- Implemented _wants_e2e() guard so non-e2e pytest invocations have zero overhead from health checks
- Provided e2e_api_client fixture with JWT auth matching the real API's get_current_user dependency
- Provided e2e_db_session fixture for direct database verification queries

## Task Commits

Each task was committed atomically:

1. **Task 1: Update pyproject.toml testpaths and create E2E package** - `1cd64be` (feat)
2. **Task 2: Create E2E conftest with Docker Compose detection and core fixtures** - `270a322` (feat)

## Files Created/Modified
- `tests/e2e/__init__.py` - E2E test package marker (empty file)
- `tests/e2e/conftest.py` - Docker Compose detection, auto-skip hook, DB session, auth client, API URL fixtures (171 lines)
- `pyproject.toml` - Added "tests" to testpaths array

## Decisions Made
- Omitted root `tests/__init__.py` to avoid Python namespace collision with existing `tests/` directories in services/libs (pre-existing import errors in libs/events-py/tests/ confirmed unrelated)
- Guarded `_check_stack()` behind `_wants_e2e()` to ensure zero overhead on regular pytest runs
- e2e_db_session yields without rollback; cleanup fixtures planned for 36-02

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- Pre-existing import errors in `libs/events-py/tests/test_models.py` and `test_outbox.py` (ModuleNotFoundError) surfaced when running `pytest --collect-only -m e2e` across all testpaths. Confirmed these are pre-existing (present before any changes) and out of scope. E2E-specific verification (`pytest --collect-only tests/e2e/`) passes cleanly.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- E2E conftest is ready for Plan 02 (test assertions and baseline)
- Any test marked `@pytest.mark.e2e` will auto-skip when Docker Compose is down
- Phase 37 can build on these fixtures to write actual E2E test cases

---
*Phase: 36-e2e-test-infrastructure*
*Completed: 2026-02-17*
