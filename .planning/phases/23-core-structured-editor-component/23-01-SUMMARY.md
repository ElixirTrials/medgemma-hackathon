---
phase: 23-core-structured-editor-component
plan: 01
subsystem: hitl-ui
tags: [ui, structured-editor, react-hook-form, radix-ui, form-validation, phase-23]
dependency_graph:
  requires: [phase-22-backend-data-model-api-extension]
  provides: [structured-field-editor-component]
  affects: [criterion-editing, field-mapping]
tech_stack:
  added: [react-hook-form, radix-ui-select]
  patterns: [discriminated-unions, adaptive-ui, form-state-management]
key_files:
  created:
    - apps/hitl-ui/src/components/structured-editor/types.ts
    - apps/hitl-ui/src/components/structured-editor/constants.ts
    - apps/hitl-ui/src/components/structured-editor/RelationSelect.tsx
    - apps/hitl-ui/src/components/structured-editor/ValueInput.tsx
    - apps/hitl-ui/src/components/structured-editor/StructuredFieldEditor.tsx
  modified: []
decisions:
  - Wrapped inputs in labels for accessibility (biome a11y compliance)
  - Used discriminated union types for relation categories and field values
  - Co-located StandardValueInput, RangeValueInput, TemporalValueInput sub-components in ValueInput.tsx
  - Implemented state cleanup via useEffect to prevent value leak when switching relation categories
metrics:
  duration: 4 min
  tasks_completed: 2
  files_created: 5
  commits: 2
  completed_date: 2026-02-13
---

# Phase 23 Plan 01: Core Structured Editor Component Summary

**Built the StructuredFieldEditor component with entity/relation/value triplet fields, Radix UI relation dropdown with all 10 operators, and adaptive value input that switches between standard/range/temporal based on relation type.**

## What Was Built

Created the core structured field editor component for v1.5 criterion editing with full form validation and adaptive UI.

### Task 1: Types, Constants, and RelationSelect (Commit: 4de9ed9)

**types.ts** - TypeScript type system:
- `RelationOperator` - Literal union of all 10 operators
- `RelationCategory` - Discriminated union tag: 'standard' | 'range' | 'temporal'
- `FieldValue` - Discriminated union: StandardValue | RangeValue | TemporalValue
- `StructuredFieldFormValues` - Form shape with entity/relation/value
- `StructuredFieldEditorProps` - Component props interface

**constants.ts** - Relation configuration:
- `RELATIONS` array with 10 operators mapped to categories
- `RELATION_CATEGORY_MAP` for O(1) category lookup
- `TEMPORAL_UNITS` with days/weeks/months/years options
- `DEFAULT_FIELD_VALUES` for form initialization
- `getDefaultValueForCategory()` helper function

**RelationSelect.tsx** - Radix UI Select wrapper:
- Grouped dropdown with 4 visual sections: Comparison, Range, Temporal, Text Match
- All 10 operators rendered with descriptive labels
- Matches existing form input styling from CriterionCard
- ChevronDown icon for visual consistency

### Task 2: ValueInput and StructuredFieldEditor (Commit: 9319534)

**ValueInput.tsx** - Adaptive value input:
- **StandardValueInput**: Single value + unit (for =, !=, >, >=, <, <=, contains, not_contains)
- **RangeValueInput**: Min + max + unit (for within)
- **TemporalValueInput**: Duration number + unit dropdown (for not_in_last)
- Main component switches on `RelationCategory` to render appropriate sub-input
- All inputs wrapped in labels for accessibility compliance

**StructuredFieldEditor.tsx** - Main triplet editor:
- Entity text input (plain text, UMLS autocomplete in Phase 25)
- Relation dropdown using RelationSelect component
- Adaptive value input conditionally rendered based on relation category
- **State cleanup mechanism**: useEffect detects relation changes and resets value fields when category changes
- react-hook-form with `useForm` + `Controller` for form state
- Save/Cancel buttons matching CriterionCard pattern
- Loader2 spinner when submitting

## Key Implementation Details

### State Management Pattern

Used react-hook-form exclusively for form state (no separate useState calls):
```tsx
const { control, handleSubmit, watch, setValue, register } = useForm<StructuredFieldFormValues>({
    defaultValues: initialValues ?? DEFAULT_FIELD_VALUES,
});
```

### State Cleanup to Prevent Value Leak

Critical useEffect hook prevents stale values when switching relation types:
```tsx
useEffect(() => {
    if (previousRelationRef.current !== currentRelation && currentRelation !== '') {
        const newCategory = RELATION_CATEGORY_MAP[currentRelation as RelationOperator];
        const currentCategory = currentValue.type;

        if (newCategory !== currentCategory) {
            setValue('value', getDefaultValueForCategory(newCategory));
        }
    }
    previousRelationRef.current = currentRelation;
}, [currentRelation, currentValue.type, setValue]);
```

This ensures:
- No leftover min/max values when switching from range to standard
- No leftover duration when switching from temporal to standard
- Clean slate for each relation category

### Discriminated Union Benefits

TypeScript discriminated unions provide compile-time safety:
```tsx
type FieldValue = StandardValue | RangeValue | TemporalValue;

// TypeScript knows which fields are available based on .type
if (value.type === 'range') {
    console.log(value.min, value.max); // ✓ Valid
    console.log(value.duration); // ✗ Compile error
}
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Validation] Added accessibility labels**
- **Found during:** Task 2 biome lint
- **Issue:** Labels not associated with inputs (a11y violation)
- **Fix:** Wrapped inputs inside label elements with span for label text
- **Files modified:** ValueInput.tsx
- **Commit:** 9319534

No other deviations - plan executed exactly as written.

## Verification Results

All verification criteria passed:

1. **TypeScript compilation**: `npx tsc --noEmit` - Zero errors
2. **Biome lint**: `npx biome check src/components/structured-editor/` - Zero errors (after accessibility fix)
3. **File existence**: All 5 files created in structured-editor directory
4. **Vite build**: `npm run build` - Completed successfully, no import errors

## Success Criteria Met

- ✅ EDIT-02: StructuredFieldEditor renders entity/relation/value triplet fields
- ✅ EDIT-03: RelationSelect contains all 10 operators grouped by category
- ✅ EDIT-04: ValueInput adapts between standard/range/temporal based on relation
- ✅ State cleanup: Switching relation category resets value fields
- ✅ No state leak: Clean transitions between relation categories
- ✅ All TypeScript strict mode passing
- ✅ All biome lint passing

## Next Steps

Phase 24 will integrate this component into CriterionCard with:
- Toggle between text edit and structured edit modes
- Dual-write to backend (text + structured fields)
- Evidence linking UI (Phase 26)
- UMLS entity autocomplete (Phase 25)

## Component Usage Example

```tsx
import { StructuredFieldEditor } from './components/structured-editor/StructuredFieldEditor';

<StructuredFieldEditor
    criterionId="crit-123"
    initialValues={{
        entity: 'Age',
        relation: '>=',
        value: { type: 'standard', value: '18', unit: 'years' }
    }}
    onSave={(values) => {
        // values: { entity: string, relation: RelationOperator, value: FieldValue }
        console.log('Saving:', values);
    }}
    onCancel={() => console.log('Cancelled')}
    isSubmitting={false}
/>
```

## Self-Check: PASSED

All files exist:
- ✅ apps/hitl-ui/src/components/structured-editor/types.ts
- ✅ apps/hitl-ui/src/components/structured-editor/constants.ts
- ✅ apps/hitl-ui/src/components/structured-editor/RelationSelect.tsx
- ✅ apps/hitl-ui/src/components/structured-editor/ValueInput.tsx
- ✅ apps/hitl-ui/src/components/structured-editor/StructuredFieldEditor.tsx

All commits exist:
- ✅ 4de9ed9: feat(23-01): add structured editor types, constants, and RelationSelect
- ✅ 9319534: feat(23-01): add ValueInput and StructuredFieldEditor components

Build verification:
- ✅ TypeScript compilation: Zero errors
- ✅ Biome lint: Zero errors
- ✅ Vite build: Successful
