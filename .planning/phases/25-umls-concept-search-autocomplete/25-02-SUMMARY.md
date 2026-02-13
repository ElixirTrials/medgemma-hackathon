---
phase: 25-umls-concept-search-autocomplete
plan: 02
subsystem: hitl-ui
tags: [frontend, umls, autocomplete, react, tanstack-query]
dependency_graph:
  requires:
    - GET /api/umls/search endpoint (from 25-01)
    - EntityCard component
    - TanStack Query infrastructure
  provides:
    - useUmlsSearch hook (debounced UMLS search with TanStack Query)
    - UmlsCombobox component (autocomplete dropdown)
    - EntityCard UMLS autocomplete integration
  affects:
    - Entity review workflow (simplified UMLS grounding modification)
tech_stack:
  added: []
  patterns:
    - React custom hook with useState + useEffect debouncing
    - TanStack Query with AbortController for request cancellation
    - cmdk + Radix Popover for accessible autocomplete UX
    - Discriminated display: primary search input + secondary editable fields
key_files:
  created:
    - apps/hitl-ui/src/hooks/useUmlsSearch.ts
    - apps/hitl-ui/src/components/UmlsCombobox.tsx
  modified:
    - apps/hitl-ui/src/components/EntityCard.tsx
decisions:
  - debounce_pattern: Use useState + useEffect + setTimeout (simpler than external library, standard React pattern)
  - min_chars: 3-character minimum enforced in both hook (enabled flag) and UI (empty state)
  - input_pattern: Plain input as PopoverTrigger (not Command.Input) for cleaner control
  - field_hierarchy: UmlsCombobox as primary input, CUI/SNOMED as secondary editable fields in 2-column grid
  - caching: 5-min staleTime, 10-min gcTime, no refetch on window focus (UMLS data is stable)
metrics:
  duration: 2 min
  tasks_completed: 2
  files_created: 2
  files_modified: 1
  completed_date: 2026-02-13
---

# Phase 25 Plan 02: Frontend UMLS Autocomplete System

Debounced UMLS concept search hook and autocomplete combobox integrated into EntityCard modify mode

## One-Liner

Reviewers can now search UMLS concepts by typing into EntityCard's modify mode — autocomplete shows preferred term + CUI + semantic type, and selecting a result auto-populates all three grounding fields (CUI, SNOMED, preferred term)

## What Was Built

### New Files

**apps/hitl-ui/src/hooks/useUmlsSearch.ts** (77 lines)
- Custom hook wrapping TanStack Query for UMLS concept search
- Debounces query input by 300ms using useState + useEffect pattern (no external library)
- Only enables query when debouncedQuery has 3+ characters
- Passes AbortController signal from TanStack Query to fetch for automatic request cancellation
- Returns `{ results, isLoading, isError, error }` interface
- 5-minute staleTime (UMLS data doesn't change frequently)
- 10-minute garbage collection time
- Single retry on failure (autocomplete shouldn't be aggressive)
- No refetch on window focus

**apps/hitl-ui/src/components/UmlsCombobox.tsx** (138 lines)
- Autocomplete component using cmdk + Radix Popover
- Plain `<input>` wrapped in PopoverTrigger for clean typing UX
- Command.List inside Popover for keyboard-navigable dropdown
- Three states: loading (spinner), empty (<3 chars message), no results (no concepts found)
- Each dropdown item displays:
  - Preferred term (bold, left)
  - CUI code (muted, right)
  - Semantic type + SNOMED code (small text below)
- `shouldFilter={false}` on Command (server-side filtering)
- Popover opens when input focused AND (results exist OR loading OR 3+ chars typed)
- Selecting an item calls `onSelect(result)` and closes popover

### Modified Files

**apps/hitl-ui/src/components/EntityCard.tsx**
- Imported `UmlsCombobox` and `UmlsSearchResult` type
- Replaced three separate text inputs in modify mode with:
  1. **Primary input:** UmlsCombobox with label "Search UMLS Concept"
  2. **Secondary fields:** CUI and SNOMED inputs in 2-column grid with `bg-muted/50` styling
- `onSelect` callback populates all three state fields: `setEditCui`, `setEditSnomed`, `setEditPreferredTerm`
- CUI/SNOMED inputs still editable for manual override
- Save/Cancel buttons unchanged (existing `handleModifySave` sends all fields via `onAction`)

## Deviations from Plan

None - plan executed exactly as written.

## Technical Details

### Debouncing Pattern

Used React's built-in state management instead of an external library:

```typescript
const [debouncedQuery, setDebouncedQuery] = useState(query);

useEffect(() => {
    const timeout = setTimeout(() => {
        setDebouncedQuery(query);
    }, 300);
    return () => clearTimeout(timeout);
}, [query]);
```

This is the standard React pattern, avoids adding dependencies, and works perfectly with TanStack Query's reactivity.

### Request Cancellation

TanStack Query v5 automatically passes `{ signal }` to queryFn. We thread this through to fetch:

```typescript
queryFn: async ({ signal }) => {
    const response = await fetch(url, { headers, signal });
    // ...
}
```

When a new query starts (because debouncedQuery changed), TanStack Query aborts the previous request.

### Autocomplete UX Flow

1. User clicks "Modify" on EntityCard
2. Edit mode shows UmlsCombobox pre-filled with current `preferred_term`
3. User types → debounce timer starts
4. After 300ms pause, `debouncedQuery` updates → TanStack Query fires
5. If typing continues, previous request is aborted, new timer starts
6. Loading spinner shows during fetch
7. Dropdown displays results with preferred term, CUI, semantic type, SNOMED
8. User selects a result → CUI + SNOMED + preferred term all populate
9. User can manually edit CUI/SNOMED if needed (still editable)
10. User clicks Save → existing mutation sends all fields

### Field Hierarchy

The UX prioritizes UMLS search while preserving manual editing capability:

- **Primary:** Large, prominent UmlsCombobox input
- **Secondary:** Smaller CUI/SNOMED inputs in 2-column grid with muted background
- **Visual cue:** `bg-muted/50` signals "auto-populated, but editable if needed"

## Success Criteria Met

- ✅ Typing 3+ characters triggers debounced UMLS search with loading indicator
- ✅ Autocomplete results show preferred term + CUI + semantic type
- ✅ Selecting a result populates CUI, SNOMED code, and preferred term in EntityCard
- ✅ Typing < 3 chars shows "Type at least 3 characters" message (no search triggered)
- ✅ Build compiles without errors (TypeScript, Biome, production build all pass)
- ✅ Rapid typing only triggers one search (300ms debounce with AbortController cancellation)

## Commits

1. **d3b5ccf**: `feat(25-02): create useUmlsSearch hook with debounce and AbortController`
   - Debounces query by 300ms using useState + useEffect
   - Only triggers search for 3+ character queries
   - TanStack Query with 5-min staleTime, AbortController signal

2. **2cb5f05**: `feat(25-02): create UmlsCombobox and integrate into EntityCard`
   - Autocomplete component using cmdk + Radix Popover
   - Shows preferred term, CUI, semantic type, SNOMED in dropdown
   - EntityCard modify mode uses UmlsCombobox as primary input
   - Auto-populates CUI, SNOMED, preferred term on selection

## Next Steps

This completes Phase 25 (UMLS Concept Search Autocomplete). The entity review workflow now has full UMLS autocomplete:
- Reviewers can search by clinical term instead of manually typing CUI codes
- All grounding fields (CUI, SNOMED, preferred term) auto-populate from authoritative UMLS data
- Manual override still available for edge cases

Potential future enhancements (not in current roadmap):
- Semantic type filtering dropdown (only show "Clinical Finding" or "Procedure")
- Recent selections history (cache last 5 concepts per session)
- Keyboard shortcuts (Ctrl+K to focus UMLS search)

## Self-Check: PASSED

**Files exist:**
- ✅ apps/hitl-ui/src/hooks/useUmlsSearch.ts
- ✅ apps/hitl-ui/src/components/UmlsCombobox.tsx

**Commits exist:**
- ✅ d3b5ccf (Task 1: useUmlsSearch hook)
- ✅ 2cb5f05 (Task 2: UmlsCombobox + EntityCard integration)

**Verification checks:**
- ✅ TypeScript compilation succeeds (npx tsc --noEmit)
- ✅ Biome linting passes (npx biome check)
- ✅ Production build succeeds (npm run build)
- ✅ useUmlsSearch hook imported and used in UmlsCombobox
- ✅ UmlsCombobox imported and used in EntityCard
- ✅ 300ms debounce present in hook
- ✅ 3-character minimum check present
- ✅ staleTime caching configured
