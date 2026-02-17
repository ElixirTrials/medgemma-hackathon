---
phase: 32-entity-model-ground-node-multi-code-display
plan: 03
subsystem: hitl-ui-entity-display
tags: [terminology, badges, autocomplete, entity-card, react, typescript, fastapi]
dependency_graph:
  requires:
    - apps/hitl-ui/src/hooks/useEntities.ts (EntityResponse interface)
    - services/api-service/src/api_service/entities.py (EntityResponse model)
    - libs/shared/src/shared/models.py (Entity model with Phase 32 multi-code fields)
    - /api/terminology/{system}/search endpoints (from Plan 32-01)
  provides:
    - Color-coded TerminologyBadge pills for RxNorm/ICD-10/SNOMED/LOINC/HPO/UMLS
    - ErrorBadge for grounding_error display
    - useTerminologySearch hook with 300ms debounce for all 6 systems
    - TerminologyCombobox reusable per-system autocomplete
    - EntityCard with unified multi-code badge section + per-system edit mode
    - EntityResponse and EntityActionRequest with full multi-code field support
  affects:
    - EntityCard display (replaces old SNOMED/UMLS badge sections)
    - Entity modify workflow (now supports rxnorm/icd10/loinc/hpo modifications)
    - ProtocolDetail retry button text
tech_stack:
  added: []
  patterns:
    - Radix Popover + cmdk Command reused from UmlsCombobox pattern
    - Per-entity-type system routing (Medication→rxnorm, Condition→icd10+snomed, etc.)
    - getattr() fallback for optional Entity fields to maintain backward compatibility
    - Helper extraction (_entity_codes_snapshot, _apply_modify_codes) to satisfy ruff C901
key_files:
  created:
    - apps/hitl-ui/src/components/TerminologyBadge.tsx
    - apps/hitl-ui/src/components/TerminologyCombobox.tsx
    - apps/hitl-ui/src/hooks/useTerminologySearch.ts
  modified:
    - apps/hitl-ui/src/components/EntityCard.tsx
    - apps/hitl-ui/src/hooks/useEntities.ts
    - apps/hitl-ui/src/screens/ProtocolDetail.tsx
    - services/api-service/src/api_service/entities.py
decisions:
  - "getattr() fallback for rxnorm_code/icd10_code/loinc_code/hpo_code in _entity_to_response: Entity model already has these fields but using getattr() prevents AttributeError if running against older DB schema"
  - "UMLS combobox in edit mode uses display (preferred_term) as input value, sets code into editCui — matches existing UmlsCombobox pattern"
  - "getRelevantSystems: Procedure entity type defaults to snomed+umls (no dedicated system); all entity types always show UMLS"
  - "_entity_codes_snapshot and _apply_modify_codes extracted from _apply_entity_action to satisfy ruff C901 complexity < 10"
metrics:
  duration: "3 min"
  completed_date: "2026-02-17"
  tasks_completed: 2
  files_modified: 4
  files_created: 3
---

# Phase 32 Plan 03: Multi-Code Display and Per-System Editing Summary

Color-coded TerminologyBadge pills for all 6 terminology systems (RxNorm/ICD-10/SNOMED/LOINC/HPO/UMLS) on EntityCard, per-system TerminologyCombobox autocomplete in edit mode, ErrorBadge for grounding failures, and "Retry Processing" button text.

## What Was Built

### Task 1: TerminologyBadge, TerminologyCombobox, useTerminologySearch

**TerminologyBadge.tsx** — Color-coded pill badge component for all 6 terminology systems:
- `SYSTEM_COLORS` mapping: rxnorm=blue, icd10=orange, snomed=green, loinc=purple, hpo=teal, umls=indigo
- `SYSTEM_LABELS` mapping for display prefix (RxNorm, ICD-10, SNOMED, LOINC, HPO, CUI)
- Optional `display` prop for preferred term shown in parentheses
- `ErrorBadge` component: red background, "Failed: {errorReason}" text

**useTerminologySearch.ts** — Generic hook for all 6 terminology systems:
- 300ms debounce on query input, 3-char minimum
- Calls `/api/terminology/{system}/search?q={query}`
- 5-minute staleTime cache, 10-minute gcTime, 1 retry
- Returns `{ results: TerminologySearchResult[], isLoading, isError }`
- `TerminologySearchResult` interface: `{ code, display, system, semantic_type?, confidence }`

**TerminologyCombobox.tsx** — Reusable per-system autocomplete:
- Props: `system`, `value`, `onSelect`, `onChange`, `placeholder?`
- Uses Radix Popover + cmdk Command (same pattern as UmlsCombobox)
- Shows system-specific label in loading/empty states ("Searching RxNorm...")
- Displays `code` + `display` in results; `semantic_type` if present
- Internal `useTerminologySearch(system, inputValue)` handles debouncing

**Commit:** `e6d7f1a`

### Task 2: EntityCard Multi-Code Badges, Per-System Editing, Backend Update

**entities.py** — Backend EntityResponse and EntityActionRequest updated:
- `EntityResponse` adds: `rxnorm_code`, `icd10_code`, `loinc_code`, `hpo_code`, `grounding_system`, `grounding_error`
- `EntityActionRequest` adds: `modified_rxnorm_code`, `modified_icd10_code`, `modified_loinc_code`, `modified_hpo_code`
- `_entity_to_response()` uses `getattr()` fallback for backward compatibility
- `_entity_codes_snapshot()` and `_apply_modify_codes()` extracted as helpers (ruff C901 fix)
- Audit trail before/after values now include all 7 code fields

**useEntities.ts** — TypeScript interfaces updated with multi-code fields on both `EntityResponse` and `EntityActionRequest`.

**EntityCard.tsx** — Major display and edit mode update:
- Read mode: unified flex-wrap badge row shows all non-null codes as TerminologyBadge pills
- UMLS CUI retains existing link to uts.nlm.nih.gov with ExternalLink icon
- `grounding_error` → ErrorBadge (red pill)
- "Not grounded" gray badge when no codes and no error
- Edit mode: `getRelevantSystems(entityType)` determines which system comboboxes to show
  - Medication → rxnorm + umls
  - Condition → icd10 + snomed + umls
  - Lab_Value → loinc + umls
  - Biomarker → hpo + umls
  - Default (Procedure) → snomed + umls
- UMLS TerminologyCombobox always shown; manual CUI/SNOMED text input retained as fallback
- `handleModifySave` includes all 7 code fields; `handleModifyCancel` resets all edit states

**ProtocolDetail.tsx:**
- "Retry Extraction" → "Retry Processing" (reflects checkpoint-based resume)
- Added `processing: 'bg-blue-100 text-blue-800'` to STATUS_COLORS and STATUS_LABELS

**Commit:** `683de97`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed ruff C901 complexity in _apply_entity_action**
- **Found during:** Task 2 (ruff check)
- **Issue:** Adding 4 new `if body.modified_*` branches pushed cyclomatic complexity to 11 > 10
- **Fix:** Extracted `_entity_codes_snapshot()` (returns dict snapshot of all code fields) and `_apply_modify_codes()` (applies all modified fields) from `_apply_entity_action`. Main function drops to complexity 4.
- **Files modified:** services/api-service/src/api_service/entities.py
- **Commit:** 683de97 (included in task commit)

## Self-Check: PASSED

- FOUND: apps/hitl-ui/src/components/TerminologyBadge.tsx
- FOUND: apps/hitl-ui/src/components/TerminologyCombobox.tsx
- FOUND: apps/hitl-ui/src/hooks/useTerminologySearch.ts
- FOUND: commit e6d7f1a (feat(32-03): create TerminologyBadge, TerminologyCombobox, and useTerminologySearch)
- FOUND: commit 683de97 (feat(32-03): multi-code badges on EntityCard, per-system editing, retry button text)
- BUILD: npm run build succeeds (1.77s)
- TYPECHECK: npx tsc --noEmit passes (0 errors)
- RUFF: ruff check entities.py passes (0 errors)
