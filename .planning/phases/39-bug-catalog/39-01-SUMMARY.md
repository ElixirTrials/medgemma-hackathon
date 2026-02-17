---
phase: 39-bug-catalog
plan: 01
subsystem: quality-eval
tags: [bug-catalog, quality, pipeline-errors, grounding]
dependency-graph:
  requires: []
  provides: [bug-catalog-section, catalog_bugs-function]
  affects: [scripts/quality_eval.py]
tech-stack:
  added: []
  patterns: [severity-categorized-issue-catalog, sub-analyzer-composition]
key-files:
  created: []
  modified:
    - scripts/quality_eval.py
key-decisions:
  - "Entities with confidence >= 0.5 but no codes are not flagged (edge case considered unlikely)"
  - "Bug Catalog section placed after LLM Assessment in report"
  - "Orphan entity detection skipped per plan (entities nested under criteria in API data)"
metrics:
  duration: 121s
  completed: 2026-02-17T17:58:39Z
---

# Phase 39 Plan 01: Bug Catalog Summary

Bug catalog analysis with severity-categorized pipeline issue inventory added to quality_eval.py report.

## What Was Done

### Task 1: Add bug catalog analysis functions (763c756)

Added four functions to `scripts/quality_eval.py` between `compute_terminology_success` and the LLM assessment section:

- `catalog_bugs()` -- Main entry point composing three sub-analyzers into a structured dict with `ungrounded_entities`, `pipeline_errors`, `structural_issues`, and `summary` keys.
- `_find_ungrounded_entities()` -- Identifies entities with no UMLS CUI and no terminology codes (snomed, rxnorm, icd10, loinc, hpo). Critical severity if confidence is None/0, warning if 0 < confidence < 0.5.
- `_find_pipeline_errors()` -- Catalogs protocols with `extraction_failed`, `grounding_failed`, `pipeline_failed`, or `dead_letter` status. All critical severity.
- `_find_structural_issues()` -- Flags criteria with zero entities (warning) and criteria with unknown type not in {inclusion, exclusion} (info).

### Task 2: Integrate bug catalog into report and main flow (1046d8f)

- Added `bug_catalog: dict | None = None` parameter to `generate_report()` (backward compatible).
- Rendered full Bug Catalog markdown section with severity-grouped subsections: Critical (pipeline errors, ungrounded entities), Warnings (low-confidence ungrounded, empty criteria), Info (unknown criteria types).
- Each subsection includes a table when issues exist or "None found." when empty, plus an actionable recommendation.
- Added Step 3b in `main()` to build bug catalog from existing data (no new API calls).
- Passed `bug_catalog` to `generate_report()`.

## Deviations from Plan

None -- plan executed exactly as written.

## Verification

- `uv run ruff check scripts/quality_eval.py` -- passed clean
- `uv run python scripts/quality_eval.py --help` -- loads without error
- Functional test with mock data confirmed all 5 required subsections render correctly with severity levels and recommendations

## Self-Check: PASSED
