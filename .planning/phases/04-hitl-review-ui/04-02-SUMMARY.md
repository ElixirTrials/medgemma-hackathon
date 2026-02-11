---
phase: 04-hitl-review-ui
plan: 02
subsystem: ui
tags: [react, react-pdf, react-resizable-panels, tanstack-query, tailwind, lucide-react, review-workflow]

# Dependency graph
requires:
  - phase: 04-hitl-review-ui
    provides: "Review API endpoints and TanStack Query hooks (useBatchList, useBatchCriteria, useReviewAction, usePdfUrl, useAuditLog)"
  - phase: 02-protocol-upload-storage
    provides: "GCS signed URL generation for PDF viewing, ProtocolList/ProtocolDetail UI patterns"
provides:
  - "ReviewQueue screen with paginated batch list, status filters, and progress indicators"
  - "ReviewPage split-screen with PDF viewer (left) and criteria review panel (right) using react-resizable-panels"
  - "PdfViewer component using react-pdf with page navigation"
  - "CriterionCard component with confidence badges, review status, approve/reject/modify actions, and inline editing"
  - "Route wiring for /reviews and /reviews/:batchId"
  - "Dashboard live pending review count with navigation to review queue"
affects: [05-grounding-umls-medgemma]

# Tech tracking
tech-stack:
  added: [react-pdf]
  patterns: ["Split-screen review layout with react-resizable-panels", "Confidence-based sorting and visual highlighting for low-confidence items", "Inline editing mode in criterion cards for modify action"]

key-files:
  created:
    - apps/hitl-ui/src/components/PdfViewer.tsx
    - apps/hitl-ui/src/components/CriterionCard.tsx
    - apps/hitl-ui/src/screens/ReviewQueue.tsx
    - apps/hitl-ui/src/screens/ReviewPage.tsx
  modified:
    - apps/hitl-ui/src/App.tsx
    - apps/hitl-ui/src/screens/Dashboard.tsx
    - apps/hitl-ui/package.json

key-decisions:
  - "Used useBatchList with client-side filter to get batch info in ReviewPage (no single-batch endpoint needed)"
  - "Confidence badge thresholds: >=0.85 high (green), >=0.7 medium (yellow), <0.7 low (red) with percentage display"
  - "Default sort is confidence ascending (lowest first) to surface items needing most attention"

patterns-established:
  - "Split-screen pattern: PanelGroup horizontal with PanelResizeHandle for PDF + review layout"
  - "Confidence badge pattern: three-tier color coding with configurable thresholds"
  - "Inline edit mode pattern: toggle between display and editable form with save/cancel"

# Metrics
duration: 4min
completed: 2026-02-11
---

# Phase 4 Plan 2: Criteria Review UI Summary

**Split-screen review interface with react-pdf PDF viewer, confidence-badged criterion cards with approve/reject/modify actions, resizable panels, and review queue with batch progress tracking**

## Performance

- **Duration:** 4 min
- **Started:** 2026-02-11T13:08:00Z
- **Completed:** 2026-02-11T13:11:49Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- Split-screen review page with resizable PDF viewer (left) and criteria cards panel (right) using react-resizable-panels
- PdfViewer renders PDFs from signed GCS URLs with page navigation (prev/next with page number display)
- CriterionCard displays confidence badge (high/medium/low), criteria type, assertion status, review status, and action buttons
- Inline editing mode for modify action with text, type, and category fields
- Low-confidence items (<0.7) highlighted with red left border
- Review queue with paginated batch list, status filter chips, and progress bars
- Dashboard shows live pending review count from API with navigation to review queue
- Collapsible audit trail panel in review page

## Task Commits

Each task was committed atomically:

1. **Task 1: Install react-pdf, create PdfViewer and CriterionCard components** - `e32bd37` (feat)
2. **Task 2: Create ReviewQueue and ReviewPage screens with route wiring** - `f2dd062` (feat)

## Files Created/Modified
- `apps/hitl-ui/src/components/PdfViewer.tsx` - PDF viewer with react-pdf, page navigation, loading/error states
- `apps/hitl-ui/src/components/CriterionCard.tsx` - Criterion card with confidence badge, review actions, inline editing
- `apps/hitl-ui/src/screens/ReviewQueue.tsx` - Paginated batch list with status filters and progress bars
- `apps/hitl-ui/src/screens/ReviewPage.tsx` - Split-screen review with PDF viewer, criteria cards, sort controls, audit trail
- `apps/hitl-ui/src/App.tsx` - Added /reviews and /reviews/:batchId routes
- `apps/hitl-ui/src/screens/Dashboard.tsx` - Live pending review count with Review Criteria button
- `apps/hitl-ui/package.json` - Added react-pdf dependency

## Decisions Made
- Used `useBatchList` with client-side filter to retrieve batch info in ReviewPage, avoiding need for a dedicated single-batch endpoint
- Confidence badge thresholds set at 0.85 (high/green) and 0.7 (medium/yellow) with percentage display in badge text
- Default sort is confidence ascending (lowest first) per REQ-04.3 to surface items needing the most review attention first

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Full HITL review UI is complete (Phase 4 done)
- Review workflow: upload protocol -> extraction -> review queue -> split-screen review -> approve/reject/modify
- Ready for Phase 5 (UMLS grounding and MedGemma integration)

---
*Phase: 04-hitl-review-ui*
*Completed: 2026-02-11*
