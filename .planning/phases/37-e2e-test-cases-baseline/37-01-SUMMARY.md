---
phase: 37-e2e-test-cases-baseline
plan: 01
subsystem: testing
tags: [pytest, e2e, regression-baseline, httpx, pipeline]

# Dependency graph
requires:
  - phase: 36-e2e-test-infrastructure
    provides: conftest.py fixtures (upload_test_pdf, e2e_api_client, wait_for_pipeline, cleanup)
provides:
  - E2E pipeline tests (upload -> extraction -> grounding -> criteria with entities)
  - Numeric regression baseline config for test PDFs
  - Fixed URL paths in Phase 36 E2E files (removed incorrect /api prefix)
affects: [37-e2e-test-cases-baseline, 38-quality-evaluation]

# Tech tracking
tech-stack:
  added: []
  patterns: [regression baseline thresholds, module-level test helpers, relative imports in test packages]

key-files:
  created:
    - tests/e2e/baseline.py
    - tests/e2e/test_pipeline_full.py
  modified:
    - tests/e2e/conftest.py
    - tests/e2e/test_infrastructure_smoke.py

key-decisions:
  - "Conservative baseline thresholds (3 criteria, 1 inclusion, 1 exclusion, 2 entities, 1 grounded) to avoid flaky tests"
  - "Relative imports (.baseline, .conftest) for test module cross-references since tests/ lacks __init__.py"

patterns-established:
  - "Regression baseline pattern: BASELINES dict + get_baseline() helper for numeric threshold enforcement"
  - "Module-level helpers (_upload_and_wait, _fetch_criteria) shared across test class methods"

# Metrics
duration: 3min
completed: 2026-02-17
---

# Phase 37 Plan 01: E2E Test Cases & Baseline Summary

**4 pipeline E2E tests (completion, criteria types, grounded entities, regression baseline) with conservative numeric thresholds and fixed URL paths**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-17T17:17:56Z
- **Completed:** 2026-02-17T17:20:59Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments
- Fixed incorrect `/api/protocols` URL paths in Phase 36 conftest.py and smoke tests to match actual FastAPI router prefix `/protocols`
- Created regression baseline config with conservative thresholds for the default CRC protocol test PDF
- Built 4 independent E2E pipeline tests covering completion status, inclusion/exclusion criteria types, grounded entity quality, and full baseline regression

## Task Commits

Each task was committed atomically:

1. **Task 0: Fix API URL paths in Phase 36 E2E files** - `125dede` (fix)
2. **Task 1: Create regression baseline config** - `859d0cb` (feat)
3. **Task 2: Create full pipeline E2E test module** - `0c036e7` (feat)

## Files Created/Modified
- `tests/e2e/conftest.py` - Fixed URL paths: /api/protocols -> /protocols throughout upload fixture and wait_for_pipeline
- `tests/e2e/test_infrastructure_smoke.py` - Fixed URL paths: /api/protocols -> /protocols in all smoke tests
- `tests/e2e/baseline.py` - NEW: BASELINES dict with min thresholds + get_baseline() helper
- `tests/e2e/test_pipeline_full.py` - NEW: 4 E2E tests (TestFullPipeline class) with shared helpers

## Decisions Made
- Used conservative baseline thresholds (min 3 criteria, 1 inclusion, 1 exclusion, 2 entities, 1 grounded) -- intentionally low floors to prevent flaky tests; should be tightened after stable runs
- Used relative imports (.baseline, .conftest) instead of absolute (tests.e2e.baseline) since tests/ directory lacks __init__.py and isn't in pythonpath

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed import path from absolute to relative**
- **Found during:** Task 2 (Create full pipeline E2E test module)
- **Issue:** `from tests.e2e.baseline import BASELINES` failed with ModuleNotFoundError because tests/ has no __init__.py
- **Fix:** Changed to relative imports: `from .baseline import BASELINES` and `from .conftest import wait_for_pipeline`
- **Files modified:** tests/e2e/test_pipeline_full.py
- **Verification:** `uv run pytest tests/e2e/test_pipeline_full.py --collect-only` collects 4 tests
- **Committed in:** 0c036e7 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Import fix necessary for tests to be importable by pytest. No scope creep.

## Issues Encountered
None beyond the import path fix documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 7 E2E tests (3 smoke + 4 pipeline) collected without errors
- Tests skip gracefully when Docker Compose stack is not running
- Pipeline tests ready to execute against real stack with `uv run pytest tests/e2e/ -m e2e`
- Baseline thresholds ready to be tightened after first successful full pipeline runs

---
*Phase: 37-e2e-test-cases-baseline*
*Completed: 2026-02-17*
