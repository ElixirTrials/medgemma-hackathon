# Architecture Research: Structured Field Mapping Editor Integration

**Domain:** Clinical trial criteria HITL review with structured field editing
**Researched:** 2026-02-13
**Confidence:** HIGH

## Executive Summary

The structured field mapping editor extends the existing HITL review UI (ReviewPage → CriterionCard) with inline structured editing capabilities for temporal_constraint, numeric_thresholds, and conditions fields. The architecture follows the existing pattern: React Hook Form for complex form state, Radix UI for accessible components, TanStack Query for server sync, and the ReviewActionRequest model extended to support structured field updates.

Key architectural decisions:
1. **Component strategy**: New StructuredFieldEditor component wraps CriterionCard edit mode, replacing simple textarea with structured form
2. **Data model**: ReviewActionRequest extends with `modified_structured_fields` JSON object
3. **State management**: React Hook Form with useFieldArray for dynamic threshold arrays, no new Zustand store needed
4. **PDF integration**: PdfViewer extends with react-pdf-highlighter for scroll-to-source via page/coordinates metadata

## Current Architecture Analysis

### Existing Data Flow

```
User Action (CriterionCard)
    ↓
handleModifySave() → onAction(criterionId, ReviewActionRequest)
    ↓
useReviewAction (TanStack Query mutation)
    ↓
POST /reviews/criteria/{id}/action (FastAPI)
    ↓
_apply_review_action() → update Criteria model
    ↓
db.commit() + invalidate queries
    ↓
UI re-renders with updated data
```

### Existing Component Hierarchy

```
ReviewPage.tsx
├── PdfViewer (left panel)
│   └── Document + Page (react-pdf)
└── CriterionCard (right panel, repeated)
    ├── Badges (type, category, confidence, status)
    ├── Display mode: criterion.text
    ├── Edit mode: textarea + type/category inputs
    └── Action buttons (Approve/Reject/Modify)
```

### Existing Request Models

**Frontend (useReviews.ts):**
```typescript
interface ReviewActionRequest {
    action: 'approve' | 'reject' | 'modify';
    reviewer_id: string;
    modified_text?: string;
    modified_type?: string;
    modified_category?: string;
    comment?: string;
}
```

**Backend (reviews.py):**
```python
class ReviewActionRequest(BaseModel):
    action: Literal["approve", "reject", "modify"]
    reviewer_id: str
    modified_text: str | None = None
    modified_type: str | None = None
    modified_category: str | None = None
    comment: str | None = None
```

## Proposed Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    React UI Layer                            │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌──────────────────┐  ┌───────────────┐  │
│  │ ReviewPage  │  │ CriterionCard    │  │ PdfViewer     │  │
│  │             │  │ ┌──────────────┐ │  │ (extended)    │  │
│  │             │  │ │ Structured   │ │  │ + highlight   │  │
│  │             │  │ │ FieldEditor  │ │  │ + scroll-to   │  │
│  │             │  │ └──────────────┘ │  │               │  │
│  └─────────────┘  └──────────────────┘  └───────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                 State Management Layer                       │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐    │
│  │ TanStack     │  │ React Hook   │  │ Zustand        │    │
│  │ Query        │  │ Form         │  │ (authStore)    │    │
│  │ (server sync)│  │ (form state) │  │                │    │
│  └──────────────┘  └──────────────┘  └────────────────┘    │
├─────────────────────────────────────────────────────────────┤
│                      API Layer                               │
├─────────────────────────────────────────────────────────────┤
│  POST /reviews/criteria/{id}/action (extended)              │
│  GET  /reviews/protocols/{id}/pdf-url (existing)            │
└─────────────────────────────────────────────────────────────┘
```

### New Components Architecture

#### 1. StructuredFieldEditor Component

**Location:** `apps/hitl-ui/src/components/StructuredFieldEditor.tsx`

**Purpose:** Inline structured editing for temporal_constraint, numeric_thresholds, conditions

**Props:**
```typescript
interface StructuredFieldEditorProps {
    criterion: Criterion;
    onSave: (structuredFields: StructuredFieldData) => void;
    onCancel: () => void;
    isSubmitting: boolean;
}

interface StructuredFieldData {
    temporal_constraint?: TemporalConstraint;
    numeric_thresholds?: NumericThreshold[];
    conditions?: Condition[];
}

interface TemporalConstraint {
    duration: string;
    relation: 'within' | 'before' | 'after' | 'at_least';
    reference_point?: string;
}

interface NumericThreshold {
    value: number;
    comparator: '>=' | '<=' | '>' | '<' | '==' | 'range';
    unit: string;
    upper_value?: number;
}

interface Condition {
    type: string;
    description: string;
}
```

**Implementation Pattern:**
- Uses React Hook Form with `useForm` and `useFieldArray` for threshold arrays
- Radix UI components for select dropdowns (relation, comparator)
- Controlled inputs with validation
- Dynamic add/remove for threshold arrays

**Component Structure:**
```tsx
<form onSubmit={handleSubmit(onSave)}>
  <TemporalConstraintFields control={control} />
  <NumericThresholdsFields control={control} fields={fields} append={append} remove={remove} />
  <ConditionsFields control={control} />
  <ActionButtons />
</form>
```

#### 2. CriterionCard Modifications

**Changes:**
- Replace simple edit mode with StructuredFieldEditor when `isEditing && isStructuredEditMode`
- Add toggle button: "Text Edit" vs "Structured Edit"
- Pass structured field data to editor
- Handle structured save callback

**Updated Edit Flow:**
```typescript
const [editMode, setEditMode] = useState<'text' | 'structured'>('text');

function handleStructuredSave(structuredFields: StructuredFieldData) {
    onAction(criterion.id, {
        action: 'modify',
        reviewer_id: 'current-user',
        modified_text: editText, // can edit both text and structured
        modified_structured_fields: structuredFields,
    });
    setIsEditing(false);
}
```

#### 3. PdfViewer Enhancement

**New Capabilities:**
- Scroll to page and highlight text
- Accept page number and text coordinates as props
- Use react-pdf-highlighter for highlight overlay

**Extended Props:**
```typescript
interface PdfViewerProps {
    url: string;
    highlightTarget?: {
        page: number;
        boundingBox?: { x: number; y: number; width: number; height: number };
        text?: string;
    };
}
```

**Implementation Strategy:**
- Wrap existing react-pdf Document with react-pdf-highlighter HighlightArea
- Add `onHighlightClick` to jump to page
- Store highlight state in component (no Zustand needed, prop-driven)
- Use PdfViewer's existing pageNumber state, extend to accept external page changes

**Library Choice:** [react-pdf-highlighter-extended](https://github.com/DanielArnould/react-pdf-highlighter-extended) (most actively maintained, supports zoom and custom styling)

## Data Model Extensions

### Frontend Type Additions

**File:** `apps/hitl-ui/src/hooks/useReviews.ts`

```typescript
interface ReviewActionRequest {
    action: 'approve' | 'reject' | 'modify';
    reviewer_id: string;
    modified_text?: string;
    modified_type?: string;
    modified_category?: string;
    modified_structured_fields?: {  // NEW
        temporal_constraint?: Record<string, unknown>;
        numeric_thresholds?: Record<string, unknown>;
        conditions?: Record<string, unknown>;
    };
    comment?: string;
}
```

### Backend Model Extensions

**File:** `services/api-service/src/api_service/reviews.py`

```python
class ReviewActionRequest(BaseModel):
    action: Literal["approve", "reject", "modify"]
    reviewer_id: str
    modified_text: str | None = None
    modified_type: str | None = None
    modified_category: str | None = None
    modified_structured_fields: Dict[str, Any] | None = None  # NEW
    comment: str | None = None
```

**Update `_apply_review_action()` function:**
```python
def _apply_review_action(
    criterion: Criteria,
    body: ReviewActionRequest,
) -> tuple[Dict[str, Any], Dict[str, Any] | None]:
    before_value: Dict[str, Any] = {
        "text": criterion.text,
        "criteria_type": criterion.criteria_type,
        "category": criterion.category,
        "temporal_constraint": criterion.temporal_constraint,  # NEW
        "numeric_thresholds": criterion.numeric_thresholds,    # NEW
        "conditions": criterion.conditions,                    # NEW
    }
    after_value: Dict[str, Any] | None = None

    if body.action == "modify":
        criterion.review_status = "modified"
        if body.modified_text is not None:
            criterion.text = body.modified_text
        if body.modified_type is not None:
            criterion.criteria_type = body.modified_type
        if body.modified_category is not None:
            criterion.category = body.modified_category

        # NEW: Handle structured field updates
        if body.modified_structured_fields is not None:
            fields = body.modified_structured_fields
            if "temporal_constraint" in fields:
                criterion.temporal_constraint = fields["temporal_constraint"]
            if "numeric_thresholds" in fields:
                criterion.numeric_thresholds = fields["numeric_thresholds"]
            if "conditions" in fields:
                criterion.conditions = fields["conditions"]

        after_value = {
            "text": criterion.text,
            "criteria_type": criterion.criteria_type,
            "category": criterion.category,
            "temporal_constraint": criterion.temporal_constraint,
            "numeric_thresholds": criterion.numeric_thresholds,
            "conditions": criterion.conditions,
        }

    return before_value, after_value
```

### Database Schema

**No changes needed** — `Criteria` model already has JSONB columns:
- `temporal_constraint: Dict[str, Any] | None`
- `numeric_thresholds: Dict[str, Any] | None`
- `conditions: Dict[str, Any] | None`

## State Management Patterns

### Form State Strategy

**Primary Tool:** React Hook Form (already in package.json)

**Pattern:**
```typescript
// In StructuredFieldEditor.tsx
const { control, handleSubmit, watch, reset } = useForm<StructuredFieldData>({
    defaultValues: {
        temporal_constraint: criterion.temporal_constraint || undefined,
        numeric_thresholds: criterion.numeric_thresholds?.thresholds || [],
        conditions: criterion.conditions?.conditions || [],
    }
});

const { fields, append, remove } = useFieldArray({
    control,
    name: 'numeric_thresholds',
});
```

**Why React Hook Form:**
- Already integrated in codebase
- Built-in validation with schema integration
- `useFieldArray` handles dynamic threshold lists perfectly
- No additional state library needed
- Performance optimized (minimal re-renders)

**References:**
- [React Hook Form useFieldArray](https://react-hook-form.com/docs/usefieldarray)
- [React Hook Form nested objects best practices](https://medium.com/@krithi.muthuraj/solving-nested-dynamic-forms-using-react-hook-form-6097b0072d48)

### Server State Strategy

**Primary Tool:** TanStack Query (existing pattern)

**No changes to query pattern:**
- `useReviewAction()` mutation already handles arbitrary ReviewActionRequest
- `invalidateQueries` triggers re-fetch after save
- Optimistic updates not needed (low-frequency HITL actions)

**Existing pattern works:**
```typescript
const reviewAction = useReviewAction();
reviewAction.mutate({
    criteriaId: criterion.id,
    ...reviewActionRequest  // includes new modified_structured_fields
});
```

### UI State Strategy

**No new Zustand store needed**

**Component-local state sufficient:**
- Edit mode toggle: `useState<'text' | 'structured'>('text')`
- PDF highlight: prop-driven from CriterionCard click
- Form state: React Hook Form manages internally

**Why avoid global state:**
- Structured editing is per-criterion (not shared)
- PDF highlight driven by user click (transient)
- No cross-component coordination needed beyond props

## PDF Scroll-to-Source Implementation

### Data Requirements

**Criteria model already has:**
- `source_section: str | None` — section text like "Inclusion Criteria"

**Needs to be added (optional enhancement):**
- `source_page: int | None` — page number where criterion appears
- `source_coordinates: Dict[str, Any] | None` — bounding box for precise highlight

**Short-term approach (no backend changes):**
- Extract page number from `source_section` text if present (e.g., "Page 5: Inclusion Criteria")
- Use text search within page to find approximate location
- Full coordinates can be added later when extraction service provides them

### Component Integration

**CriterionCard changes:**
```typescript
// Add click handler to criterion text
<p
    className="text-sm text-foreground mb-3 cursor-pointer hover:underline"
    onClick={() => onScrollToPdf(criterion)}
>
    {criterion.text}
</p>
```

**ReviewPage changes:**
```typescript
const [pdfHighlight, setPdfHighlight] = useState<PdfHighlight | null>(null);

function handleScrollToPdf(criterion: Criterion) {
    if (criterion.source_page) {
        setPdfHighlight({
            page: criterion.source_page,
            text: criterion.text,
        });
    }
}

// Pass to PdfViewer
<PdfViewer
    url={pdfData.url}
    highlightTarget={pdfHighlight}
    onHighlightDismiss={() => setPdfHighlight(null)}
/>
```

**PdfViewer implementation:**
```typescript
// Using react-pdf-highlighter-extended
import { PdfHighlighter, Highlight, Popup } from 'react-pdf-highlighter-extended';

export default function PdfViewer({ url, highlightTarget }: PdfViewerProps) {
    const [highlights, setHighlights] = useState<Highlight[]>([]);

    useEffect(() => {
        if (highlightTarget) {
            // Scroll to page
            // Create temporary highlight
            const tempHighlight: Highlight = {
                id: 'temp',
                position: {
                    pageNumber: highlightTarget.page,
                    boundingRect: highlightTarget.boundingBox || {
                        x1: 0, y1: 0, x2: 100, y2: 100, width: 100, height: 100,
                    },
                },
                content: { text: highlightTarget.text },
            };
            setHighlights([tempHighlight]);
        }
    }, [highlightTarget]);

    return (
        <PdfHighlighter
            pdfDocument={url}
            highlights={highlights}
            onSelectionFinished={() => {}}
        />
    );
}
```

**Library rationale:**
- [react-pdf-highlighter-extended](https://github.com/DanielArnould/react-pdf-highlighter-extended) chosen over base react-pdf-highlighter
- Actively maintained (last update 2025)
- Better TypeScript support
- Zoom support built-in
- Custom styling capabilities

**Alternative approach (if coordinates unavailable):**
- Use react-pdf's text layer search
- Find text occurrence on page
- Highlight entire page section
- Lower precision but works with current data model

## Architectural Patterns

### Pattern 1: Inline Structured Editor

**What:** Replace simple textarea with complex form inline within card component

**When to use:**
- Data has multiple structured sub-fields
- Users need visual field separation
- Still single edit session (not multi-step wizard)

**Trade-offs:**
- **Pros:** No modal/drawer needed, inline context, faster editing
- **Cons:** Card becomes large when editing, more complex component

**Example:**
```typescript
// CriterionCard.tsx
{isEditing && editMode === 'structured' ? (
    <StructuredFieldEditor
        criterion={criterion}
        onSave={handleStructuredSave}
        onCancel={() => setIsEditing(false)}
        isSubmitting={isSubmitting}
    />
) : (
    <SimpleTextEditor ... />
)}
```

### Pattern 2: Extend Existing Request Model

**What:** Add optional fields to ReviewActionRequest instead of creating separate endpoint

**When to use:**
- New fields are optional extensions of existing action
- Validation logic remains similar
- UI can fall back to simple mode

**Trade-offs:**
- **Pros:** Single endpoint, backward compatible, simpler API
- **Cons:** Request model grows, need to handle both modes in backend

**Example:**
```python
# Backend handles both simple and structured modifications
if body.modified_text is not None:
    criterion.text = body.modified_text
if body.modified_structured_fields is not None:
    criterion.temporal_constraint = body.modified_structured_fields.get("temporal_constraint")
```

### Pattern 3: Prop-Driven PDF Highlight

**What:** Parent component controls highlight via props, child is pure renderer

**When to use:**
- Highlight triggered by external event (criterion click)
- No persistent highlight state needed
- Single source of truth in parent

**Trade-offs:**
- **Pros:** Simple data flow, no duplicate state, easy to test
- **Cons:** Parent must manage highlight lifecycle

**Example:**
```typescript
// ReviewPage.tsx (parent)
const [highlight, setHighlight] = useState<PdfHighlight | null>(null);

// CriterionCard.tsx (sibling)
onClick={() => setHighlight({ page: 5, text: "..." })}

// PdfViewer.tsx (child)
<PdfViewer highlightTarget={highlight} />
```

## Data Flow: Structured Edit

### Complete Flow Diagram

```
1. User clicks "Modify" → setIsEditing(true)
                        ↓
2. User toggles "Structured Edit"
                        ↓
3. StructuredFieldEditor renders
   - React Hook Form initializes with criterion data
   - useFieldArray manages threshold array
                        ↓
4. User edits fields
   - Add/remove thresholds via append/remove
   - Select dropdowns for relation/comparator
   - Text inputs for values/units
                        ↓
5. User clicks "Save"
   - handleSubmit validates form
   - onSave callback with StructuredFieldData
                        ↓
6. CriterionCard.handleStructuredSave()
   - Constructs ReviewActionRequest with modified_structured_fields
   - Calls onAction(criterionId, request)
                        ↓
7. ReviewPage.handleAction()
   - reviewAction.mutate({ criteriaId, ...request })
                        ↓
8. TanStack Query mutation
   - POST /reviews/criteria/{id}/action
   - Body includes modified_structured_fields JSON
                        ↓
9. FastAPI reviews.py
   - _apply_review_action() updates criterion
   - Writes temporal_constraint, numeric_thresholds, conditions
   - Creates Review + AuditLog records
   - db.commit()
                        ↓
10. Mutation onSuccess
    - invalidateQueries(['batch-criteria'])
                        ↓
11. UI re-fetches criteria
    - CriterionCard re-renders with updated structured data
    - Badges show new threshold/temporal values
```

### Key State Transitions

| State | Location | Trigger | Next State |
|-------|----------|---------|------------|
| View mode | CriterionCard | User clicks Modify | Edit mode (text) |
| Edit mode (text) | CriterionCard | User toggles Structured | Edit mode (structured) |
| Edit mode (structured) | StructuredFieldEditor | User clicks Save | Submitting |
| Submitting | TanStack Query | API responds | Success → View mode |
| Success | CriterionCard | Query invalidation | View mode (updated data) |

## Integration Points

### New Component Dependencies

| Component | New Dependencies | Purpose |
|-----------|------------------|---------|
| StructuredFieldEditor | react-hook-form, @radix-ui/react-select | Form state + accessible selects |
| PdfViewer | react-pdf-highlighter-extended | Text highlighting + scroll-to |
| CriterionCard | (no new deps) | Orchestrates editor toggle |
| ReviewPage | (no new deps) | Manages PDF highlight prop |

### Backend Integration Points

| Endpoint | Changes | Backward Compatible |
|----------|---------|---------------------|
| POST /reviews/criteria/{id}/action | Add optional `modified_structured_fields` to ReviewActionRequest | YES — field is optional |
| _apply_review_action() | Handle structured field updates | YES — only runs if field present |
| Criteria model | (no changes) | YES — JSONB columns exist |

### External Service Calls

**No new external services needed**

| Service | Current Usage | New Usage |
|---------|---------------|-----------|
| GCS | PDF signed URLs | (unchanged) |
| PostgreSQL | Criteria JSONB storage | (unchanged) |
| UMLS MCP | Entity grounding | (not used in this feature) |

## Build Order & Dependencies

### Phase 1: Backend Foundation
**Dependencies:** None
**Duration:** Low complexity

1. Extend `ReviewActionRequest` model with `modified_structured_fields`
2. Update `_apply_review_action()` to handle structured field updates
3. Add integration test for structured modify action
4. Deploy backend changes (backward compatible)

**Deliverable:** API accepts structured field updates

### Phase 2: Frontend Form Components
**Dependencies:** Phase 1 complete
**Duration:** Medium complexity

1. Create `StructuredFieldEditor.tsx` component
   - Temporal constraint fields
   - Numeric thresholds with useFieldArray
   - Conditions fields
2. Create sub-components:
   - `TemporalConstraintFields.tsx`
   - `NumericThresholdsFields.tsx`
   - `ConditionsFields.tsx`
3. Add Radix UI Select components to ui/ folder
4. Wire up React Hook Form validation

**Deliverable:** Structured editor renders and validates

### Phase 3: CriterionCard Integration
**Dependencies:** Phase 2 complete
**Duration:** Low complexity

1. Add edit mode toggle to CriterionCard
2. Conditionally render StructuredFieldEditor
3. Wire up save callback
4. Update TypeScript types in useReviews.ts
5. Test structured save flow end-to-end

**Deliverable:** Users can edit and save structured fields

### Phase 4: PDF Highlighting (Optional)
**Dependencies:** Phase 3 complete
**Duration:** Medium complexity

1. Install react-pdf-highlighter-extended
2. Extend PdfViewer with highlight support
3. Add click handler to CriterionCard criterion text
4. Wire up highlight prop from ReviewPage
5. Test scroll-to-page functionality

**Deliverable:** Clicking criterion scrolls PDF to source

### Phase 5: Source Metadata Enhancement (Future)
**Dependencies:** Phase 4 complete
**Duration:** High complexity (requires backend changes)

1. Update extraction-service to capture page numbers
2. Add `source_page` column to Criteria table (migration)
3. Populate source_page during extraction
4. (Optional) Add bounding box coordinates
5. Update PdfViewer to use precise coordinates

**Deliverable:** Precise PDF highlighting with coordinates

### Dependency Graph

```
Phase 1 (Backend)
    ↓
Phase 2 (Form Components)
    ↓
Phase 3 (Integration) ← [MINIMUM VIABLE]
    ↓
Phase 4 (PDF Highlight) ← [NICE TO HAVE]
    ↓
Phase 5 (Source Metadata) ← [FUTURE ENHANCEMENT]
```

## Scaling Considerations

| Scale | Consideration | Approach |
|-------|---------------|----------|
| 1-100 criteria per batch | Current (no changes needed) | In-memory React state works fine |
| 100-1000 criteria per batch | Large DOM, slow rendering | Virtualize criteria list (react-window) |
| Complex nested structures | Deep object nesting in thresholds | Use React Hook Form useLens for better performance |
| High edit frequency | Many concurrent edits | Add optimistic updates to TanStack Query |

### Performance Optimization Opportunities

1. **Virtualized List:** If >100 criteria per batch, use react-window for CriterionCard list
2. **Debounced Validation:** Debounce React Hook Form validation to avoid lag on typing
3. **Memoization:** Memoize StructuredFieldEditor render with React.memo
4. **Code Splitting:** Lazy load StructuredFieldEditor (only needed when editing)

**Current scale:** 50-100 criteria per protocol — no optimization needed yet

## Anti-Patterns to Avoid

### Anti-Pattern 1: Separate Structured Edit Modal

**What people do:** Create separate modal/drawer for structured editing

**Why it's wrong:**
- Loses context of original criterion text
- Requires modal state management
- Slower workflow (extra click to open modal)

**Do this instead:**
- Inline editing within CriterionCard
- Toggle between text/structured mode
- Keep all context visible

### Anti-Pattern 2: Separate API Endpoint for Structured Updates

**What people do:** Create POST /reviews/criteria/{id}/structured-update

**Why it's wrong:**
- Duplicate endpoint logic
- Frontend needs to decide which endpoint to call
- Harder to maintain (two paths for same action)

**Do this instead:**
- Extend existing ReviewActionRequest model
- Single endpoint handles both simple and structured
- Backend differentiates based on field presence

### Anti-Pattern 3: Global Zustand Store for Form State

**What people do:** Put form state in Zustand store shared across components

**Why it's wrong:**
- Form state is component-local (not shared)
- Zustand triggers unnecessary re-renders
- React Hook Form already manages state efficiently

**Do this instead:**
- React Hook Form manages form state locally
- Only lift state when actually shared between components
- Use TanStack Query for server state

### Anti-Pattern 4: Custom Highlight Implementation

**What people do:** Build custom PDF highlight overlay from scratch

**Why it's wrong:**
- Complex coordinate math (viewport transforms, zoom, rotation)
- Text layer rendering edge cases
- Accessibility concerns
- Weeks of development time

**Do this instead:**
- Use mature library (react-pdf-highlighter-extended)
- Battle-tested coordinate handling
- Built-in accessibility
- Focus on product features

## Sources

### React Ecosystem
- [React Hook Form Documentation](https://react-hook-form.com/)
- [React Hook Form useFieldArray](https://react-hook-form.com/docs/usefieldarray)
- [React Hook Form with Shadcn UI](https://ui.shadcn.com/docs/forms/react-hook-form)
- [React Hook Form nested structures best practices](https://medium.com/@krithi.muthuraj/solving-nested-dynamic-forms-using-react-hook-form-6097b0072d48)
- [React Hook Form useLens for complex nesting](https://react-hook-form.com/docs/uselens)

### PDF Highlighting
- [React PDF Viewer Highlight Plugin](https://react-pdf-viewer.dev/plugins/highlight/)
- [react-pdf-highlighter-extended GitHub](https://github.com/DanielArnould/react-pdf-highlighter-extended)
- [react-pdf-highlighter (base library)](https://github.com/agentcooper/react-pdf-highlighter)

### Architecture Patterns
- [TanStack Query Documentation](https://tanstack.com/query/latest)
- [Zustand Documentation](https://github.com/pmndrs/zustand)
- [Radix UI Primitives](https://www.radix-ui.com/)

---
*Architecture research for: Clinical Trial Criteria HITL Structured Field Mapping*
*Researched: 2026-02-13*
*Confidence: HIGH — Based on verified existing codebase patterns and mature library documentation*
