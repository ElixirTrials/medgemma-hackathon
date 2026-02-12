---
phase: 07-production-hardening
plan: 01
subsystem: pipeline-reliability
tags: [dead-letter, retry, status-enum, error-handling]
completed: 2026-02-12
duration_minutes: 6

dependency_graph:
  requires: [06-02]
  provides: [protocol-status-enum, dead-letter-detection, retry-endpoint, protocol-archival]
  affects: [outbox-processor, protocols-api, protocol-model]

tech_stack:
  added:
    - ProtocolStatus enum (9 states)
    - MAX_RETRIES constant (3)
    - col() wrapper for SQLModel in_() queries
  patterns:
    - Dead-letter queue pattern for exhausted retries
    - Lazy archival on access (7-day cutoff)
    - Retry endpoint for manual recovery

key_files:
  created:
    - services/api-service/alembic/versions/07_01_protocol_status_enum.py
  modified:
    - libs/shared/src/shared/models.py
    - libs/events-py/src/events_py/outbox.py
    - services/api-service/src/api_service/protocols.py

decisions:
  - desc: "ProtocolStatus enum stored as string in DB (not PostgreSQL enum type)"
    rationale: "Avoid migration complexity; application-level validation sufficient"
  - desc: "error_reason field stores human-readable message, metadata_.error stores technical details"
    rationale: "Separation of concerns for user-facing vs debug information"
  - desc: "Failed events re-polled via status.in_(['pending', 'failed'])"
    rationale: "Enables retry logic without separate polling mechanism"
  - desc: "Lazy archival triggered on get_protocol access"
    rationale: "Avoid periodic cron job; archival on-demand is sufficient"
  - desc: "Used col() wrapper for mypy compatibility with in_() operator"
    rationale: "Matches existing pattern in api-service (entities.py, reviews.py, search.py)"

metrics:
  tasks_completed: 2
  files_modified: 3
  files_created: 1
  commits: 3
  tests_passing: 101
---

# Phase 07 Plan 01: Protocol Status State Machine & Dead-Letter Handling Summary

Protocol status enum with 9 states, dead-letter detection after 3 retries, manual retry endpoint, and 7-day archival for failed protocols.

## Overview

This plan establishes the foundation for Phase 7 production hardening by implementing a proper protocol status state machine with dead-letter handling. The ProtocolStatus enum distinguishes between normal processing states (uploaded, extracting, grounding, pending_review, complete) and failure states (extraction_failed, grounding_failed, dead_letter, archived). The outbox processor now caps retries at 3 failures before transitioning protocols to dead_letter status with error metadata. A new POST /protocols/{id}/retry endpoint allows users to manually retry failed protocols, and dead-letter protocols are automatically archived after 7 days of inactivity.

## Tasks Completed

| Task | Description | Commit | Files |
|------|-------------|--------|-------|
| 1 | Add ProtocolStatus enum and error_reason field | 0a87d89 | models.py, 07_01_protocol_status_enum.py |
| 2 | Add dead-letter handling and retry endpoint | 8330057 | outbox.py, protocols.py |
| Fix | Add col() wrapper and fix migration docstring | 076dc4a | outbox.py, 07_01_protocol_status_enum.py |

## What Changed

### ProtocolStatus Enum (Task 1)

**libs/shared/src/shared/models.py:**
- Added `ProtocolStatus(str, Enum)` with 9 values:
  - `UPLOADED`: Initial state after upload
  - `EXTRACTING`: Extraction in progress
  - `EXTRACTION_FAILED`: Extraction failed (retryable)
  - `GROUNDING`: Grounding in progress
  - `GROUNDING_FAILED`: Grounding failed (retryable)
  - `PENDING_REVIEW`: Awaiting human review
  - `COMPLETE`: Processing complete
  - `DEAD_LETTER`: Max retries exhausted (requires manual intervention)
  - `ARCHIVED`: Dead-letter protocol archived after 7 days
- Updated `Protocol.status` default to `ProtocolStatus.UPLOADED`
- Added `error_reason: str | None` field for human-readable error messages
- Stored as string in DB (not PostgreSQL enum type) for simplicity

**services/api-service/alembic/versions/07_01_protocol_status_enum.py:**
- Created migration to add `error_reason` column to `protocol` table
- Nullable column (existing rows default to None)
- Depends on `47530bf7f47c` (GIN index migration)

### Dead-Letter Handling (Task 2)

**libs/events-py/src/events_py/outbox.py:**
- Added `MAX_RETRIES = 3` constant at module level
- Updated poll query to include failed events: `.where(col(OutboxEvent.status).in_(["pending", "failed"]))`
- In exception handler:
  - Increment `event.retry_count`
  - If `retry_count >= MAX_RETRIES`: transition to "dead_letter" status
  - If protocol event: update `protocol.status = "dead_letter"`, set `error_reason`, add metadata
  - Otherwise: transition to "failed" status for retry
- Used `col()` wrapper for mypy compatibility (matches existing pattern in api-service)

**services/api-service/src/api_service/protocols.py:**
- Added `POST /protocols/{id}/retry` endpoint:
  - Validates protocol is in retryable state (extraction_failed, grounding_failed, dead_letter)
  - Resets `protocol.status = "uploaded"`, clears `error_reason` and `metadata_.error`
  - Creates new PROTOCOL_UPLOADED outbox event to re-trigger pipeline
  - Returns `{"status": "retry_queued", "protocol_id": protocol_id}`
- Added `_check_dead_letter_archival()` helper:
  - Checks if dead_letter protocol hasn't been updated in 7+ days
  - Transitions status to "archived" if cutoff exceeded
  - Called from `get_protocol()` detail endpoint (lazy archival)
- Updated `list_protocols()` to exclude archived protocols from default view
  - When `status` query param is None: `.where(Protocol.status != "archived")`
  - Archived protocols still accessible via explicit `?status=archived` filter

## Deviations from Plan

None - plan executed exactly as written. All verification checks passed.

## Verification Results

1. ProtocolStatus enum importable with 9 values: PASSED
2. Protocol.status defaults to ProtocolStatus.UPLOADED: PASSED
3. Alembic migration applied cleanly: PASSED
4. Outbox processor has MAX_RETRIES = 3: PASSED
5. Failed events re-polled for retry: PASSED
6. Retry endpoint exists and validates states: PASSED
7. Dead-letter archival logic integrated: PASSED
8. `uv run ruff check .`: PASSED
9. `uv run mypy .`: PASSED
10. `uv run pytest services/api-service/tests/ -x`: PASSED (101 tests)

## Success Criteria

- [x] ProtocolStatus enum with 9 values exists in shared models
- [x] Protocol model uses enum default and has error_reason field
- [x] Outbox processor caps retries at 3 and sets dead_letter status
- [x] Failed outbox events are re-polled for retry
- [x] Retry endpoint resets protocol status and creates new outbox event
- [x] Dead-letter protocols auto-archive after 7 days on access
- [x] All existing tests pass

## Technical Details

### Status State Machine

```
uploaded → extracting → extraction_failed (retryable)
         ↓
    grounding → grounding_failed (retryable)
         ↓
pending_review → complete

extraction_failed/grounding_failed → dead_letter (after 3 retries) → archived (after 7 days)
```

### Error Metadata Structure

When a protocol reaches dead_letter status, the metadata field contains:

```python
protocol.metadata_ = {
    **protocol.metadata_,
    "error": {
        "category": "pipeline_failed",
        "reason": "Maximum retries exceeded",
        "retry_count": 3,
    },
}
```

### Retry Endpoint Behavior

**Valid retryable states:** extraction_failed, grounding_failed, dead_letter

**Reset behavior:**
- status → "uploaded"
- error_reason → None
- metadata_.error → removed
- New PROTOCOL_UPLOADED event created

**Returns 400 if:**
- Protocol not in retryable state (e.g., already complete, or currently processing)

**Returns 404 if:**
- Protocol ID not found

## Key Decisions

1. **ProtocolStatus stored as string, not PostgreSQL enum**
   - Avoids ALTER TYPE complexity in migrations
   - Application-level validation via Python enum is sufficient
   - Easier to add new states in future plans

2. **error_reason vs metadata_.error separation**
   - `error_reason`: Human-readable message ("Maximum retries exceeded")
   - `metadata_.error`: Technical details (category, retry_count, stack traces)
   - Matches frontend display requirements (user-facing vs debug info)

3. **Lazy archival on access**
   - Triggered in `get_protocol()` detail endpoint
   - No periodic cron job needed
   - Acceptable trade-off: archival happens when user views protocol detail
   - Alternative (rejected): Background job adds infrastructure complexity

4. **col() wrapper for in_() operator**
   - Required for mypy type checking compatibility
   - Matches existing pattern in api-service (entities.py, reviews.py, search.py)
   - SQLModel's `status.in_()` triggers mypy "str has no attribute in_" error
   - `col(OutboxEvent.status).in_()` resolves the type issue

## Self-Check: PASSED

**Created files verified:**
- [FOUND] services/api-service/alembic/versions/07_01_protocol_status_enum.py

**Modified files verified:**
- [FOUND] libs/shared/src/shared/models.py
- [FOUND] libs/events-py/src/events_py/outbox.py
- [FOUND] services/api-service/src/api_service/protocols.py

**Commits verified:**
- [FOUND] 0a87d89: feat(07-01): add ProtocolStatus enum and error_reason field
- [FOUND] 8330057: feat(07-01): add dead-letter handling and retry endpoint
- [FOUND] 076dc4a: fix(07-01): add col() wrapper for mypy and fix migration docstring

## Next Steps

Plan 07-01 complete. Ready for Plan 07-02 (circuit breakers and retry for external service calls).

**Recommendations for Plan 07-02:**
- Wrap GCS operations (upload URL, download, metadata) with retries + circuit breakers
- Wrap UMLS API calls with retries + circuit breakers
- Wrap Gemini/Vertex AI calls with retries + circuit breakers
- Consider shared resilience module with pre-configured breakers
