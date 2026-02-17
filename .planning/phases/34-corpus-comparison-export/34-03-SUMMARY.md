---
phase: 34-corpus-comparison-export
plan: 03
subsystem: ui
tags: [react, tanstack-query, radix-ui, lucide-react, tailwind]

# Dependency graph
requires:
  - phase: 34-01
    provides: GET /reviews/batches/{batch_id}/metrics endpoint with modification breakdown
  - phase: 34-02
    provides: POST /reviews/criteria/{id}/rerun, GET /reviews/batch-compare, GET /protocols/{id}/batches
provides:
  - useCorpus.ts TanStack Query hooks for metrics, batch timeline, batch comparison, criterion re-run
  - AgreementMetrics component with 3-layer progressive disclosure
  - BatchTimeline component with comparison selector
  - BatchCompareView component with aggregate stats and per-criterion diff
  - CriterionRerunPanel Radix Dialog with 2-step feedback → comparison flow
  - ProtocolDetail updated with Review Metrics + Batch History collapsible sections
  - CriterionCard with "Correct with AI" button wired to CriterionRerunPanel
affects: [corpus-comparison-export-complete, hitl-ui-criterion-review, frontend-metrics-display]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Radix Collapsible for 3-layer progressive disclosure (summary → breakdown → per-criterion)"
    - "Radix Dialog for 2-step AI correction flow (feedback input → side-by-side comparison)"
    - "useBatchCompare enabled only when 2 batch IDs provided — lazy load on user action"
    - "BatchTimeline manages max-2 checkbox selection state locally, resets on selection change"
    - "CriterionRerunPanel reset() clears mutation state when dialog closes or cancel pressed"

key-files:
  created:
    - apps/hitl-ui/src/hooks/useCorpus.ts
    - apps/hitl-ui/src/components/AgreementMetrics.tsx
    - apps/hitl-ui/src/components/BatchTimeline.tsx
    - apps/hitl-ui/src/components/BatchCompareView.tsx
    - apps/hitl-ui/src/components/CriterionRerunPanel.tsx
  modified:
    - apps/hitl-ui/src/screens/ProtocolDetail.tsx
    - apps/hitl-ui/src/components/CriterionCard.tsx

key-decisions:
  - "No new npm dependencies needed — all Radix components + lucide-react already installed"
  - "useAllProtocolBatches is a NEW hook separate from useBatchesByProtocol (per research anti-pattern: don't reuse review-workflow hook for timeline)"
  - "useCriterionRerun has no cache invalidation — read-only proposal pattern; reviewer commits via existing useReviewAction"
  - "BatchCompareView sorts rows: changed/added/removed first, unchanged collapsed at bottom for scannability"
  - "CriterionRerunPanel onAccept builds ReviewActionRequest with comment='AI-assisted correction with reviewer feedback' for audit trail"
  - "Review Metrics section defaults open, Batch History defaults closed to avoid overwhelming the page"

patterns-established:
  - "AgreementMetrics: detailsOpen state keyed by label string for independent nested collapsible control"
  - "BatchTimeline: max-2 selection replaces oldest with newest when limit reached (not disables further clicks)"
  - "CriterionRerunPanel: two-step Dialog flow controlled by rerunMutation.isSuccess state, not separate step counter"
  - "fieldChanged helper compares JSON.stringify of field values to detect structural changes in nested objects"

# Metrics
duration: 3min
completed: 2026-02-17
---

# Phase 34 Plan 03: Corpus Frontend Components Summary

**Radix-powered AgreementMetrics with 3-layer progressive disclosure, lazy BatchCompareView, and per-criterion AI correction Dialog wired into ProtocolDetail and CriterionCard**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-17T10:42:52Z
- **Completed:** 2026-02-17T10:45:57Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- `useCorpus.ts` provides 4 TanStack Query hooks matching all Phase 34 backend endpoints with correct query keys
- `AgreementMetrics` shows approve/reject/modify grid with percentage bars, expandable modification breakdown by schema version, and nested per-criterion lists filterable by review status
- `BatchTimeline` lists all batches (including archived with visual indicator), checkbox selection capped at 2, triggers lazy `BatchCompareView` only on user click
- `BatchCompareView` shows aggregate stats (added/removed/changed/unchanged) + per-criterion rows with color-coded borders and match score badges
- `CriterionRerunPanel` is a Radix Dialog with feedback textarea (Step 1) transitioning to side-by-side original vs revised fields with change highlighting (Step 2) — accept triggers `useReviewAction` with audit trail comment
- `ProtocolDetail` gets two new Radix Collapsible sections: Review Metrics (default open) + Batch History (default closed)
- `CriterionCard` gets "Correct with AI" button (Wand2 icon, purple variant) visible in read mode

## Task Commits

Each task was committed atomically:

1. **Task 1: TanStack Query hooks, AgreementMetrics, BatchTimeline, BatchCompareView, ProtocolDetail wiring** - `0481e54` (feat)
2. **Task 2: CriterionRerunPanel dialog and CriterionCard "Correct with AI" button** - `28595ce` (feat)

**Plan metadata:** (docs commit to follow)

## Files Created/Modified

- `apps/hitl-ui/src/hooks/useCorpus.ts` - useBatchMetrics, useAllProtocolBatches, useBatchCompare, useCriterionRerun with TypeScript interfaces
- `apps/hitl-ui/src/components/AgreementMetrics.tsx` - 3-layer progressive disclosure with Radix Collapsible
- `apps/hitl-ui/src/components/BatchTimeline.tsx` - Chronological batch list with comparison selector
- `apps/hitl-ui/src/components/BatchCompareView.tsx` - Side-by-side batch comparison table
- `apps/hitl-ui/src/components/CriterionRerunPanel.tsx` - AI re-run feedback dialog with Radix Dialog
- `apps/hitl-ui/src/screens/ProtocolDetail.tsx` - Added Review Metrics + Batch History collapsible sections
- `apps/hitl-ui/src/components/CriterionCard.tsx` - Added "Correct with AI" button + CriterionRerunPanel wiring

## Decisions Made

- No new npm dependencies: all Radix components (@radix-ui/react-dialog, @radix-ui/react-collapsible) and lucide-react icons already in package.json
- `useAllProtocolBatches` is deliberately separate from `useBatchesByProtocol` — the review workflow hook excludes archived batches; timeline hook uses different endpoint (`/protocols/{id}/batches`) that returns ALL batches
- `useCriterionRerun` has no `onSuccess` cache invalidation — the mutation is a read-only AI proposal; the DB write happens via `useReviewAction` on accept
- BatchCompareView renders changed/added/removed rows first, unchanged at bottom — scannability over completeness
- Review Metrics open by default (researchers want overview immediately), Batch History closed by default (secondary workflow)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - TypeScript was clean on first check for both tasks.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 34 corpus comparison frontend is complete: all 3 phases (01 backend integrity/metrics, 02 backend re-run/compare/timeline, 03 frontend components) are done
- Researchers can view review statistics with progressive disclosure drill-down on ProtocolDetail
- Batch history with comparison is available when the Batch History section is expanded
- Per-criterion AI correction is available from any CriterionCard in review mode
- All data loads lazily — comparison data only fetched when user selects 2 batches and clicks Compare

---
*Phase: 34-corpus-comparison-export*
*Completed: 2026-02-17*
