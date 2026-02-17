---
phase: 30-ux-polish-editor-pre-loading
plan: 02
subsystem: ui
tags: [react, radix-ui, react-hook-form, typescript, hitl-ui]

# Dependency graph
requires:
  - phase: 30-01
    provides: Status border CriterionCard, filter bar, section grouping
  - phase: 29
    provides: field_mappings stored in conditions JSONB via structured editor modify action
provides:
  - RejectDialog component with multi-select predefined reject reasons + optional free-text
  - FieldMappingBadges component showing saved field_mappings as clickable read-mode rows
  - reject_reasons field on ReviewActionRequest interface
  - EDIT-01 verification: buildInitialValues pre-loads from conditions.field_mappings (Priority 1)
affects: [31, 32, future-review-analytics]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Dialog pattern: Radix Dialog.Root + Portal + Overlay + Content for modal interactions"
    - "Form pattern: react-hook-form Controller for controlled checkbox arrays (multi-select)"
    - "Read-mode badge pattern: null return when no data, clickable rows with AND connectors"
    - "Priority-based initialValues: saved field_mappings > AI-extracted data in buildInitialValues"

key-files:
  created:
    - apps/hitl-ui/src/components/RejectDialog.tsx
    - apps/hitl-ui/src/components/FieldMappingBadges.tsx
  modified:
    - apps/hitl-ui/src/components/CriterionCard.tsx
    - apps/hitl-ui/src/hooks/useReviews.ts

key-decisions:
  - "Reject flow uses dialog with predefined checkboxes (not free-text only) for audit compliance"
  - "Approve remains one-click with no rationale prompt per user decision"
  - "FieldMappingBadges returns null when no field_mappings exist (no empty state rendered)"
  - "AND connector shown as static read-mode display; actual AND/OR logic editable in structured editor"
  - "Index key used for field_mappings array (biome-ignored) — mappings have no stable unique id"

patterns-established:
  - "Radix Dialog used directly (not wrapped) for one-off modal dialogs"
  - "Controller+checkbox pattern for multi-select form groups with string[] state"
  - "formatMappingValue helper centralizes range/temporal/standard value display logic"

# Metrics
duration: 2min
completed: 2026-02-17
---

# Phase 30 Plan 02: Reject Dialog and Field Mapping Badges Summary

**RejectDialog with 5 predefined audit-ready reject reasons + FieldMappingBadges showing saved field_mappings as clickable entity/relation/value rows with AND connectors in read mode**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-17T07:03:59Z
- **Completed:** 2026-02-17T07:06:33Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- Created `RejectDialog.tsx` — Radix Dialog with react-hook-form Controller for 5 predefined reject reason checkboxes (multi-select) plus optional free-text comment; destructive submit fires reject action with reasons + comment
- Created `FieldMappingBadges.tsx` — displays saved `conditions.field_mappings` as clickable entity/relation/value rows with AND connector between them; returns null when empty; clicking opens structured editor
- Verified EDIT-01: `buildInitialValues` already correctly pre-loads saved field_mappings from `criterion.conditions.field_mappings` as Priority 1 (before AI-extracted fallback)
- Updated `ReviewActionRequest` interface with `reject_reasons?: string[]` for audit compliance

## Task Commits

1. **Task 1: RejectDialog + CriterionCard reject integration** - `90e09c7` (feat)
2. **Task 2: FieldMappingBadges read-mode display** - `74c5473` (feat)
3. **Task 2 (format fix): biome format RejectDialog** - `981229a` (chore)

## Files Created/Modified

- `apps/hitl-ui/src/components/RejectDialog.tsx` — Radix Dialog with predefined reject checkboxes, optional comment textarea, and submit/cancel actions
- `apps/hitl-ui/src/components/FieldMappingBadges.tsx` — Read-mode display of field_mappings with AND connectors; clicking opens structured editor
- `apps/hitl-ui/src/components/CriterionCard.tsx` — Integrated RejectDialog (state + handlers) and FieldMappingBadges (after criterion text in read mode)
- `apps/hitl-ui/src/hooks/useReviews.ts` — Added `reject_reasons?: string[]` to `ReviewActionRequest` interface

## Decisions Made

- Reject dialog uses predefined checkboxes (not freetext) for structured audit trail — supports compliance reporting by reason code
- Approve stays one-click, no dialog per original user decision
- FieldMappingBadges returns null when no mappings (no "No mappings" empty state — cleaner read mode)
- AND connector is static in read mode; full AND/OR editing happens in the structured editor via useFieldArray

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed biome formatting violations in RejectDialog.tsx**
- **Found during:** Task 2 (biome check run)
- **Issue:** Biome formatter reported line-length formatting issues for checkbox onChange handler and Button props
- **Fix:** Ran `biome format --write` on RejectDialog.tsx to apply auto-format
- **Files modified:** `apps/hitl-ui/src/components/RejectDialog.tsx`
- **Verification:** `npx biome check src/components/FieldMappingBadges.tsx src/components/RejectDialog.tsx` — zero errors
- **Committed in:** `981229a` (chore)

---

**Total deviations:** 1 auto-fixed (Rule 3 - blocking lint issue)
**Impact on plan:** Biome format auto-applied, no logic changes. Pre-existing biome issues in CriterionCard.tsx (noArrayIndexKey for threshold display, useKeyWithClickEvents for page_number click) are out-of-scope pre-existing issues.

## Issues Encountered

None — all tasks executed cleanly. TypeScript zero errors throughout.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Reject dialog and field mapping badges fully integrated into CriterionCard read mode
- EDIT-01 (editor pre-loading) confirmed working via buildInitialValues Priority 1 path
- Phase 30 UX Polish complete — all 2 plans done
- Pre-existing biome issues in CriterionCard.tsx (threshold index key, p click handler a11y) logged for potential future cleanup

---
*Phase: 30-ux-polish-editor-pre-loading*
*Completed: 2026-02-17*
