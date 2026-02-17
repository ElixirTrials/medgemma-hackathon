---
phase: 34-corpus-comparison-export
plan: 02
subsystem: api-service
tags: [fastapi, gemini, fuzzy-matching, batch-comparison, re-extraction]
dependency_graph:
  requires:
    - 33-01: re-extraction endpoint (batch archiving, CriteriaBatch.is_archived)
    - 33-02: re-extraction frontend (context for timeline feature)
  provides:
    - POST /reviews/criteria/{id}/rerun (AI proposal without DB write)
    - GET /reviews/batch-compare (fuzzy diff between two batches)
    - GET /protocols/{id}/batches (all batches for timeline)
  affects:
    - services/api-service/src/api_service/main.py (two new router registrations)
tech_stack:
  added:
    - google-generativeai (lazy import in criterion_rerun.py)
    - rapidfuzz (already present from 33-01)
  patterns:
    - Gemini structured output via response_schema + response_mime_type=application/json
    - Read-only AI endpoint (no DB writes — proposal pattern)
    - Bulk count queries via GROUP BY to avoid N+1 on batch timeline
    - Helper function extraction to stay under ruff C901 complexity limit
key_files:
  created:
    - services/api-service/src/api_service/criterion_rerun.py
    - services/api-service/src/api_service/batch_compare.py
  modified:
    - services/api-service/src/api_service/protocols.py
    - services/api-service/src/api_service/main.py
decisions:
  - Lazy import for google-generativeai in criterion_rerun.py (linter converted
    top-level import to lazy for test isolation; kept as-is since it works)
  - _find_best_match helper extracted from compare_batches to satisfy C901 < 10
  - Bare dict annotations replaced with Dict[str, Any] to match mypy strict mode
    used by the rest of the codebase
  - Pre-existing mypy errors in protocols.py (metadata_ bare dict, unused type:ignore)
    left untouched per scope boundary rule — they pre-date this plan
  - Bulk GROUP BY queries for criteria counts in list_protocol_batches to avoid N+1
metrics:
  duration: 5 min
  completed: 2026-02-17
  tasks: 2
  files: 4
---

# Phase 34 Plan 02: Per-Criterion AI Re-run, Batch Compare, Protocol Batches Summary

One-liner: Gemini-powered read-only criterion correction proposal, token_set_ratio batch diff with 70%/90% thresholds, and all-batches protocol timeline endpoint.

## What Was Built

Three backend endpoints enabling the Phase 34 corpus comparison user stories:

**1. POST /reviews/criteria/{criterion_id}/rerun** (`criterion_rerun.py`)

Single-criterion AI re-extraction using reviewer feedback as guidance. Sends the original criterion text, current structured fields, and reviewer natural-language correction to Gemini via structured output (response_schema=SingleCriterionResult). Returns original vs. revised fields as a proposal — this endpoint intentionally NEVER writes to the database. The reviewer must call the existing `POST /reviews/criteria/{id}/action` with action=modify to commit any changes.

Handles Gemini failures gracefully with 422 and a human-readable message. Tries `response.parsed` first, falls back to `SingleCriterionResult.model_validate_json(response.text)`.

**2. GET /reviews/batch-compare** (`batch_compare.py`)

Fuzzy-matched diff between two extraction batches. For each criterion in batch A, finds the best unmatched criterion in batch B using `rapidfuzz.fuzz.token_set_ratio`. Classification thresholds (distinct from the 90% inheritance threshold used in re-extraction):
- score >= 90.0: unchanged
- 70.0 <= score < 90.0: changed
- score < 70.0: removed (from batch A perspective)
- unmatched batch B criteria: added

Enforces criteria_type guard before text comparison (same pattern as 33-01 fuzzy_matching.py) to prevent inclusion/exclusion false positives.

**3. GET /protocols/{protocol_id}/batches** (`protocols.py`)

Returns ALL batches for a protocol including archived ones, ordered chronologically (created_at ASC). Uses two bulk GROUP BY queries to compute criteria_count and reviewed_count per batch without N+1. Intentionally does NOT touch the existing `GET /reviews/batches` endpoint which correctly excludes archived batches for the review workflow.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Linter converted google-generativeai import to lazy**
- **Found during:** Task 1 (ruff fix run)
- **Issue:** Ruff auto-converted top-level `import google.generativeai` to lazy import inside the endpoint function with a try/except for ImportError
- **Fix:** Kept the linter's version (adds graceful 503 if package not installed, which is strictly better)
- **Files modified:** criterion_rerun.py
- **Commit:** 8907e8b

**2. [Rule 2 - Missing] C901 complexity exceeded in compare_batches**
- **Found during:** Task 1 (ruff check)
- **Issue:** compare_batches() had complexity 13 > 10 due to nested matching loop
- **Fix:** Extracted `_find_best_match()` helper to reduce main function complexity
- **Files modified:** batch_compare.py
- **Commit:** 8907e8b

**3. [Rule 1 - Bug] Bare dict annotations failing mypy**
- **Found during:** Task 1 (mypy check)
- **Issue:** `dict` and `list[dict]` without type params rejected by mypy
- **Fix:** Replaced with `Dict[str, Any]` and `list[Dict[str, Any]]` using imported typing aliases
- **Files modified:** criterion_rerun.py, batch_compare.py
- **Commit:** 8907e8b

## Self-Check: PASSED

- FOUND: services/api-service/src/api_service/criterion_rerun.py
- FOUND: services/api-service/src/api_service/batch_compare.py
- FOUND: commit 8907e8b (task 1: criterion_rerun + batch_compare + main.py)
- FOUND: commit ebf02d3 (task 2: protocols.py batch timeline endpoint)
