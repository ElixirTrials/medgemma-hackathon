---
phase: 30-ux-polish-editor-pre-loading
plan: 01
subsystem: ui
tags: [react, tailwind, use-debounce, useMemo, lucide-react, radix-ui-tabs]

# Dependency graph
requires:
  - phase: 29-backend-bug-fixes
    provides: criteria with review_status field, audit trail, correct pending count
provides:
  - Review status colored left borders on CriterionCard (green/red/blue/yellow)
  - Sticky search/filter bar with debounced text search and 3 dropdowns
  - Criteria grouped into Inclusion/Exclusion/To Be Sorted sections with progress counts
  - Pending criteria sorted before reviewed within each section
  - Client-side filtering with useMemo on loaded criteria
affects: [31-pipeline-consolidation, 32-extraction-upgrade]

# Tech tracking
tech-stack:
  added: [use-debounce]
  patterns:
    - useMemo for client-side filter + grouping (avoids server round-trips)
    - useDebounce(searchText, 300) for text search performance
    - for...of instead of forEach (biome noForEach compliance)

key-files:
  created: []
  modified:
    - apps/hitl-ui/src/components/CriterionCard.tsx
    - apps/hitl-ui/src/screens/ReviewPage.tsx
    - apps/hitl-ui/package.json

key-decisions:
  - "Status border supersedes low-confidence border — review_status carries more actionable info; ConfidenceBadge already shows confidence level"
  - "Client-side filtering via useMemo — instant UX on loaded data, no server round-trips for filter changes"
  - "Fixed API sort (confidence asc) — server sort removed from UI since section grouping + pending-first sort replaces it"
  - "Tabs.Content className removed (empty string) — filter bar needs full-width sticky behavior"

patterns-established:
  - "Filter bar pattern: sticky top-0 z-10 bg-card border-b, inside overflow-auto container for sticky scroll behavior"
  - "Section grouping pattern: uncategorized → inclusion → exclusion, each with pending-first sort"
  - "countReviewed helper: list.filter(c => c.review_status !== null).length for progress headers"

# Metrics
duration: 2min
completed: 2026-02-17
---

# Phase 30 Plan 01: UX Polish — Review Status Borders and Filter Bar Summary

**Review status colored left borders (green/red/blue/yellow) on criteria cards plus sticky filter bar with debounced search, 3 dropdowns, and section grouping with Inclusion/Exclusion/To Be Sorted headers showing reviewed/total progress counts.**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-17T06:54:33Z
- **Completed:** 2026-02-17T06:56:33Z
- **Tasks:** 2
- **Files modified:** 3 (CriterionCard.tsx, ReviewPage.tsx, package.json)

## Accomplishments
- CriterionCard now shows colored `border-l-4` based on `review_status`: green=approved, red=rejected, blue=modified, yellow=pending (null) — replaces the less-informative low-confidence red border
- Sticky search/filter bar with 300ms debounced text search + dropdowns for Status (all/pending/reviewed), Type (all/inclusion/exclusion), and Confidence (all/high/medium/low)
- Criteria grouped into "To Be Sorted" / "Inclusion Criteria" / "Exclusion Criteria" sections; bold headers show `(N/M reviewed)` progress counts; pending criteria sorted before reviewed within each section
- Replaced server-driven sort controls with client-side useMemo filtering — instant response on already-loaded data

## Task Commits

Each task was committed atomically:

1. **Task 1: Review status border colors and use-debounce install** - `5d71ffe` (feat)
2. **Task 2: Sticky search/filter bar and section sorting with headers** - `0e3252b` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified
- `apps/hitl-ui/src/components/CriterionCard.tsx` - border-l-4 with status-based color (green/red/blue/yellow); removed isLowConfidence
- `apps/hitl-ui/src/screens/ReviewPage.tsx` - sticky filter bar, useMemo filtering, section grouping with progress headers, removed SORT_OPTIONS and sort UI
- `apps/hitl-ui/package.json` + `package-lock.json` - added use-debounce

## Decisions Made
- **Status border supersedes low-confidence border.** Review status (approved/rejected/modified/pending) carries more actionable information than the confidence level, which is already shown via ConfidenceBadge. The `border-l-4` class is always applied; color varies by status.
- **Client-side filtering via useMemo.** Avoids server round-trips on filter changes; all criteria are already loaded for the batch. The API still fetches with a fixed `confidence asc` sort.
- **Server sort controls removed from UI.** SORT_OPTIONS constant and sortBy/sortOrder state removed (the sort controls div was replaced by the filter bar). The API call uses fixed `confidence` + `asc` defaults.
- **Tabs.Content className set to empty string.** The filter bar needs full-width sticky positioning; padding moved to the `<div className="p-4 space-y-6">` inner wrapper.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Removed unused Button import after deleting sort controls**
- **Found during:** Task 2 (TypeScript verification)
- **Issue:** `Button` import caused `TS6133: 'Button' is declared but its value is never read` after removing sort controls
- **Fix:** Removed the `import { Button } from '../components/ui/Button'` line
- **Files modified:** `apps/hitl-ui/src/screens/ReviewPage.tsx`
- **Verification:** `npx tsc --noEmit` — zero errors
- **Committed in:** `0e3252b` (Task 2 commit)

**2. [Rule 1 - Bug] Converted forEach to for...of for biome compliance**
- **Found during:** Task 2 (biome lint check)
- **Issue:** `lint/complexity/noForEach` — biome prefers `for...of` over `forEach` for arrays
- **Fix:** Replaced `filteredCriteria.forEach((c) => {...})` with `for (const c of filteredCriteria) {...}`
- **Files modified:** `apps/hitl-ui/src/screens/ReviewPage.tsx`
- **Verification:** `npx biome check src/screens/ReviewPage.tsx` — zero errors
- **Committed in:** `0e3252b` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (both Rule 1 - Bug)
**Impact on plan:** Both fixes necessary for zero-error build. No scope creep.

## Issues Encountered
- Pre-existing biome errors in other files (`CriterionCard.tsx` a11y, `App.tsx` import type, etc.) were confirmed pre-existing via `git stash` test and deferred per scope boundary rules.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Review page now has professional visual hierarchy: colored status borders + section grouping + filter bar
- Phase 30 Plan 02 (if any) can build on filteredCriteria / section grouping patterns
- Pre-existing biome warnings in CriterionCard.tsx (a11y/useKeyWithClickEvents, noArrayIndexKey) should be addressed in a dedicated cleanup phase

## Self-Check: PASSED

- FOUND: apps/hitl-ui/src/components/CriterionCard.tsx
- FOUND: apps/hitl-ui/src/screens/ReviewPage.tsx
- FOUND: .planning/phases/30-ux-polish-editor-pre-loading/30-01-SUMMARY.md
- FOUND: commit 5d71ffe (Task 1)
- FOUND: commit 0e3252b (Task 2)

---
*Phase: 30-ux-polish-editor-pre-loading*
*Completed: 2026-02-17*
