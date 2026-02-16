---
phase: 29-backend-bug-fixes
plan: 02
subsystem: reviews-api-hitl-ui
tags: [bugfix, audit-trail, pending-count, regulatory-compliance]
dependency_graph:
  requires: []
  provides:
    - batch_id-scoped-audit-log-api
    - criteria-level-pending-count-query
    - per-criterion-audit-history-ui
  affects:
    - services/api-service (reviews.py audit log endpoint)
    - apps/hitl-ui (CriterionCard, Dashboard, useReviews hook)
tech_stack:
  added: []
  patterns:
    - SQLModel join query (AuditLog → Criteria)
    - Radix UI Collapsible for audit history
    - TanStack Query hook for pending summary
key_files:
  created:
    - apps/hitl-ui/src/components/CriterionAuditHistory.tsx
  modified:
    - services/api-service/src/api_service/reviews.py
    - apps/hitl-ui/src/hooks/useReviews.ts
    - apps/hitl-ui/src/components/CriterionCard.tsx
    - apps/hitl-ui/src/screens/Dashboard.tsx
decisions:
  - title: Batch status auto-transition to 'reviewed'
    rationale: When all criteria in a batch are reviewed, batch status now auto-updates to 'reviewed' (mixed results), 'approved' (all approved), or 'rejected' (any rejected)
    impact: Batches no longer stay in 'in_progress' indefinitely after review completion
  - title: Audit history collapsed by default
    rationale: Per user decision - keeps criterion cards clean, click to expand "History (N)"
    impact: Audit trail visible but non-intrusive
  - title: Criteria-level pending count query
    rationale: Count unreviewed criteria across active batches instead of batch status
    impact: Dashboard shows accurate pending work (batches with 1/41 reviewed are now counted)
metrics:
  duration_minutes: 4
  tasks_completed: 2
  files_created: 1
  files_modified: 4
  commits: 2
  tests_passing: 117
  completed_at: 2026-02-16T15:59:16Z
---

# Phase 29 Plan 02: Audit Trail Visibility & Pending Count Accuracy Summary

**One-liner:** Per-criterion audit history UI with batch_id filter and criteria-level pending count query replacing batch status query

## What Was Built

**Backend (Task 1):**
- Added `batch_id` query parameter to `/reviews/audit-log` endpoint
- Join query: `AuditLog → Criteria` to filter audit entries by batch_id
- New `/reviews/pending-summary` endpoint returning criteria-level counts
- Batch status auto-transition: `in_progress → reviewed/approved/rejected` when all criteria reviewed
- Terminal states: `approved` (all approved), `rejected` (any rejected), `reviewed` (mixed/modified)

**Frontend (Task 2):**
- `CriterionAuditHistory` component (98 lines) - collapsible audit history per criterion
- Updated `useAuditLog` hook to accept `batchId` parameter
- New `usePendingSummary` hook for dashboard pending counts
- Integrated audit history into `CriterionCard` (collapsed by default, at bottom after action buttons)
- Dashboard displays "N batches (M criteria) pending review" using criteria-level query

## Deviations from Plan

None - plan executed exactly as written.

## Verification Results

**Backend:**
- ✅ `uv run ruff check services/api-service/` - clean
- ✅ `uv run pytest services/api-service/tests/` - 117 passed, 60 warnings (deprecation warnings from dependencies, not code issues)
- ✅ `uv run mypy services/api-service/src/` - 2 pre-existing errors in shared.resilience module (out of scope)
- ✅ Audit log endpoint accepts `batch_id` parameter (verified in reviews.py function signature)
- ✅ Pending summary endpoint returns `pending_batches` and `pending_criteria` fields

**Frontend:**
- ✅ TypeScript compilation succeeds (`cd apps/hitl-ui && npx tsc --noEmit`)
- ✅ CriterionAuditHistory component is 98 lines (under 100-line limit per plan requirement)
- ✅ CriterionCard imports and renders CriterionAuditHistory at bottom
- ✅ useReviews.ts exports `useAuditLog` with `batchId` parameter and `usePendingSummary` hook
- ✅ Dashboard displays criteria-level pending count via `usePendingSummary` hook

## Key Implementation Details

**Audit log batch_id filter (BUGF-02):**
- Backend joins `AuditLog → Criteria` on `target_id == id` when `batch_id` is provided
- Filter applies to BOTH count query and data query (ensures correct pagination)
- Backward compatible: when `batch_id` is not provided, existing `target_type`/`target_id` filters work unchanged
- Frontend hook adds `batchId` to query key for cache isolation

**Pending count criteria-level query (BUGF-03):**
- Counts criteria where `review_status IS NULL` joined with batches in `['pending_review', 'in_progress']` status
- Separate count for distinct batches with ANY unreviewed criteria
- Dashboard message format: "N batches (M criteria) pending review"
- Replaces old batch-level status query that missed partially reviewed batches

**Batch status auto-transition:**
- `pending_review → in_progress` on first review submitted (unchanged)
- `in_progress → approved` when all criteria reviewed AND none rejected
- `in_progress → rejected` when all criteria reviewed AND any rejected
- `in_progress → reviewed` when all criteria reviewed AND mixed results (approved + modified, or modified only)

**Audit history UI:**
- Radix UI Collapsible component (already in project dependencies)
- Collapsed by default (user decision: "collapsed by default")
- Action summary only: "Approved by X at Y" (no full before/after diff per user decision)
- Rationale displayed in italic if present
- Timestamp formatted with `toLocaleString()` for human-readable dates
- Actor ID cleaned up (email username extracted for display)

## Files Changed

**Backend:**
- `services/api-service/src/api_service/reviews.py` (+114 lines, -12 lines)
  - Added `PendingSummaryResponse` model
  - Added `get_pending_summary()` endpoint
  - Updated `list_audit_log()` with `batch_id` parameter and join logic
  - Updated `_update_batch_status()` with 'reviewed' terminal state

**Frontend:**
- `apps/hitl-ui/src/components/CriterionAuditHistory.tsx` (new file, 98 lines)
  - Collapsible audit history component
  - Formats action, actor, timestamp
  - Displays rationale if present
- `apps/hitl-ui/src/components/CriterionCard.tsx` (+4 lines)
  - Import CriterionAuditHistory
  - Render at bottom after action buttons
- `apps/hitl-ui/src/hooks/useReviews.ts` (+17 lines)
  - Added `batchId` parameter to useAuditLog
  - Added `PendingSummary` interface
  - Added `usePendingSummary` hook
- `apps/hitl-ui/src/screens/Dashboard.tsx` (+8 lines, -5 lines)
  - Import usePendingSummary instead of useBatchList
  - Display criteria-level pending count

## Success Criteria Met

- ✅ Audit trail entries visible per-criterion on the Review page (collapsed by default, expandable)
- ✅ Dashboard pending count accurately reflects unreviewed criteria across all active batches
- ✅ Partially reviewed batches (e.g., 1/41 criteria done) are counted as pending
- ✅ Batch status auto-transitions when all criteria are reviewed
- ✅ All backend tests pass (117 passed)
- ✅ No TypeScript errors

## Known Limitations

- No pagination in per-criterion audit history (shows first 20 entries only) - acceptable for current use case
- No display of per-batch progress (e.g., "12/15 reviewed") in batch list - deferred to future UX enhancement
- 'reviewed' batch status is new and not yet used in batch list filtering - may need UI update to show reviewed batches separately

## Next Steps

- Phase 29 Plan 01: Fix grounding confidence bug (BUGF-01) - MedGemma agentic loop failures
- E2E verification: Upload protocol → extract → ground → review cycle to verify audit trail visibility in production
- Consider adding batch list filter for 'reviewed' status (separate from 'approved'/'rejected')

## Self-Check: PASSED

✅ All created files exist:
- apps/hitl-ui/src/components/CriterionAuditHistory.tsx (98 lines)

✅ All commits exist:
- f12890c: feat(29-02): add batch_id audit filter and criteria-level pending count
- 3e31b58: feat(29-02): add per-criterion audit history UI and criteria-level pending count

✅ All tests pass:
- Backend: 117 passed
- Frontend: TypeScript compilation clean

✅ Key functionality verified:
- Audit log API accepts batch_id parameter
- Pending summary endpoint returns criteria-level counts
- CriterionAuditHistory component integrated into CriterionCard
- Dashboard displays "N batches (M criteria) pending review"
