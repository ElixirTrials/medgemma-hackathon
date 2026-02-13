---
phase: 22-backend-data-model-api-extension
plan: 01
subsystem: api-service
tags:
  - structured-fields
  - review-api
  - backward-compatibility
  - audit-log
dependency_graph:
  requires:
    - shared.models.Criteria (temporal_constraint, numeric_thresholds, conditions JSONB columns)
  provides:
    - ReviewActionRequest.modified_structured_fields API field
    - _apply_review_action() structured field persistence
    - AuditLog.details.schema_version (structured_v1 vs text_v1)
  affects:
    - Phase 23-24 frontend structured editor (consumes this API)
tech_stack:
  added:
    - Dict[str, Any] type for modified_structured_fields in Pydantic model
  patterns:
    - Dual-write pattern (text + structured fields in single request)
    - Optional field pattern (modified_structured_fields defaults to None for backward compat)
    - Schema versioning in audit logs (structured_v1 vs text_v1)
key_files:
  created: []
  modified:
    - services/api-service/src/api_service/reviews.py
    - services/api-service/tests/test_review_api.py
decisions:
  - decision: "Use optional modified_structured_fields field for backward compatibility"
    rationale: "Existing callers sending only modified_text continue to work unchanged"
    alternatives: ["Versioned API endpoints (v1 vs v2)", "Separate structured modify endpoint"]
    chosen: "Optional field"
  - decision: "Add schema_version to AuditLog details rather than new column"
    rationale: "Preserves existing AuditLog schema, enables filtering by schema version in queries"
    alternatives: ["New schema_version column", "Infer from presence of structured fields"]
    chosen: "schema_version in details dict"
  - decision: "Support dual-write pattern (text + structured in same request)"
    rationale: "Enables phased migration where both representations are updated simultaneously"
    alternatives: ["Separate requests for text and structured", "Structured-only (no text)"]
    chosen: "Dual-write"
metrics:
  duration_minutes: 3
  tasks_completed: 2
  files_modified: 2
  tests_added: 9
  tests_passing: 24
  completed_date: "2026-02-13"
---

# Phase 22 Plan 01: Backend API Extension for Structured Field Edits

One-liner: Extended ReviewActionRequest API to accept and persist structured field edits (temporal_constraint, numeric_thresholds, conditions) with full backward compatibility and comprehensive audit logging.

## Objective

Extend the ReviewActionRequest and _apply_review_action() to accept and persist structured field edits (temporal_constraint, numeric_thresholds, conditions) while maintaining full backward compatibility with existing text-only modify actions. This is the backend foundation for v1.5 Structured Criteria Editor.

## Summary of Changes

### 1. Extended ReviewActionRequest (Task 1)
Added `modified_structured_fields: Dict[str, Any] | None = None` to ReviewActionRequest Pydantic model. Field is optional so existing text-only modify calls remain unchanged.

### 2. Updated _apply_review_action() (Task 1)
Modified the function to:
- Capture structured fields (temporal_constraint, numeric_thresholds, conditions) in before_value
- Apply structured field updates when modified_structured_fields is provided
- Capture updated structured fields in after_value
- Support dual-write pattern (both text AND structured fields in single request)

### 3. Enhanced AuditLog (Task 1)
Added `schema_version` to AuditLog.details:
- `"structured_v1"` when modified_structured_fields provided
- `"text_v1"` when text-only modify
Enables filtering and tracking of structured vs text-only edits.

### 4. Comprehensive Integration Tests (Task 2)
Added TestStructuredModify class with 9 tests:
- Backward compatibility (text-only still works)
- Individual field persistence (temporal, thresholds, conditions)
- All fields simultaneously
- Dual-write pattern
- Audit log schema_version tracking
- Before/after value capture for structured changes

## Verification Results

All success criteria met:

✅ **ReviewActionRequest accepts optional modified_structured_fields** without breaking existing callers
✅ **_apply_review_action updates JSONB columns** (temporal_constraint, numeric_thresholds, conditions) from structured fields
✅ **AuditLog includes schema_version** distinguishing structured_v1 from text_v1
✅ **Before/after values capture structured field changes**
✅ **All 24 tests pass** (10 existing + 9 new + 5 other) with zero regressions
✅ **ruff and mypy pass clean**

Test results:
- `uv run pytest services/api-service/tests/test_review_api.py -v`: 24 passed
- `uv run pytest services/api-service/tests/ -v`: 107 passed, 3 pre-existing failures (test_umls_clients.py, unrelated)
- `uv run ruff check services/api-service/`: All checks passed
- Backward compat verified: test_modify_updates_text still passes

## Deviations from Plan

None - plan executed exactly as written.

## Implementation Notes

### Backward Compatibility
The optional `modified_structured_fields` field ensures zero breaking changes:
```python
# Existing code continues to work unchanged
POST /reviews/criteria/{id}/action
{
    "action": "modify",
    "reviewer_id": "user-1",
    "modified_text": "Updated text"  # structured fields remain None
}

# New structured modify
POST /reviews/criteria/{id}/action
{
    "action": "modify",
    "reviewer_id": "user-1",
    "modified_structured_fields": {
        "temporal_constraint": {"duration": "6 months", "relation": "within"}
    }
}

# Dual-write pattern
POST /reviews/criteria/{id}/action
{
    "action": "modify",
    "reviewer_id": "user-1",
    "modified_text": "Age >= 18 years within 6 months of screening",
    "modified_structured_fields": {
        "temporal_constraint": {"duration": "6 months", "relation": "within"},
        "numeric_thresholds": {"value": 18.0, "unit": "years", "comparator": ">="}
    }
}
```

### Audit Trail
The schema_version field enables tracking migration from text-only to structured edits:
```python
# Query all structured edits
SELECT * FROM auditlog WHERE details->>'schema_version' = 'structured_v1';

# Count text-only vs structured edits
SELECT
    details->>'schema_version' as version,
    COUNT(*)
FROM auditlog
WHERE event_type = 'review_action'
GROUP BY version;
```

### JSONB Column Usage
No new database columns required. Uses existing JSONB columns on Criteria model:
- `temporal_constraint: Dict[str, Any] | None` (already exists)
- `numeric_thresholds: Dict[str, Any] | None` (already exists)
- `conditions: Dict[str, Any] | None` (already exists)

The API now provides a write path to populate these fields via the review workflow.

## Integration with Frontend (Phases 23-24)

The frontend structured editor (Phase 23-24) will:
1. Display existing structured fields from CriterionResponse (temporal_constraint, numeric_thresholds, conditions already in response)
2. Allow editing via Cauldron-style field mapping UI
3. Submit changes via `modified_structured_fields` in ReviewActionRequest
4. Support dual-write pattern to keep text and structured representations synchronized

## Next Steps

Phase 22 Plan 02: Entity linking API extension (enable editing UMLS/SNOMED mappings from structured editor).

## Self-Check

Verifying claims:

**Files modified:**
- ✅ services/api-service/src/api_service/reviews.py exists and contains modified_structured_fields
- ✅ services/api-service/tests/test_review_api.py exists and contains TestStructuredModify

**Commits:**
- ✅ 9aa7a20: feat(22-01): add structured field support to ReviewActionRequest
- ✅ 729db03: test(22-01): add comprehensive tests for structured modify API

**Test coverage:**
- ✅ test_text_only_modify_still_works: backward compatibility verified
- ✅ test_structured_modify_temporal_constraint: temporal field persistence
- ✅ test_structured_modify_numeric_thresholds: thresholds field persistence
- ✅ test_structured_modify_conditions: conditions field persistence
- ✅ test_structured_modify_all_fields: all three fields simultaneously
- ✅ test_dual_write_text_and_structured: dual-write pattern verified
- ✅ test_structured_modify_audit_log_schema_version: schema_version structured_v1
- ✅ test_text_only_modify_audit_log_schema_version: schema_version text_v1
- ✅ test_structured_modify_before_after_includes_structured: audit before/after capture

## Self-Check: PASSED

All claims verified. Implementation complete.
