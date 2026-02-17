---
phase: 33-re-extraction-tooling-review-protection
plan: 02
subsystem: ui
tags: [react, radix-ui, tanstack-query, lucide-react, alertdialog, re-extraction, protocol-detail]

# Dependency graph
requires:
  - phase: 33-re-extraction-tooling-review-protection
    plan: 01
    provides: POST /protocols/{id}/re-extract endpoint with batch archiving and 409 guard
  - phase: 30-ux-polish-editor-pre-loading
    provides: ProtocolDetail screen, useProtocols/useReviews hooks, Button component

provides:
  - useReExtractProtocol mutation hook (POST /protocols/{id}/re-extract, invalidates protocols + review-batches)
  - ReExtractButton component with Radix AlertDialog confirmation modal
  - Re-extraction processing banner (Loader2 spinner when status=extracting)
  - Review New Criteria link shown when status transitions to pending_review
  - useProtocol accepts optional UseQueryOptions for refetchInterval polling
  - refetchInterval=5000 for auto-refresh on ProtocolDetail during processing

affects: [33-03, hitl-ui, protocol-detail-ui, review-batches-ui]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Radix AlertDialog imported as namespace (* as AlertDialog) and composed inline without a pre-built wrapper component
    - useProtocol with optional UseQueryOptions spread — allows callers to pass refetchInterval without requiring a separate hook variant
    - RE_EXTRACT_ALLOWED_STATUSES Set for O(1) status gate check (pending_review, complete, extraction_failed, grounding_failed, dead_letter)

key-files:
  created: []
  modified:
    - apps/hitl-ui/src/hooks/useProtocols.ts
    - apps/hitl-ui/src/screens/ProtocolDetail.tsx

key-decisions:
  - "Radix AlertDialog used directly (namespace import) rather than creating a wrapped component — single-use modal, no reuse needed"
  - "refetchInterval=5000 (constant) instead of query-state-conditional — simpler TypeScript, TanStack Query deduplicates; polling stops naturally when component unmounts"
  - "Review New Criteria shown only when status=pending_review; all other states show generic Review Criteria — distinguishes fresh re-extraction result from existing batch"
  - "useProtocol extended with Partial<UseQueryOptions> spread — allows ProtocolDetail to add refetchInterval without forking the hook"

patterns-established:
  - "AlertDialog inline composition: import * as AlertDialog from @radix-ui/react-alert-dialog and compose Root/Trigger/Portal/Overlay/Content/Title/Description/Cancel/Action directly"
  - "Status gate constant: RE_EXTRACT_ALLOWED_STATUSES Set — enumerate allowed states positively (not block states) for clear intent"

# Metrics
duration: 8min
completed: 2026-02-17
---

# Phase 33 Plan 02: Re-Extraction Frontend UI Summary

**Re-extraction button with Radix AlertDialog confirmation modal, processing spinner, and polling-based review link on ProtocolDetail using the 33-01 backend endpoint**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-02-17T00:22:00Z
- **Completed:** 2026-02-17T00:30:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- `useReExtractProtocol` mutation hook added to `useProtocols.ts` — POSTs to `/protocols/{id}/re-extract`, invalidates `protocols` and `review-batches` query caches on success
- `ReExtractButton` component with Radix AlertDialog: title "Re-extract criteria?", description warning about batch archiving and review inheritance preservation, Cancel and Re-extract action buttons
- Button disabled for in-progress protocol statuses (uploaded, extracting, grounding) and while mutation is pending
- Processing spinner banner shown specifically when `status === 'extracting'` (with Loader2 animate-spin)
- "Review New Criteria (N)" link shown in actions when `status === 'pending_review'` after re-extraction triggers
- `useProtocol` extended with `Partial<UseQueryOptions>` spread so ProtocolDetail can pass `refetchInterval=5000` for auto-polling during processing states

## Task Commits

Each task was committed atomically:

1. **Task 1: useReExtractProtocol mutation hook** - `ef81291` (feat)
2. **Task 2: Re-extraction button, confirmation modal, and processing states in ProtocolDetail** - `64698a0` (feat)

**Plan metadata:** (pending docs commit)

## Files Created/Modified

- `apps/hitl-ui/src/hooks/useProtocols.ts` - Added `ReExtractResponse` interface, `useReExtractProtocol` mutation hook, extended `useProtocol` with optional `UseQueryOptions`
- `apps/hitl-ui/src/screens/ProtocolDetail.tsx` - Added `ReExtractButton` component with AlertDialog, processing banners, "Review New Criteria" link, refetchInterval polling

## Decisions Made

- **Radix AlertDialog namespace import:** No pre-built component wrapper exists in `apps/hitl-ui/src/components/ui/` (only `Button.tsx` present). Used direct namespace import `import * as AlertDialog from '@radix-ui/react-alert-dialog'` and composed inline — single-use modal, no need to create a generic wrapper component.
- **refetchInterval as constant 5000:** Used `refetchInterval: 5000` (always-on) rather than a conditional callback. TanStack Query deduplicates refetches; background refetching is disabled via `refetchIntervalInBackground: false`. Simpler TypeScript than the query-state callback pattern which required `any` typing.
- **Review New Criteria vs Review Criteria:** When `status === 'pending_review'`, show "Review New Criteria" to signal the re-extraction result is ready. All other statuses show generic "Review Criteria" — preserves existing behavior for first-time extraction.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] useProtocol signature extension needed for refetchInterval**
- **Found during:** Task 2 (ProtocolDetail processing state display)
- **Issue:** Plan specified adding `refetchInterval` to the `useProtocol` call but the hook only accepted `id: string` — passing a second options argument caused TS2554 "Expected 1 arguments, but got 2"
- **Fix:** Extended `useProtocol` signature to accept `Partial<UseQueryOptions<Protocol, Error>>` as optional second parameter, spread into `useQuery` after base options. Added `UseQueryOptions` import from `@tanstack/react-query`.
- **Files modified:** `apps/hitl-ui/src/hooks/useProtocols.ts`
- **Verification:** `npx tsc --noEmit` passes with no errors
- **Committed in:** `64698a0` (Task 2 commit)

**2. [Rule 1 - Bug] Removed unused variables declared but never read**
- **Found during:** Task 2 verification (TypeScript strict check)
- **Issue:** `isProcessing` placeholder variable and `isActivelyProcessing`/`PROCESSING_STATUSES` constants were declared but never read — TS6133 errors
- **Fix:** Removed all three unused declarations; refetchInterval simplified to constant avoids needing the PROCESSING_STATUSES set
- **Files modified:** `apps/hitl-ui/src/screens/ProtocolDetail.tsx`
- **Verification:** `npx tsc --noEmit` exits with no output (clean)
- **Committed in:** `64698a0` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (2 bugs)
**Impact on plan:** Both fixes required for TypeScript compilation. No scope changes — the behavior matches the plan spec exactly.

## Issues Encountered

None beyond the TypeScript compilation errors documented above as deviations.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Frontend re-extraction UI is complete — researchers can trigger re-extraction from ProtocolDetail and see processing state and review link
- Phase 33 is functionally complete (backend 33-01 + frontend 33-02)
- The `_apply_review_inheritance` hook in `api-service/protocols.py` is implemented but only called if `archived_reviewed_criteria` is present in the outbox payload — the extraction-service persist node needs to pass this through (noted in 33-01 SUMMARY as next-phase work)
- No blockers for Phase 34

---
*Phase: 33-re-extraction-tooling-review-protection*
*Completed: 2026-02-17*
