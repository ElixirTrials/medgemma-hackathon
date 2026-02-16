# Phase 30: UX Polish & Editor Pre-Loading - Research

**Researched:** 2026-02-16
**Domain:** React UI/UX patterns with Radix UI, TailwindCSS, and React Hook Form
**Confidence:** HIGH

## Summary

Phase 30 is a frontend-only UX polish phase focused on enhancing the review workflow with visual status indicators, rationale capture, client-side search/filtering, section sorting, and field mapping display improvements. The work builds on the existing React 18.3, Radix UI v1.x, TailwindCSS v3.4, and React Hook Form v7.55 stack already in place.

Key technical challenges include: (1) implementing efficient client-side filtering with debouncing for responsive search, (2) managing form state for multi-select reject reason checkboxes within a Radix Dialog, (3) pre-loading existing field_mappings into the structured editor's useFieldArray form, and (4) displaying read-only field mapping badges that open the editor when clicked.

The codebase already uses modern React patterns (functional components, hooks, TanStack Query for data fetching), making integration straightforward. Performance considerations are minimal since batch sizes are expected to be <1000 criteria based on typical protocol sizes.

**Primary recommendation:** Use CSS-only solutions (Tailwind utility classes, position: sticky, transition utilities) for visual polish; implement client-side filtering with useMemo for computed filter results and a simple debounced state hook; use Radix Dialog + react-hook-form Controller for reject rationale capture; pre-populate editor state by mapping saved field_mappings to StructuredFieldFormValues in buildInitialValues.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Review status visuals:**
- Left border color to distinguish status: green=approved, red/orange=rejected, yellow=pending (three states)
- No rationale prompt for approve actions — approve is one click
- Reject shows a popup with predefined reason checkboxes (multi-select): "Not a criteria", "Incorrect entity grounding", "Poor splitting into composites", etc. — plus optional free-text
- Modify retains existing rationale pattern

**Section sorting & headers:**
- Bold headers with review progress count: "Inclusion Criteria (8/12 reviewed)", "Exclusion Criteria (3/8 reviewed)"
- Inclusion section first, then Exclusion
- Within each section: pending criteria first, then reviewed
- Uncategorized criteria go into a "To be sorted" panel where the reviewer must assign as inclusion, exclusion, modify, or reject
- "To be sorted" panel appears at the top if any uncategorized criteria exist

**Search & filtering:**
- Sticky search/filter bar above criteria sections
- Text search plus filter dropdowns for: status (pending/reviewed/all), type (inclusion/exclusion), confidence level
- Client-side filtering (instant, on already-loaded data)
- Show/hide non-matching cards (no text highlighting)
- Debounced text input (300ms)

**Field mapping display:**
- Structured mini-cards in read mode showing entity/relation/value per mapping
- Mini-cards are clickable — clicking opens the structured editor focused on that mapping
- All saved mappings load when entering modify mode (not just the clicked one)
- Each criterion should display one or more entity/relation/value rows with a modifiable composite connector (AND/OR) between them
- Design assumption: AI will pre-populate suggested field mappings for most criteria (extraction-side work is deferred to Phase 31/32)

### Claude's Discretion

- Exact chip/card styling for field mapping mini-cards
- Debounce timing for filters
- Animation/transition when filtering cards
- Exact placement of "To be sorted" panel

### Deferred Ideas (OUT OF SCOPE)

- AI auto-generating field mappings during extraction (pipeline-side work for Phase 31/32)
- Server-side search for scaling to very large batches

</user_constraints>

## Standard Stack

### Core Libraries (Already Installed)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| React | 18.3.1 | UI framework | Modern React with hooks, concurrent features |
| React Hook Form | 7.55.0 | Form state management | Already used in StructuredFieldEditor; minimal re-renders |
| Radix UI | 1.x (various) | Headless UI primitives | Already used (Dialog, Tabs, Checkbox); accessible, composable |
| TailwindCSS | 3.4.17 | Utility-first styling | Already configured; HSL CSS variables for theming |
| TanStack Query | 5.90.15 | Server state & caching | Already handles data fetching/invalidation |
| Lucide React | 0.487.0 | Icon library | Already used throughout (CheckCircle, XCircle, etc.) |

### Supporting Libraries (Recommended)

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| use-debounce | ^10.0.0 | Debounced state hook | For search input debouncing (simpler than lodash) |
| lodash.debounce | ^4.0.8 | Debounce utility | Alternative if fine control needed; already in deps |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| use-debounce | Custom useDebounce hook | More code to maintain; use-debounce is tiny (1kb) |
| Radix Dialog | Native dialog element | Radix already in project; consistent with existing UI |
| CSS position: sticky | react-sticky library | CSS is simpler, faster (GPU-accelerated), zero dependencies |
| useMemo for filtering | Separate state manager | Over-engineering for client-side filtering |

**Installation:**

Not required — all core libraries already installed. Optional:

```bash
npm install use-debounce
```

## Architecture Patterns

### Project Structure (Current)

```
apps/hitl-ui/src/
├── components/
│   ├── CriterionCard.tsx          # Contains review action logic
│   ├── structured-editor/         # StructuredFieldEditor + types
│   └── ui/                        # Button, etc.
├── screens/
│   └── ReviewPage.tsx             # Main review workflow container
├── hooks/
│   └── useReviews.ts              # TanStack Query hooks for API
└── stores/                        # Zustand stores (auth, etc.)
```

### Pattern 1: Client-Side Filtering with useMemo

**What:** Compute filtered list on every dependency change (criteria array, search text, filter values) using useMemo to avoid re-computation on unrelated renders.

**When to use:** Client-side filtering for <10k items with moderate filter complexity.

**Example:**

```typescript
import { useMemo, useState } from 'react';
import { useDebounce } from 'use-debounce';

function ReviewPage() {
  const { data: criteria } = useBatchCriteria(batchId);
  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState<string>('all');
  const [typeFilter, setTypeFilter] = useState<string>('all');
  const [confidenceFilter, setConfidenceFilter] = useState<string>('all');

  // Debounce search text to avoid re-filtering on every keystroke
  const [debouncedSearch] = useDebounce(searchText, 300);

  const filteredCriteria = useMemo(() => {
    if (!criteria) return [];

    return criteria.filter(c => {
      // Text search (case-insensitive, checks criterion text)
      if (debouncedSearch && !c.text.toLowerCase().includes(debouncedSearch.toLowerCase())) {
        return false;
      }

      // Status filter
      if (statusFilter !== 'all') {
        const isReviewed = c.review_status !== null;
        if (statusFilter === 'reviewed' && !isReviewed) return false;
        if (statusFilter === 'pending' && isReviewed) return false;
      }

      // Type filter (inclusion/exclusion)
      if (typeFilter !== 'all' && c.criteria_type !== typeFilter) {
        return false;
      }

      // Confidence filter (high/medium/low)
      if (confidenceFilter !== 'all') {
        const isHigh = c.confidence >= 0.85;
        const isMedium = c.confidence >= 0.7 && c.confidence < 0.85;
        const isLow = c.confidence < 0.7;

        if (confidenceFilter === 'high' && !isHigh) return false;
        if (confidenceFilter === 'medium' && !isMedium) return false;
        if (confidenceFilter === 'low' && !isLow) return false;
      }

      return true;
    });
  }, [criteria, debouncedSearch, statusFilter, typeFilter, confidenceFilter]);

  // ... render filteredCriteria
}
```

**Source:** Adapted from [React filter list performance patterns](https://www.zigpoll.com/content/how-can-i-optimize-the-performance-of-my-react-app-when-rendering-large-lists-of-dynamic-data)

### Pattern 2: Section Grouping with Headers

**What:** Group criteria by type (inclusion/exclusion/uncategorized), sort within each group (pending first), render with headers showing progress.

**When to use:** List sections with different sort/display rules per section.

**Example:**

```typescript
// Group and sort criteria
const { inclusionCriteria, exclusionCriteria, uncategorizedCriteria } = useMemo(() => {
  const inclusion: Criterion[] = [];
  const exclusion: Criterion[] = [];
  const uncategorized: Criterion[] = [];

  filteredCriteria.forEach(c => {
    if (c.criteria_type === 'inclusion') inclusion.push(c);
    else if (c.criteria_type === 'exclusion') exclusion.push(c);
    else uncategorized.push(c);
  });

  // Sort: pending first, then reviewed
  const sortByStatus = (a: Criterion, b: Criterion) => {
    const aReviewed = a.review_status !== null;
    const bReviewed = b.review_status !== null;
    if (aReviewed === bReviewed) return 0;
    return aReviewed ? 1 : -1;
  };

  inclusion.sort(sortByStatus);
  exclusion.sort(sortByStatus);
  uncategorized.sort(sortByStatus);

  return { inclusionCriteria: inclusion, exclusionCriteria: exclusion, uncategorizedCriteria: uncategorized };
}, [filteredCriteria]);

// Render sections
return (
  <>
    {uncategorizedCriteria.length > 0 && (
      <section>
        <h2 className="text-lg font-semibold mb-3">
          To Be Sorted ({uncategorizedCriteria.filter(c => c.review_status !== null).length}/{uncategorizedCriteria.length} reviewed)
        </h2>
        {uncategorizedCriteria.map(c => <CriterionCard key={c.id} criterion={c} />)}
      </section>
    )}

    <section>
      <h2 className="text-lg font-semibold mb-3">
        Inclusion Criteria ({inclusionCriteria.filter(c => c.review_status !== null).length}/{inclusionCriteria.length} reviewed)
      </h2>
      {inclusionCriteria.map(c => <CriterionCard key={c.id} criterion={c} />)}
    </section>

    <section>
      <h2 className="text-lg font-semibold mb-3">
        Exclusion Criteria ({exclusionCriteria.filter(c => c.review_status !== null).length}/{exclusionCriteria.length} reviewed)
      </h2>
      {exclusionCriteria.map(c => <CriterionCard key={c.id} criterion={c} />)}
    </section>
  </>
);
```

**Source:** Adapted from [React list grouping patterns](https://ej2.syncfusion.com/react/documentation/listview/grouping)

### Pattern 3: Radix Dialog with Checkbox Multi-Select

**What:** Controlled Radix Dialog containing react-hook-form with checkbox group for reject reasons.

**When to use:** Capture structured input (multi-select + optional text) in a modal before action.

**Example:**

```typescript
import * as Dialog from '@radix-ui/react-dialog';
import { useForm, Controller } from 'react-hook-form';

const REJECT_REASONS = [
  { value: 'not_criteria', label: 'Not a criteria' },
  { value: 'incorrect_grounding', label: 'Incorrect entity grounding' },
  { value: 'poor_splitting', label: 'Poor splitting into composites' },
  { value: 'other', label: 'Other' },
];

interface RejectDialogProps {
  open: boolean;
  onClose: () => void;
  onSubmit: (data: { reasons: string[]; comment?: string }) => void;
}

function RejectDialog({ open, onClose, onSubmit }: RejectDialogProps) {
  const { control, handleSubmit, reset } = useForm({
    defaultValues: { reasons: [], comment: '' },
  });

  const handleFormSubmit = (data: { reasons: string[]; comment: string }) => {
    onSubmit({ reasons: data.reasons, comment: data.comment || undefined });
    reset();
    onClose();
  };

  return (
    <Dialog.Root open={open} onOpenChange={onClose}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/50" />
        <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-lg p-6 max-w-md w-full">
          <Dialog.Title className="text-lg font-semibold mb-4">
            Reject Criterion
          </Dialog.Title>

          <form onSubmit={handleSubmit(handleFormSubmit)}>
            <div className="space-y-3 mb-4">
              <label className="text-sm font-medium">Reasons (select all that apply)</label>
              {REJECT_REASONS.map(reason => (
                <Controller
                  key={reason.value}
                  name="reasons"
                  control={control}
                  render={({ field }) => (
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        value={reason.value}
                        checked={field.value.includes(reason.value)}
                        onChange={(e) => {
                          if (e.target.checked) {
                            field.onChange([...field.value, reason.value]);
                          } else {
                            field.onChange(field.value.filter(v => v !== reason.value));
                          }
                        }}
                        className="h-4 w-4 rounded border-gray-300"
                      />
                      <span className="text-sm">{reason.label}</span>
                    </label>
                  )}
                />
              ))}
            </div>

            <Controller
              name="comment"
              control={control}
              render={({ field }) => (
                <textarea
                  {...field}
                  placeholder="Optional additional comments..."
                  className="w-full rounded-md border border-input p-2 text-sm mb-4"
                  rows={3}
                />
              )}
            />

            <div className="flex gap-2">
              <button type="submit" className="px-4 py-2 bg-red-600 text-white rounded">
                Reject
              </button>
              <button type="button" onClick={onClose} className="px-4 py-2 border rounded">
                Cancel
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
```

**Source:** Adapted from [Radix Dialog docs](https://www.radix-ui.com/primitives/docs/components/dialog) and [react-hook-form Controller](https://react-hook-form.com/docs/usecontroller/controller)

### Pattern 4: Pre-Loading Editor State from Saved Data

**What:** Map saved field_mappings from API response to StructuredFieldFormValues shape, passing as initialValues to StructuredFieldEditor.

**When to use:** Editor should restore previous edits when re-opening.

**Example:**

```typescript
// Already implemented in CriterionCard.tsx buildInitialValues() function
// Priority 1: Check for existing field_mappings in conditions
const cond = criterion.conditions as Record<string, unknown> | null;
if (cond && 'field_mappings' in cond && Array.isArray(cond.field_mappings)) {
  const fms = cond.field_mappings as Array<Record<string, unknown>>;
  const mappings: FieldMapping[] = fms.map((fm) => {
    const rel = (fm.relation as string) ?? '';
    const rawVal = fm.value as Record<string, unknown> | undefined;
    let value: FieldValue = { type: 'standard', value: '', unit: '' };

    if (rawVal && rawVal.type === 'range') {
      value = {
        type: 'range',
        min: String(rawVal.min ?? ''),
        max: String(rawVal.max ?? ''),
        unit: String(rawVal.unit ?? ''),
      };
    } else if (rawVal && rawVal.type === 'temporal') {
      value = {
        type: 'temporal',
        duration: String(rawVal.duration ?? ''),
        unit: (rawVal.unit as TemporalUnit) ?? 'days',
      };
    } else if (rawVal && rawVal.type === 'standard') {
      value = {
        type: 'standard',
        value: String(rawVal.value ?? ''),
        unit: String(rawVal.unit ?? ''),
      };
    }

    return {
      entity: String(fm.entity ?? ''),
      relation: (rel as RelationOperator) || '',
      value,
    };
  });

  if (mappings.length > 0) return { mappings };
}

// Priority 2: Infer from AI-extracted data (entities + thresholds)
// ... existing logic
```

**Note:** This pattern is already implemented in CriterionCard.tsx lines 186-222. No changes needed for EDIT-01 — just verify it works correctly.

### Pattern 5: Read-Mode Field Mapping Badges

**What:** Display saved field_mappings as clickable badges/chips showing entity/relation/value; clicking opens structured editor.

**When to use:** Show compact preview of structured data in read mode.

**Example:**

```typescript
// In CriterionCard read mode section (editMode === 'none')
function FieldMappingBadges({ criterion, onOpenEditor }: { criterion: Criterion; onOpenEditor: () => void }) {
  const cond = criterion.conditions as Record<string, unknown> | null;
  if (!cond || !('field_mappings' in cond) || !Array.isArray(cond.field_mappings)) {
    return null;
  }

  const mappings = cond.field_mappings as Array<{ entity: string; relation: string; value: unknown }>;

  return (
    <div className="mb-3 flex flex-wrap gap-2">
      {mappings.map((mapping, idx) => {
        const valueStr = formatMappingValue(mapping.value);
        return (
          <button
            key={idx}
            onClick={onOpenEditor}
            className="inline-flex items-center gap-1 rounded-full bg-blue-100 px-3 py-1 text-xs font-medium text-blue-800 hover:bg-blue-200 transition-colors cursor-pointer"
          >
            <span className="font-semibold">{mapping.entity}</span>
            {mapping.relation && (
              <>
                <span className="text-blue-600">{mapping.relation}</span>
                <span>{valueStr}</span>
              </>
            )}
          </button>
        );
      })}
    </div>
  );
}

function formatMappingValue(value: unknown): string {
  if (typeof value !== 'object' || value === null) return '';
  const v = value as Record<string, unknown>;

  if (v.type === 'range') {
    return `${v.min}-${v.max} ${v.unit || ''}`.trim();
  }
  if (v.type === 'temporal') {
    return `${v.duration} ${v.unit}`.trim();
  }
  if (v.type === 'standard') {
    return `${v.value} ${v.unit || ''}`.trim();
  }
  return '';
}
```

**Source:** Adapted from [Tailwind badge patterns](https://tailwindcss.com/plus/ui-blocks/application-ui/elements/badges)

### Pattern 6: Sticky Filter Bar with CSS

**What:** Use CSS `position: sticky` for filter bar that stays visible during scroll.

**When to use:** Filter controls should remain accessible while scrolling long lists.

**Example:**

```tsx
<div className="h-full overflow-auto">
  {/* Sticky header with filters */}
  <div className="sticky top-0 z-10 bg-card border-b px-4 py-3 space-y-3">
    <div className="flex items-center gap-3">
      <input
        type="text"
        value={searchText}
        onChange={(e) => setSearchText(e.target.value)}
        placeholder="Search criteria..."
        className="flex-1 rounded-md border border-input bg-background px-3 py-2 text-sm"
      />
      <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="...">
        <option value="all">All Status</option>
        <option value="pending">Pending</option>
        <option value="reviewed">Reviewed</option>
      </select>
      {/* More filters */}
    </div>
  </div>

  {/* Scrollable content */}
  <div className="p-4 space-y-4">
    {/* Criteria cards */}
  </div>
</div>
```

**Note:** CSS `position: sticky` is faster than JS solutions (GPU-accelerated). No library needed.

**Source:** [CSS position sticky guide](https://medium.com/@harish_rajora/css-position-sticky-tutorial-with-examples-complete-guide-28e28a3db4e6)

### Pattern 7: Visual Status Distinction with Border Colors

**What:** Use Tailwind border-l-* utilities to add colored left border based on review_status.

**When to use:** Visual status indicators without disrupting card layout.

**Example:**

```typescript
// In CriterionCard.tsx root div
<div
  className={cn(
    'rounded-lg border bg-card p-4 shadow-sm',
    // Add status border
    criterion.review_status === 'approved' && 'border-l-4 border-l-green-500',
    criterion.review_status === 'rejected' && 'border-l-4 border-l-red-500',
    criterion.review_status === 'modified' && 'border-l-4 border-l-blue-500',
    !criterion.review_status && 'border-l-4 border-l-yellow-400',
    // Existing low-confidence border (override if status exists)
    isLowConfidence && !criterion.review_status && 'border-l-4 border-l-red-300'
  )}
>
```

**Source:** [Tailwind border utilities](https://tailwindcss.com/docs/border-width)

### Anti-Patterns to Avoid

- **Filtering on every render without memoization**: Causes performance degradation even for small lists. Always wrap filter logic in useMemo.
- **Deep nesting conditions in JSX**: Makes code hard to read. Extract filter/sort logic to separate useMemo hooks.
- **Using array index as key**: Breaks React reconciliation when filtering/sorting. Always use stable IDs (criterion.id).
- **Mutating original array**: Always create new arrays for filtered/sorted results to ensure React detects changes.
- **Heavy animations on list items**: Avoid complex CSS animations (scale, rotate) on 100+ cards. Simple opacity/height transitions only.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Debouncing | Custom setTimeout logic | use-debounce hook or lodash.debounce | Edge cases: cleanup on unmount, ref stability, concurrent updates |
| Dialog focus trap | Custom keydown handlers | Radix Dialog | Accessible modal patterns (ESC, focus lock, scroll lock) are complex |
| Checkbox group state | Manual array manipulation | react-hook-form Controller | Form validation, error handling, reset logic already built |
| Sticky positioning | IntersectionObserver + state | CSS position: sticky | CSS is simpler, faster (GPU), works with overflow-auto parent |
| List virtualization | Custom scroll handlers | react-window/react-virtualized | Only if >10k items; not needed for typical batch sizes (<1000) |

**Key insight:** Modern browser CSS (sticky, transitions, grid) handles most UI polish needs without JS libraries. React Hook Form + Radix UI already provide accessible, production-ready patterns for forms and dialogs.

## Common Pitfalls

### Pitfall 1: Debounce Closure Stale State

**What goes wrong:** Debounced function captures stale state/props due to closure over initial render values.

**Why it happens:** Creating debounced function inline in component body creates new function on every render with stale closures.

**How to avoid:** Use `useMemo` or `useRef` to memoize debounced function, or use `use-debounce` hook which handles this automatically.

**Warning signs:** Filter results don't update after state changes; debounced function uses old values.

**Example (WRONG):**

```typescript
function MyComponent() {
  const [search, setSearch] = useState('');
  const [items, setItems] = useState([]);

  // BAD: creates new debounced fn every render, captures stale items
  const debouncedFilter = debounce(() => {
    const filtered = items.filter(item => item.name.includes(search));
    // ... do something
  }, 300);

  return <input onChange={(e) => { setSearch(e.target.value); debouncedFilter(); }} />;
}
```

**Example (CORRECT):**

```typescript
import { useDebounce } from 'use-debounce';

function MyComponent() {
  const [search, setSearch] = useState('');
  const [items, setItems] = useState([]);

  // GOOD: use-debounce hook handles memoization
  const [debouncedSearch] = useDebounce(search, 300);

  const filteredItems = useMemo(() => {
    return items.filter(item => item.name.includes(debouncedSearch));
  }, [items, debouncedSearch]);

  return <input value={search} onChange={(e) => setSearch(e.target.value)} />;
}
```

**Source:** [React debounce pitfalls](https://www.developerway.com/posts/debouncing-in-react)

### Pitfall 2: React Hook Form Controller Re-Renders

**What goes wrong:** Every keystroke in a Controller-wrapped input re-renders parent component, causing lag.

**Why it happens:** Controller subscribes to formState by default; parent re-renders on every form change.

**How to avoid:** Use `useWatch` for selective subscriptions; extract controlled inputs to separate components wrapped in React.memo; avoid destructuring formState at root level.

**Warning signs:** Typing in input feels sluggish; React DevTools shows parent re-rendering on every keystroke.

**Example (optimized):**

```typescript
// Extract checkbox group to separate memoized component
const CheckboxGroup = React.memo(({ control }: { control: Control }) => {
  return (
    <>
      {REJECT_REASONS.map(reason => (
        <Controller key={reason.value} name="reasons" control={control} /* ... */ />
      ))}
    </>
  );
});
```

**Source:** [React Hook Form re-render optimization](https://react-hook-form.com/advanced-usage/)

### Pitfall 3: useMemo Dependency Array Mistakes

**What goes wrong:** Filtered list doesn't update when it should, or updates too often causing performance issues.

**Why it happens:** Missing dependencies (filter doesn't re-run when values change) or unnecessary dependencies (re-runs on unrelated changes).

**How to avoid:** Include all values used inside useMemo in dependency array; use ESLint plugin for exhaustive-deps warnings.

**Warning signs:** Filter results stale after changing filters; or excessive re-filtering (see in React DevTools Profiler).

**Example:**

```typescript
// Include all filter variables in deps
const filteredCriteria = useMemo(() => {
  return criteria.filter(c => {
    // Uses: criteria, debouncedSearch, statusFilter, typeFilter, confidenceFilter
    // ...
  });
}, [criteria, debouncedSearch, statusFilter, typeFilter, confidenceFilter]); // All deps listed
```

**Source:** [React useMemo best practices](https://react.dev/reference/react/useMemo)

### Pitfall 4: Sticky Positioning with overflow-hidden Parent

**What goes wrong:** Sticky element doesn't stick; scrolls away normally.

**Why it happens:** CSS `position: sticky` requires an overflow-scroll ancestor. If parent has `overflow: hidden`, sticky doesn't work.

**How to avoid:** Ensure sticky element's scroll container has `overflow-auto` or `overflow-scroll`, not `overflow: hidden`.

**Warning signs:** Sticky bar scrolls out of view instead of staying at top.

**Example (CORRECT structure):**

```tsx
<div className="h-screen flex flex-col">
  <div className="h-full overflow-auto"> {/* overflow-auto here */}
    <div className="sticky top-0 z-10"> {/* sticky works */}
      Filters
    </div>
    <div>Content</div>
  </div>
</div>
```

**Source:** [CSS sticky positioning gotchas](https://medium.com/@harish_rajora/css-position-sticky-tutorial-with-examples-complete-guide-28e28a3db4e6)

### Pitfall 5: Key Prop Instability After Filtering

**What goes wrong:** React re-mounts components after filter changes instead of updating them; lose component state (e.g., open accordions collapse).

**Why it happens:** Using array index as key; when array changes, indices shift and React thinks items are different.

**How to avoid:** Always use stable unique ID as key (e.g., criterion.id), never array index.

**Warning signs:** Component animations restart after filtering; internal component state resets.

**Example:**

```typescript
// WRONG
{filteredCriteria.map((c, idx) => <CriterionCard key={idx} criterion={c} />)}

// CORRECT
{filteredCriteria.map(c => <CriterionCard key={c.id} criterion={c} />)}
```

**Source:** [React list rendering best practices](https://react.dev/learn/rendering-lists)

## Code Examples

Verified patterns from official sources and existing codebase:

### Client-Side Search with Debounce (use-debounce)

```typescript
import { useState, useMemo } from 'react';
import { useDebounce } from 'use-debounce';

function ReviewPage() {
  const { data: criteria } = useBatchCriteria(batchId);
  const [searchText, setSearchText] = useState('');
  const [debouncedSearch] = useDebounce(searchText, 300);

  const filteredCriteria = useMemo(() => {
    if (!criteria) return [];
    if (!debouncedSearch) return criteria;

    const lowerSearch = debouncedSearch.toLowerCase();
    return criteria.filter(c => c.text.toLowerCase().includes(lowerSearch));
  }, [criteria, debouncedSearch]);

  return (
    <div>
      <input
        type="text"
        value={searchText}
        onChange={(e) => setSearchText(e.target.value)}
        placeholder="Search criteria..."
        className="w-full rounded-md border px-3 py-2"
      />
      <div className="mt-4 space-y-4">
        {filteredCriteria.map(c => <CriterionCard key={c.id} criterion={c} />)}
      </div>
    </div>
  );
}
```

**Source:** [use-debounce documentation](https://github.com/xnimorz/use-debounce)

### Reject Dialog with Multi-Select Checkboxes

```typescript
import * as Dialog from '@radix-ui/react-dialog';
import { useForm, Controller } from 'react-hook-form';
import { Button } from '@/components/ui/Button';

const REJECT_REASONS = [
  { value: 'not_criteria', label: 'Not a criteria' },
  { value: 'incorrect_grounding', label: 'Incorrect entity grounding' },
  { value: 'poor_splitting', label: 'Poor splitting into composites' },
];

interface RejectFormData {
  reasons: string[];
  comment: string;
}

function RejectDialog({ open, onOpenChange, onConfirm }) {
  const { control, handleSubmit, reset } = useForm<RejectFormData>({
    defaultValues: { reasons: [], comment: '' },
  });

  const handleReject = (data: RejectFormData) => {
    onConfirm({ reasons: data.reasons, comment: data.comment || undefined });
    reset();
    onOpenChange(false);
  };

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/50 z-50" />
        <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-white rounded-lg p-6 max-w-md w-full z-50 shadow-lg">
          <Dialog.Title className="text-lg font-semibold mb-4">
            Reject Criterion
          </Dialog.Title>

          <form onSubmit={handleSubmit(handleReject)} className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2">
                Reasons (select all that apply)
              </label>
              <div className="space-y-2">
                {REJECT_REASONS.map(reason => (
                  <Controller
                    key={reason.value}
                    name="reasons"
                    control={control}
                    render={({ field }) => (
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          value={reason.value}
                          checked={field.value.includes(reason.value)}
                          onChange={(e) => {
                            const newValue = e.target.checked
                              ? [...field.value, reason.value]
                              : field.value.filter(v => v !== reason.value);
                            field.onChange(newValue);
                          }}
                          className="h-4 w-4 rounded border-gray-300"
                        />
                        <span className="text-sm">{reason.label}</span>
                      </label>
                    )}
                  />
                ))}
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">
                Additional comments (optional)
              </label>
              <Controller
                name="comment"
                control={control}
                render={({ field }) => (
                  <textarea
                    {...field}
                    placeholder="Explain your reasoning..."
                    className="w-full rounded-md border border-input px-3 py-2 text-sm"
                    rows={3}
                  />
                )}
              />
            </div>

            <div className="flex gap-2 justify-end">
              <Button
                type="button"
                variant="outline"
                onClick={() => { reset(); onOpenChange(false); }}
              >
                Cancel
              </Button>
              <Button type="submit" variant="destructive">
                Reject
              </Button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
```

**Source:** Adapted from [Radix Dialog docs](https://www.radix-ui.com/primitives/docs/components/dialog) and existing project patterns

### Field Mapping Badges (Read Mode)

```typescript
interface FieldMappingBadgesProps {
  criterion: Criterion;
  onEditClick: () => void;
}

function FieldMappingBadges({ criterion, onEditClick }: FieldMappingBadgesProps) {
  const cond = criterion.conditions as Record<string, unknown> | null;
  const fieldMappings = cond?.field_mappings as Array<{ entity: string; relation: string; value: Record<string, unknown> }> | undefined;

  if (!fieldMappings || fieldMappings.length === 0) return null;

  return (
    <div className="mb-3">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-xs font-medium text-muted-foreground">Field Mappings:</span>
      </div>
      <div className="flex flex-wrap gap-2">
        {fieldMappings.map((mapping, idx) => {
          const valueDisplay = formatFieldValue(mapping.value);

          return (
            <button
              key={idx}
              onClick={onEditClick}
              className="inline-flex items-center gap-1.5 rounded-full bg-blue-50 border border-blue-200 px-3 py-1.5 text-xs hover:bg-blue-100 transition-colors cursor-pointer"
              title="Click to edit"
            >
              <span className="font-semibold text-blue-900">{mapping.entity}</span>
              {mapping.relation && (
                <>
                  <span className="text-blue-600">{mapping.relation}</span>
                  {valueDisplay && <span className="text-blue-800">{valueDisplay}</span>}
                </>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function formatFieldValue(value: Record<string, unknown>): string {
  if (value.type === 'range') {
    return `${value.min}–${value.max}${value.unit ? ' ' + value.unit : ''}`;
  }
  if (value.type === 'temporal') {
    return `${value.duration} ${value.unit}`;
  }
  if (value.type === 'standard') {
    return `${value.value}${value.unit ? ' ' + value.unit : ''}`;
  }
  return '';
}
```

**Source:** Adapted from [Tailwind badge examples](https://tailwindcss.com/plus/ui-blocks/application-ui/elements/badges)

### Grouped Criteria with Section Headers

```typescript
function CriteriaList({ criteria }: { criteria: Criterion[] }) {
  const grouped = useMemo(() => {
    const uncategorized: Criterion[] = [];
    const inclusion: Criterion[] = [];
    const exclusion: Criterion[] = [];

    criteria.forEach(c => {
      if (!c.criteria_type || c.criteria_type === '') {
        uncategorized.push(c);
      } else if (c.criteria_type === 'inclusion') {
        inclusion.push(c);
      } else if (c.criteria_type === 'exclusion') {
        exclusion.push(c);
      }
    });

    // Sort each group: pending first, then reviewed
    const sortFn = (a: Criterion, b: Criterion) => {
      const aPending = a.review_status === null;
      const bPending = b.review_status === null;
      if (aPending && !bPending) return -1;
      if (!aPending && bPending) return 1;
      return 0;
    };

    uncategorized.sort(sortFn);
    inclusion.sort(sortFn);
    exclusion.sort(sortFn);

    return { uncategorized, inclusion, exclusion };
  }, [criteria]);

  const countReviewed = (list: Criterion[]) => list.filter(c => c.review_status !== null).length;

  return (
    <div className="space-y-6">
      {grouped.uncategorized.length > 0 && (
        <section>
          <h2 className="text-lg font-bold mb-3 text-foreground">
            To Be Sorted ({countReviewed(grouped.uncategorized)}/{grouped.uncategorized.length} reviewed)
          </h2>
          <div className="space-y-4">
            {grouped.uncategorized.map(c => <CriterionCard key={c.id} criterion={c} />)}
          </div>
        </section>
      )}

      <section>
        <h2 className="text-lg font-bold mb-3 text-foreground">
          Inclusion Criteria ({countReviewed(grouped.inclusion)}/{grouped.inclusion.length} reviewed)
        </h2>
        <div className="space-y-4">
          {grouped.inclusion.map(c => <CriterionCard key={c.id} criterion={c} />)}
        </div>
      </section>

      <section>
        <h2 className="text-lg font-bold mb-3 text-foreground">
          Exclusion Criteria ({countReviewed(grouped.exclusion)}/{grouped.exclusion.length} reviewed)
        </h2>
        <div className="space-y-4">
          {grouped.exclusion.map(c => <CriterionCard key={c.id} criterion={c} />)}
        </div>
      </section>
    </div>
  );
}
```

**Source:** Existing CriterionCard patterns + list grouping best practices

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Class components with componentDidMount | Functional components with hooks | React 16.8 (2019) | Simpler state logic, better composition |
| Uncontrolled forms with refs | react-hook-form with Controller | ~2020 | Better validation, less boilerplate |
| Custom debounce with useEffect | use-debounce hook | ~2021 | Handles cleanup and edge cases automatically |
| JavaScript-based sticky headers | CSS position: sticky | Widely supported 2020+ | Better performance, simpler code |
| Formik for forms | react-hook-form | 2020-2023 shift | Less re-renders, better TS support |
| Styled-components | Tailwind CSS utility classes | 2021-2024 shift | Faster builds, smaller bundles, less runtime overhead |

**Deprecated/outdated:**
- **React.FC type**: No longer recommended; use explicit function signatures instead
- **defaultProps**: Deprecated for function components; use default parameters
- **Legacy Context API**: Use React.createContext (new Context API)
- **componentWillReceiveProps**: Use useEffect with dependency array
- **findDOMNode**: Use refs instead

## Open Questions

1. **Approve rationale requirement**
   - What we know: User decisions say "No rationale prompt for approve actions — approve is one click"
   - What's unclear: Should we track approve actions in audit log without rationale?
   - Recommendation: Yes — audit log should record action=approve with no comment field required; rationale is optional for modify and reject only

2. **Filter bar animation preferences**
   - What we know: Claude's discretion for animation/transition when filtering cards
   - What's unclear: User preference for subtle vs. prominent animations
   - Recommendation: Start with simple opacity transition (transition-opacity duration-200) for cards; can enhance if user feedback requests more

3. **"To be sorted" panel placement**
   - What we know: Should appear if uncategorized criteria exist; Claude's discretion for exact placement
   - What's unclear: Above sections or floating sidebar?
   - Recommendation: Place at top of list (before Inclusion) since it's highest priority for reviewer to categorize

4. **Confidence filter thresholds**
   - What we know: Filter by confidence level (high/medium/low)
   - What's unclear: Should thresholds match ConfidenceBadge component (high >=0.85, medium >=0.7, low <0.7)?
   - Recommendation: Yes — reuse existing thresholds from ConfidenceBadge for consistency

## Sources

### Primary (HIGH confidence)

- React 18 documentation - [https://react.dev](https://react.dev) - Hooks, rendering, performance
- React Hook Form documentation - [https://react-hook-form.com](https://react-hook-form.com) - useFieldArray, Controller, validation
- Radix UI Primitives documentation - [https://www.radix-ui.com/primitives](https://www.radix-ui.com/primitives) - Dialog, Checkbox, accessibility
- TailwindCSS documentation - [https://tailwindcss.com/docs](https://tailwindcss.com/docs) - Utilities, transitions, positioning
- Existing codebase - CriterionCard.tsx, StructuredFieldEditor.tsx, ReviewPage.tsx - Current patterns and state management

### Secondary (MEDIUM confidence)

- [use-debounce documentation](https://github.com/xnimorz/use-debounce) - Debounced state hook
- [React Hook Form advanced usage](https://www.react-hook-form.com/advanced-usage/) - Performance optimization
- [Tailwind UI badge examples](https://tailwindcss.com/plus/ui-blocks/application-ui/elements/badges) - Design patterns
- [React useMemo best practices](https://react.dev/reference/react/useMemo) - Memoization guidelines
- [CSS position sticky guide](https://medium.com/@harish_rajora/css-position-sticky-tutorial-with-examples-complete-guide-28e28a3db4e6) - Sticky positioning

### Tertiary (LOW confidence - Verified against official docs)

- [LogRocket: React animation libraries 2026](https://blog.logrocket.com/best-react-animation-libraries/) - Animation recommendations
- [LogRocket: React filter list performance](https://blog.logrocket.com/how-and-when-to-debounce-or-throttle-in-react/) - Debounce patterns
- [Medium: React debouncing](https://www.developerway.com/posts/debouncing-in-react) - Common pitfalls
- [shadcn UI guide](https://designrevision.com/blog/shadcn-ui-guide) - Component library overview

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries already installed and configured in project
- Architecture patterns: HIGH - Patterns verified against official docs and existing codebase
- Pitfalls: HIGH - Common issues well-documented in React Hook Form and React docs
- Code examples: HIGH - Adapted from official sources and existing codebase patterns

**Research date:** 2026-02-16
**Valid until:** ~30 days (stable stack; React Hook Form and Radix UI release slowly; Tailwind stable since v3)
