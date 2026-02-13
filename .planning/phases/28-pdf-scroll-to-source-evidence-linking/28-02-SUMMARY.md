---
phase: 28-pdf-scroll-to-source-evidence-linking
plan: 02
subsystem: ui
tags: [react, pdf, react-pdf, evidence-linking, click-to-scroll, text-highlighting]

# Dependency graph
requires:
  - phase: 28-01
    provides: page_number data flowing from extraction to API response
provides:
  - Click-to-scroll evidence linking from criterion cards to PDF viewer
  - Text highlighting in PDF viewer using react-pdf customTextRenderer
  - Graceful degradation when page_number is null
  - Toggle selection behavior for criterion cards
affects: [29-field-mappings-display, v1.6-corrections]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Optional prop pattern for backward compatibility (targetPage, highlightText)"
    - "useEffect-based page navigation in PdfViewer"
    - "customTextRenderer for PDF text highlighting with HTML mark tags"
    - "Parent state management for cross-component interaction (activeCriterion)"

key-files:
  created: []
  modified:
    - apps/hitl-ui/src/components/PdfViewer.tsx
    - apps/hitl-ui/src/components/CriterionCard.tsx
    - apps/hitl-ui/src/screens/ReviewPage.tsx

key-decisions:
  - "Use first 40 chars of criterion text for highlight matching (full criteria text can be very long)"
  - "Case-insensitive text matching for highlight robustness"
  - "Toggle selection pattern (clicking same criterion deselects it)"
  - "Only show click affordance (cursor-pointer, hover) when page_number exists"
  - "Page badge placement in CriterionCard header row alongside other badges"

patterns-established:
  - "Pattern 1: Optional navigation props (targetPage/highlightText) enable click-to-scroll without breaking existing PdfViewer usage"
  - "Pattern 2: Parent component (ReviewPage) manages shared state (activeCriterion) between sibling components (CriterionCard, PdfViewer)"
  - "Pattern 3: Graceful degradation via conditional rendering/behavior based on data availability (page_number)"

# Metrics
duration: 8min
completed: 2026-02-13
---

# Phase 28 Plan 02: Evidence Linking UI Summary

**Click-to-scroll evidence linking with text highlighting using react-pdf customTextRenderer and graceful degradation for missing page numbers**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-13T17:00:00Z
- **Completed:** 2026-02-13T17:08:00Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments
- PdfViewer navigates to source page via optional targetPage prop with useEffect-based page change
- Text highlighting in PDF using customTextRenderer with HTML mark tags (yellow highlight)
- CriterionCard shows page badge and click handler only when page_number exists
- ReviewPage manages activeCriterion state to wire click events between CriterionCard and PdfViewer
- Toggle selection behavior (clicking same criterion deselects it)
- Graceful degradation when page_number is null (no click affordance, no errors)

## Task Commits

Each task was committed atomically:

1. **Task 1: Enhance PdfViewer with targetPage prop and text highlighting** - `2744872` (feat)
2. **Task 2: Add click handler to CriterionCard and wire through ReviewPage** - `62667a9` (feat)
3. **Task 3: Verify evidence linking end-to-end** - Human verification checkpoint (approved)

## Files Created/Modified
- `apps/hitl-ui/src/components/PdfViewer.tsx` - Added targetPage and highlightText props, useEffect for page navigation, customTextRenderer for text highlighting with mark tags, flashKey for visual feedback
- `apps/hitl-ui/src/components/CriterionCard.tsx` - Added onCriterionClick callback prop, isActive prop, page badge display, click handler on criterion text with conditional cursor/hover based on page_number presence
- `apps/hitl-ui/src/screens/ReviewPage.tsx` - Added activeCriterion state, handleCriterionClick toggle handler, wired targetPage/highlightText to PdfViewer, passed onCriterionClick/isActive to CriterionCard

## Decisions Made
- **First 40 chars for highlight matching:** Full criterion text can be very long (>100 chars), so we use first 40 chars of criterion.text for PDF text matching to improve match accuracy
- **Case-insensitive matching:** Robustness for text extraction variations between Gemini's criterion extraction and react-pdf's text layer
- **Toggle selection pattern:** Clicking the same criterion twice deselects it and clears the highlight, providing intuitive UX
- **Conditional click affordance:** Only show cursor-pointer and hover state when page_number exists, avoiding false affordances for criteria without source page data
- **Page badge in header row:** Placed "p.N" badge alongside confidence/type badges for visual consistency

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Evidence linking feature complete and verified. Ready for:
- Phase 29: Display saved field_mappings in CriterionCard non-edit mode
- Phase 29: Populate StructuredFieldEditor initialValues from saved field_mappings
- v1.6 Correction Workflow: Editor polish and gold-standard corpus building

**Current System Gaps (v1.5 remaining):**
- No display of field_mappings in non-edit mode (saved mappings not shown as badges)
- No initialValues population from saved field_mappings (editor always starts with 1 empty mapping)

## Self-Check: PASSED

**Files verified:**
- FOUND: apps/hitl-ui/src/components/PdfViewer.tsx
- FOUND: apps/hitl-ui/src/components/CriterionCard.tsx
- FOUND: apps/hitl-ui/src/screens/ReviewPage.tsx

**Commits verified:**
- FOUND: 2744872 (Task 1: PdfViewer enhancements)
- FOUND: 62667a9 (Task 2: CriterionCard click handler)

---
*Phase: 28-pdf-scroll-to-source-evidence-linking*
*Completed: 2026-02-13*
