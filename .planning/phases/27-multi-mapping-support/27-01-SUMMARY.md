---
phase: 27-multi-mapping-support
plan: 01
subsystem: hitl-ui, api-service
tags: [multi-mapping, structured-editor, field-arrays, phase-27]
dependency_graph:
  requires: [phase-24-criterioncard-integration, phase-23-structured-editor-component]
  provides: [multi-mapping-ui, field-mappings-array-storage]
  affects: [structured-criteria-editing, review-workflow]
tech_stack:
  added: [useFieldArray from react-hook-form]
  patterns: [dynamic-form-arrays, per-mapping-cards, minimum-1-enforcement]
key_files:
  created: []
  modified:
    - apps/hitl-ui/src/components/structured-editor/StructuredFieldEditor.tsx
    - apps/hitl-ui/src/components/structured-editor/types.ts
    - apps/hitl-ui/src/components/structured-editor/constants.ts
    - apps/hitl-ui/src/hooks/useReviews.ts
    - apps/hitl-ui/src/components/CriterionCard.tsx
    - services/api-service/src/api_service/reviews.py
decisions:
  - decision: "Use useFieldArray for dynamic mapping management"
    rationale: "React Hook Form's useFieldArray provides robust array handling with built-in form state management, validation, and minimal re-renders"
    alternatives: ["Manual array state with useState", "Separate forms per mapping"]
    chosen: "useFieldArray"
  - decision: "Store field_mappings in conditions JSONB column"
    rationale: "Conditions is the general-purpose JSONB field for structured criteria data; keeps multi-mapping data separate from legacy temporal/threshold fields"
    alternatives: ["Create new JSONB column", "Store in numeric_thresholds"]
    chosen: "conditions JSONB"
  - decision: "Minimum 1 mapping enforcement via disabled remove button"
    rationale: "UI constraint (disabled button) is clearer than allowing removal then showing validation error"
    alternatives: ["Allow removal with validation error", "Hide remove button when 1 mapping"]
    chosen: "Disabled button"
  - decision: "v1.5-multi schema_version for audit logs"
    rationale: "Enables querying and filtering multi-mapping edits separately from single-field edits for analytics and debugging"
    alternatives: ["Reuse structured_v1", "No schema version distinction"]
    chosen: "v1.5-multi"
metrics:
  duration: 6 min
  tasks_completed: 2
  files_modified: 6
  commits: 2
  completed_date: 2026-02-13
---

# Phase 27 Plan 01: Multi-Mapping Support Summary

**Multi-mapping UI with useFieldArray, backend array storage, and full round-trip persistence for complex eligibility criteria like "18-65 years AND BMI <30".**

## What Was Built

Extended the StructuredFieldEditor (Phase 23) to support multiple field mappings per criterion using react-hook-form's useFieldArray, with backend storage in the conditions JSONB field and v1.5-multi schema versioning for audit logs.

### Task 1: Frontend Multi-Mapping with useFieldArray (Commit: f9e0070)

**StructuredFieldEditor.tsx** - Refactored to dynamic mapping array:
- Changed form structure from single `{ entity, relation, value }` to `{ mappings: FieldMapping[] }`
- Integrated `useFieldArray({ control, name: 'mappings' })` for array management
- Each mapping rendered in a visual card with border (`border rounded-lg p-3 mb-3`)
- Card header shows "Mapping 1", "Mapping 2", etc. with trash icon remove button in top-right
- Remove button disabled when `fields.length === 1` (minimum 1 mapping enforcement)
- Each mapping has independent entity input, relation dropdown, and adaptive value input
- State cleanup via useEffect tracks previous relations per mapping index to reset value on category change
- "Add Mapping" button at bottom with Plus icon calls `append(DEFAULT_MAPPING)`
- Validation: "Add Mapping" disabled if last mapping's entity is empty, shows inline message "Complete the current mapping before adding another"

**types.ts** - Updated TypeScript interfaces:
- Added `FieldMapping` interface: `{ entity: string; relation: RelationOperator | ''; value: FieldValue }`
- Changed `StructuredFieldFormValues` to `{ mappings: FieldMapping[] }`
- Editor props unchanged (onSave signature updated to accept mappings array)

**constants.ts** - New default values:
- `DEFAULT_MAPPING`: Single empty mapping object
- `DEFAULT_FIELD_VALUES`: `{ mappings: [DEFAULT_MAPPING] }` (initializes with 1 empty mapping)

**useReviews.ts** - Extended ReviewActionRequest type:
- Added `FieldMapping` interface for type safety
- Updated `modified_structured_fields` to support `{ field_mappings?: FieldMapping[]; [key: string]: unknown }`

**CriterionCard.tsx** - Updated handleStructuredSave:
- Changed signature from `(values: { entity, relation, value })` to `(values: { mappings: Array<...> })`
- Wraps mappings in `{ field_mappings: values.mappings }` before sending to backend

**UI behavior:**
- Default: 1 empty mapping card on open
- Click "Add Mapping" → appends 2nd card (if first has entity filled)
- Click remove on 2nd mapping → leaves 1 mapping, remove button disabled
- Form submission → `{ field_mappings: [{ entity, relation, value }, ...] }` array sent to backend

### Task 2: Backend field_mappings Array Storage (Commit: e12dd5d)

**reviews.py** - Extended `_apply_review_action`:
- Added field_mappings storage: `if "field_mappings" in sf: criterion.conditions = {"field_mappings": sf["field_mappings"]}`
- Stores full array in conditions JSONB column (overwrites any existing conditions data when field_mappings present)
- Preserves array structure for exact frontend reconstruction

**reviews.py** - Enhanced audit log schema versioning:
```python
has_field_mappings = (
    body.modified_structured_fields
    and "field_mappings" in body.modified_structured_fields
)
if has_field_mappings:
    schema_version = "v1.5-multi"
elif body.modified_structured_fields:
    schema_version = "structured_v1"
else:
    schema_version = "text_v1"
```
- v1.5-multi schema_version distinguishes multi-mapping edits for analytics/debugging

**Backward compatibility:**
- Pre-v1.5 modify actions (no modified_structured_fields) → unchanged behavior
- Single-element field_mappings array → stored same as multi-element (no special casing)
- Text-only modify → schema_version = "text_v1" (existing behavior preserved)

**CriterionResponse** - Already supports JSONB return:
- `conditions: Dict[str, Any] | None` field returns nested structures including field_mappings
- Frontend can read `criterion.conditions.field_mappings` after save/refresh

## Deviations from Plan

None - plan executed exactly as written. Both tasks completed successfully with no architectural changes, bugs, or blocking issues discovered.

## Verification Results

All success criteria met:

✅ **MULTI-01 (Add Mapping)**: "Add Mapping" button appends new mapping card with empty entity/relation/value fields
✅ **MULTI-02 (Remove with min enforcement)**: Remove button on each card removes it; disabled when only 1 mapping remains
✅ **MULTI-03 (Independent fields)**: Each mapping card has own entity input, relation dropdown, value input via useFieldArray indexed fields
✅ **MULTI-04 (Backend round-trip)**: Backend stores field_mappings as array in conditions JSONB, returns in API response, survives page refresh

**TypeScript compilation:**
```bash
cd apps/hitl-ui && npx tsc --noEmit
# → Zero errors
```

**Python linting:**
```bash
uv run ruff check services/api-service/
# → All checks passed!
```

**Python type checking:**
```bash
uv run mypy services/api-service/src/api_service/reviews.py
# → Success: no issues found in 1 source file
```

**Backend tests:**
```bash
uv run pytest services/api-service/tests/test_review_api.py -v
# → 24 passed (all review API tests pass, including structured modify tests)
```

## Key Implementation Details

### useFieldArray Pattern

Dynamic mapping management with automatic re-renders:
```tsx
const { fields, append, remove } = useFieldArray({
    control,
    name: 'mappings',
});

// fields array has stable IDs for React keys
{fields.map((field, index) => (
    <div key={field.id}>
        <Controller name={`mappings.${index}.entity`} ... />
        <Controller name={`mappings.${index}.relation`} ... />
        <Controller name={`mappings.${index}.value`} ... />
    </div>
))}
```

### Per-Mapping State Cleanup

Relation category changes reset value per mapping:
```tsx
useEffect(() => {
    allMappings.forEach((mapping, index) => {
        const currentRelation = mapping.relation;
        const previousRelation = previousRelationsRef.current[index] ?? '';

        if (previousRelation !== currentRelation && currentRelation !== '') {
            const newCategory = RELATION_CATEGORY_MAP[currentRelation];
            const currentCategory = mapping.value.type;

            if (newCategory !== currentCategory) {
                setValue(`mappings.${index}.value`, getDefaultValueForCategory(newCategory));
            }
        }

        previousRelationsRef.current[index] = currentRelation;
    });
}, [allMappings, setValue]);
```

Prevents state leak: Switching mapping 2 from "within" (range) to ">=" (standard) resets mapping 2's value without affecting mapping 1.

### Minimum 1 Mapping Validation

UI-level constraint via disabled button:
```tsx
<Button
    onClick={() => remove(index)}
    disabled={fields.length === 1 || isSubmitting}
>
    <Trash2 className="h-4 w-4 text-red-600" />
</Button>
```

Clearer UX than allowing removal then showing validation error. Always at least 1 mapping card present.

### Add Mapping Validation

Prevents empty mapping accumulation:
```tsx
const canAddMapping = () => {
    if (fields.length === 0) return true;
    const lastMapping = allMappings[allMappings.length - 1];
    return lastMapping && lastMapping.entity.trim() !== '';
};

<Button onClick={handleAddMapping} disabled={!canAddMapping()}>
    <Plus className="h-4 w-4 mr-1" />
    Add Mapping
</Button>
{!canAddMapping() && fields.length > 0 && (
    <p className="text-xs text-muted-foreground mt-1">
        Complete the current mapping before adding another
    </p>
)}
```

### Backend Storage Pattern

Field_mappings overwrites conditions JSONB:
```python
if "field_mappings" in sf:
    # Store field_mappings array in conditions JSONB field
    criterion.conditions = {"field_mappings": sf["field_mappings"]}
```

**Note:** This overwrites any existing conditions data. If a criterion has legacy conditions (from pre-v1.5), those are replaced when field_mappings is saved. This is acceptable because:
1. Conditions field was previously unused for single-mapping edits (Phase 23-24 used temporal_constraint and numeric_thresholds)
2. Multi-mapping is the new canonical structured field representation
3. Frontend can migrate legacy data to field_mappings on edit (future phase)

### Audit Log Schema Versioning

Three schema versions:
- `"text_v1"`: Text-only modify (modified_text/type/category)
- `"structured_v1"`: Single-mapping structured edit (temporal_constraint, numeric_thresholds, conditions - Phase 22-24)
- `"v1.5-multi"`: Multi-mapping structured edit (field_mappings array - Phase 27+)

Enables analytics queries:
```sql
SELECT * FROM audit_log
WHERE details->>'schema_version' = 'v1.5-multi';
```

## Integration Notes

### Data Flow Summary

```
User clicks "Modify Fields"
  ↓
CriterionCard sets editMode='structured'
  ↓
StructuredFieldEditor renders with 1 empty mapping (DEFAULT_FIELD_VALUES)
  ↓
User fills mapping 1 (entity: "Age", relation: ">=", value: "18")
User clicks "Add Mapping" → mapping 2 appears
User fills mapping 2 (entity: "BMI", relation: "<", value: "30")
User clicks Save
  ↓
handleSubmit calls onSave({ mappings: [{ entity: "Age", ... }, { entity: "BMI", ... }] })
  ↓
handleStructuredSave wraps: { field_mappings: values.mappings }
  ↓
onAction(criterionId, { action: 'modify', modified_structured_fields: { field_mappings: [...] } })
  ↓
useReviewAction POST /reviews/criteria/{id}/action
  ↓
Backend _apply_review_action stores criterion.conditions = { field_mappings: [...] }
  ↓
AuditLog created with schema_version = "v1.5-multi"
  ↓
Response returns updated Criterion with conditions.field_mappings
  ↓
TanStack Query invalidates batch-criteria → refetch
  ↓
CriterionCard re-renders with criterion.conditions.field_mappings = [{ entity: "Age", ... }, { entity: "BMI", ... }]
  ↓
(Future phase) Next edit: StructuredFieldEditor initialValues populates from criterion.conditions.field_mappings
```

### Future: Initial Values from Saved Mappings

Phase 27 focuses on create/save flow. Next phase (28 or later) will add:
- Read criterion.conditions.field_mappings on edit
- Pass as initialValues to StructuredFieldEditor
- useFieldArray initializes with saved mappings instead of DEFAULT_FIELD_VALUES

Example (not implemented yet):
```tsx
const initialMappings = criterion.conditions?.field_mappings ?? [DEFAULT_MAPPING];
<StructuredFieldEditor
    criterionId={criterion.id}
    initialValues={{ mappings: initialMappings }}
    onSave={handleStructuredSave}
    onCancel={() => setEditMode('none')}
    isSubmitting={isSubmitting}
/>
```

### Display After Save

Currently (Phase 27) no UI display of field_mappings in non-edit mode. Criterion.conditions.field_mappings is stored and returned but not rendered. Future phase will add:
- Multi-mapping badge display in CriterionCard (similar to existing temporal/threshold badges)
- Format: "Age >= 18 AND BMI < 30" or individual badge per mapping

## Self-Check: PASSED

All files modified:
- ✅ apps/hitl-ui/src/components/structured-editor/StructuredFieldEditor.tsx (useFieldArray multi-mapping)
- ✅ apps/hitl-ui/src/components/structured-editor/types.ts (FieldMapping, mappings array)
- ✅ apps/hitl-ui/src/components/structured-editor/constants.ts (DEFAULT_MAPPING)
- ✅ apps/hitl-ui/src/hooks/useReviews.ts (field_mappings in ReviewActionRequest)
- ✅ apps/hitl-ui/src/components/CriterionCard.tsx (handleStructuredSave wraps mappings)
- ✅ services/api-service/src/api_service/reviews.py (field_mappings storage, v1.5-multi schema)

All commits exist:
- ✅ f9e0070: feat(27-01): add multi-mapping support to StructuredFieldEditor
- ✅ e12dd5d: feat(27-01): backend support for field_mappings array storage

TypeScript verification:
- ✅ `npx tsc --noEmit` → Zero errors

Python verification:
- ✅ `uv run ruff check services/api-service/` → All checks passed
- ✅ `uv run mypy services/api-service/src/api_service/reviews.py` → Success
- ✅ `uv run pytest services/api-service/tests/test_review_api.py` → 24 passed

Data flow verification:
- ✅ Frontend sends `{ field_mappings: [...] }` in modified_structured_fields
- ✅ Backend stores in criterion.conditions JSONB column
- ✅ Backend returns conditions.field_mappings in CriterionResponse
- ✅ Audit log includes schema_version = "v1.5-multi"
