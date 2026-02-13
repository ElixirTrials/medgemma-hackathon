# Pitfalls Research

**Domain:** Adding structured field mapping editor to existing HITL review system
**Researched:** 2026-02-13
**Confidence:** HIGH

## Critical Pitfalls

### Pitfall 1: Form State Explosion from Nested Field Mappings

**What goes wrong:**
When adding structured field mapping (entity → relation → value triplets with units, min/max, temporal constraints), developers create separate useState hooks for each field. With multiple mappings per criterion, this creates 10+ state variables per card, leading to synchronization bugs where one field updates but related fields don't (e.g., relation changes from "=" to "range" but min/max fields aren't initialized).

**Why it happens:**
The existing CriterionCard uses simple useState for text/type/category (3 fields). Developers extend this pattern naively for structured mappings without recognizing that field mappings are complex nested objects requiring coordinated state transitions. The spread operator only performs shallow merges, causing nested object updates to lose sibling properties.

**How to avoid:**
Use useReducer with discriminated action types for the entire field mapping structure. Define a single state shape containing all mappings as an array, where each action (ADD_MAPPING, UPDATE_ENTITY, UPDATE_RELATION, UPDATE_VALUE) updates the entire mapping atomically. Use Immer or immutable update patterns for nested objects to ensure all related fields update together.

**Warning signs:**
- More than 5 useState hooks in edit mode component
- Separate handlers for related fields (e.g., handleEntityChange, handleRelationChange, handleValueChange)
- Manual synchronization logic between fields (useEffect watching one field to update another)
- Bug reports: "Changed relation to 'range' but min/max fields stayed disabled"

**Phase to address:**
Phase that introduces structured field mapping editor (form state architecture design)

---

### Pitfall 2: PDF Scroll-to-Source Coordinate Mismatch

**What goes wrong:**
Click on criterion → PDF scrolls to wrong page or wrong location. This happens because react-pdf and similar libraries require page-level coordinates (page index + x/y offset within page), but criterion data stores document-level positions (character offset or absolute coordinates). Developers use scrollTop without accounting for page breaks, zoom level, or coordinate system transforms.

**Why it happens:**
The existing PDF viewer renders pages but doesn't expose a coordinate API. Developers assume scrolling is like HTML (just set scrollTop), not realizing PDFs have a separate coordinate system per page. Extraction doesn't store page-level coordinates—just text spans. No utility exists to convert document position → (pageIndex, offsetX, offsetY).

**How to avoid:**
- Store page_number and page_coordinates during extraction (not just text spans)
- Use react-pdf-viewer's jumpToDestination or scrollToPage with page index
- If using windowToPage coordinate transforms, account for zoom level and viewport transforms
- Test with multi-column layouts and pages with different dimensions
- Store bounding boxes (x, y, width, height, page) for each criterion during extraction

**Warning signs:**
- Extraction data has text spans but no page_number field
- Scroll implementation uses document.getElementById().scrollIntoView() on PDF viewer container
- Coordinate calculations don't account for page.getViewport().scale
- Bug reports: "Works on first page, breaks on page 2"
- No testing with zoomed-in PDF viewer

**Phase to address:**
Phase that adds scroll-to-source feature (extraction schema update + frontend integration)

---

### Pitfall 3: UMLS Autocomplete Network Waterfall

**What goes wrong:**
User types "acet..." in entity field → 6 sequential API calls (one per keystroke) → results arrive out-of-order → UI shows results for "ac" after showing results for "acet" → user selects wrong term. With 300-500ms API latency, this creates 2-3 second lag and flickering results.

**Why it happens:**
Developers add onChange → fetch(query) without debouncing. UMLS API has ~300-500ms latency. Race conditions occur: requests sent as "a", "ac", "ace", "acet" but responses arrive as "a", "ace", "a", "acet". No request cancellation, so all 6 requests complete even though only the last is relevant.

**How to avoid:**
- Debounce UMLS queries with 300ms delay (user stops typing before search triggers)
- Cancel in-flight requests when new query starts (AbortController)
- Show loading spinner during search, disable selection until results load
- Cache results client-side (TanStack Query with staleTime: 5 minutes)
- For queries <3 characters, don't search (show "Type 3+ characters" message)
- Use query ID to detect stale responses: if responseId < currentQueryId, discard results

**Warning signs:**
- No useDebounce or useDebouncedValue hook
- fetch() calls in onChange handler without AbortController
- No loading state between typing and results
- No minimum query length check
- Bug reports: "Autocomplete shows old results", "Results flicker while typing"
- Network tab shows 10+ overlapping UMLS requests

**Phase to address:**
Phase that adds UMLS autocomplete to entity editor (API integration design)

---

### Pitfall 4: Backwards Compatibility Explosion with Review Data

**What goes wrong:**
Existing reviews have modified_text/modified_type/modified_category. New system adds modified_field_mappings. Old reviews break in new UI because code expects field_mappings but finds null. Migrations add empty arrays, but business logic can't distinguish "user approved empty mappings" from "mappings not reviewed yet". Audit trail loses fidelity: before/after comparisons show "[old format]" vs "[new format]" instead of actual changes.

**Why it happens:**
Developers add modified_field_mappings column with default [], assuming empty array = "no mappings". But existing reviews (approved before feature launch) have null because they were never edited with the new UI. No migration strategy for converting modified_text → modified_field_mappings. Audit logs store raw JSON without version markers, so old reviews can't be displayed correctly.

**How to avoid:**
- Dual-write pattern: new reviews write both modified_text (legacy) and modified_field_mappings (new)
- Migration: backfill review_format_version = 'v1_text_only' for existing reviews
- UI checks version: if v1_text_only, show text editor; if v2_field_mappings, show structured editor
- Audit logs include schema_version field so comparisons use correct format
- Display layer converts v1 → v2 format read-only (don't mutate old reviews, just display them)
- API accepts both formats: /review accepts modified_text OR modified_field_mappings

**Warning signs:**
- Migration only adds column with default value (no version marker)
- No handling for null vs. [] distinction
- Existing review pages crash with "Cannot read property 'length' of null"
- Audit log comparisons show "[object Object]" instead of readable diffs
- No strategy for displaying old reviews in new UI
- Bug reports: "Approved reviews now show as 'Pending' after deploy"

**Phase to address:**
Phase that defines review data schema and migration strategy (before implementing editor)

---

### Pitfall 5: Progressive Disclosure State Leak Between Steps

**What goes wrong:**
3-step editing flow: (1) select entity → (2) select relation → (3) enter value. User selects "age" entity, chooses "range" relation, enters min=18/max=65. User clicks back to step 2, changes relation to ">=". Step 3 still shows min/max fields with 18/65 instead of single value field. User saves, backend receives {relation: ">=", value: null, min: 18, max: 65}—invalid data.

**Why it happens:**
Each step sets partial state (entityState, relationState, valueState) but steps don't reset dependent state. Relation change (step 2) should clear valueState (step 3), but developer forgets cleanup. UI conditionally renders fields based on relation but doesn't clear stale values. Backend validation catches invalid combinations, but user loses work.

**How to avoid:**
- Use reducer with explicit state transitions: EDIT_RELATION action clears all value-related fields
- Define allowed state shapes: StandardValue {value}, RangeValue {min, max}, TemporalValue {value, unit}
- Use discriminated unions so TypeScript enforces value shape matches relation type
- Step components receive only their slice of state (no direct access to sibling steps)
- Validation at each step: can't advance from step 2 until step 3 state is initialized correctly
- Reset button on each step clears forward steps (back from step 3 → step 2 resets step 3)

**Warning signs:**
- State setters called directly in step components without going through reducer
- No cleanup logic when relation changes (no useEffect watching relation to reset value fields)
- Backend validation errors like "range relation requires min and max"
- TypeScript allows {relation: ">=", min: 10} (should be impossible type)
- User bug reports: "Changed my mind in step 2, but step 3 still had old values"

**Phase to address:**
Phase that implements multi-step field editor (state machine design)

---

### Pitfall 6: Rationale Textarea Orphaned from Review Action

**What goes wrong:**
User modifies field mappings, fills rationale textarea with "Corrected age range based on protocol section 4.2", clicks Cancel instead of Save. Later edits same criterion, rationale textarea still contains old text. User clicks Save without noticing, ships stale rationale that doesn't match current edits. Audit trail shows rationale for edit A attached to edit B.

**Why it happens:**
Rationale state lives in local component state, not tied to the specific edit transaction. Cancel clears form state (entity/relation/value) but forgets to clear rationale. No unique edit session ID linking rationale to form state. Developers assume user won't click Cancel, so don't implement cleanup.

**How to avoid:**
- Rationale must be part of the same reducer state as field mappings
- Cancel action resets entire state including rationale (all or nothing)
- Rationale validation: can't save if rationale is empty or unchanged from placeholder
- Edit session ID: each time user enters edit mode, generate new ID. Rationale tied to session.
- Confirmation dialog on Cancel: "You have unsaved changes including a rationale. Discard?"
- Backend validation: reject review actions without rationale (or with empty string)

**Warning signs:**
- Rationale textarea uses separate useState(editRationale) from form state
- Cancel handler clears form fields but not rationale
- No confirmation dialog on Cancel when rationale has content
- Backend accepts empty rationale string
- Bug reports: "My rationale from yesterday appeared in today's edit"

**Phase to address:**
Phase that implements rationale capture (edit workflow design)

---

### Pitfall 7: Evidence Linking Without Source Text Stability

**What goes wrong:**
User clicks "Age: ≥18 years" in PDF → entity field pre-fills with "18" and stores evidence pointer {page: 2, text: "Age: ≥18 years", char_start: 850, char_end: 865}. Protocol gets re-extracted with new PDF (corrected version) → text at char_start:850 is now "Prior cancer history" (paragraph shifted up). Evidence pointer broken, user sees wrong highlighted text.

**Why it happens:**
Evidence pointers store character offsets, which are fragile to document changes. Developers assume protocol PDFs never change, but protocols get amended, corrected versions uploaded, or re-extracted with improved parsing. No content hash to detect when PDF changed. No warning in UI that evidence pointer may be stale.

**How to avoid:**
- Store content hash of protocol PDF with each evidence pointer
- On review load, check protocol.current_hash == evidence.protocol_hash
- If hashes differ, show warning badge: "Protocol updated since evidence was captured"
- Store actual text snippet: evidence.captured_text = "Age: ≥18 years"
- On review load, fuzzy match captured_text against protocol to find new position
- If match found, update pointer silently; if no match, show "Evidence not found in current version"
- Allow user to re-capture evidence from updated protocol

**Warning signs:**
- Evidence pointers use only char_start/char_end (no content hash)
- No version/hash stored with protocol
- No handling for missing evidence pointers
- Bug reports: "Clicked evidence link, highlighted wrong text"
- No testing with amended protocols

**Phase to address:**
Phase that implements evidence linking (extraction schema + review data model)

---

### Pitfall 8: UMLS Autocomplete Without Offline Fallback

**What goes wrong:**
User in field clinic with intermittent network. Types "diabetes" in entity field → autocomplete shows spinner → 30 second timeout → error message → can't complete review. No way to manually enter UMLS code if autocomplete fails. User forced to skip entity grounding, reducing data quality.

**Why it happens:**
Developers assume 100% network availability (desktop office environment). UMLS autocomplete has no offline cache or fallback to manual entry. No progressive enhancement: field is completely disabled until autocomplete loads. No recent searches cache for common terms.

**How to avoid:**
- Cache last 100 UMLS searches in localStorage/IndexedDB
- On network error, show cached results with "(cached)" badge
- Always show "Manual entry" option below autocomplete
- Manual entry: separate text inputs for CUI, SNOMED code, preferred term
- Save draft reviews to localStorage (offline-first pattern)
- On reconnect, sync drafts to server
- Show network status indicator: "Working offline - 3 drafts pending sync"

**Warning signs:**
- No error.code === 'NETWORK_ERROR' handling in autocomplete
- No localStorage caching
- Autocomplete is only way to enter entity codes (no manual fallback)
- No offline testing in development
- Bug reports: "Can't review when VPN drops"

**Phase to address:**
Phase that implements UMLS autocomplete (network resilience design)

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Skip field mapping migrations, just add modified_field_mappings column | Ships feature 2 days faster | Old reviews break in new UI, audit trail loses fidelity, rollback requires data backfill | Never—breaks production data |
| Use useState for field mappings instead of useReducer | Less code (20 lines vs 60) | State synchronization bugs, impossible to add undo/redo, hard to test | Never for complex forms with 5+ related fields |
| Debounce UMLS queries but skip request cancellation | 80% of UX improvement for 20% effort | Race conditions show stale results 1% of time, confusing users | Acceptable for MVP if documented as known issue |
| Store evidence as char_start/char_end without content hash | Simpler data model (2 fields vs 4) | Breaks when protocols updated, no way to detect staleness | Acceptable if protocols never change (rare) |
| Skip rationale validation, trust user to fill it | No backend changes needed | Audit trail has gaps, compliance issues if audited | Never for regulated domains (clinical trials) |
| No offline cache for UMLS, require network | Standard React Query pattern | Field users can't complete reviews, data quality drops | Acceptable for desktop-only office environments |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| react-pdf viewer scroll | Use scrollTop on container div (treats PDF like HTML) | Use jumpToDestination(pageIndex, offsetX, offsetY) with page-level coordinates |
| UMLS Terminology Service | Search on every keystroke without debounce | Debounce 300ms + AbortController + cache results with TanStack Query |
| PostgreSQL JSONB updates | UPDATE criteria SET modified_field_mappings = '{}' (loses nested data) | Use jsonb_set or ORM-level merge to preserve nested structure |
| TanStack Query mutations | Don't handle rollback on error | Implement onMutate rollback: save old state, restore on error |
| Evidence text selection | Store only Selection.toString() (loses position) | Store Range with page, char_start, char_end, actual text snippet |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| No UMLS query caching | Same term searched 50x in one session, network latency every time | TanStack Query with staleTime: 5min, gcTime: 30min | 10+ reviews in one session |
| Render all field mapping rows | Edit mode slow to open with 10+ mappings per criterion | Virtualize list with react-window if >5 mappings | >5 field mappings per criterion |
| No optimistic updates | Every Save button click waits 500ms for server | Optimistic update: update UI immediately, rollback on error | Users notice 500ms lag |
| PDF re-renders on every scroll | Scrolling to evidence position re-renders entire PDF | Memoize PDF component, only re-render on page change | PDFs >20 pages |
| No form state memoization | Every keystroke in value field re-renders entire card | Memoize field components, update only changed fields | Forms with >10 fields |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Store rationale in localStorage without encryption | PHI exposure if device stolen (clinical trial data is protected) | Don't cache rationale; if offline mode required, use encrypted IndexedDB |
| No CSRF protection on review mutations | Attacker tricks reviewer into approving malicious edits | Backend requires CSRF token + SameSite cookies |
| Evidence pointers expose full protocol text in API | User downloads protocol they shouldn't have access to | API returns only highlighted snippet, not full page text |
| No rate limiting on UMLS autocomplete | Attacker scrapes entire UMLS database via autocomplete API | Rate limit: 20 requests/minute per user |
| Client-side validation only | User bypasses UI, sends invalid field_mappings to API | Backend validates relation + value shape matches schema |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Hide rationale textarea until user clicks "Add rationale" | 60% of users forget rationale, submit without it | Always visible, marked required with red border |
| No confirmation on Cancel when form has unsaved changes | User loses 5 minutes of careful field mapping work | "You have unsaved changes. Discard?" confirmation dialog |
| Autocomplete results show CUI codes only | User sees "C0011849" instead of "diabetes mellitus", can't recognize correct term | Show preferred term first, CUI in smaller grey text |
| No loading state during UMLS search | User types, nothing happens for 2 seconds, thinks it's broken | Spinner + "Searching..." text immediately on typing |
| Progressive disclosure hides all steps until previous completes | User can't see overview of what they need to fill | Show all steps, but disable/grey out future steps until previous completes |
| Evidence highlight disappears on scroll | User scrolls PDF to verify, highlight gone, can't find context again | Persistent highlight with "Jump to evidence" button |
| No "undo" for field mapping changes | User accidentally deletes mapping, has to re-enter entire triplet | Undo/redo stack with Cmd+Z/Cmd+Shift+Z |

## "Looks Done But Isn't" Checklist

- [ ] **UMLS Autocomplete:** Often missing debounce, request cancellation, cache — verify no race conditions in Network tab, test rapid typing
- [ ] **PDF Scroll-to-Source:** Often missing page coordinate transform — verify with multi-page PDFs, zoomed viewer, multi-column layouts
- [ ] **Field Mapping State:** Often missing relation → value cleanup — verify changing relation from "range" to "=" clears min/max fields
- [ ] **Rationale Capture:** Often missing Cancel cleanup — verify Cancel after typing rationale clears textarea on next edit
- [ ] **Evidence Linking:** Often missing content hash — verify evidence pointers break gracefully when protocol updated
- [ ] **Backwards Compatibility:** Often missing version marker — verify old reviews (pre-feature) still display correctly
- [ ] **Optimistic Updates:** Often missing rollback — verify network error during Save restores previous state
- [ ] **Form Validation:** Often missing server-side validation — verify can't submit invalid relation+value combinations via API

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Form state explosion (useState instead of useReducer) | MEDIUM | Refactor: create reducer, move all state to single object, add action creators — 4 hours |
| PDF scroll coordinate mismatch | LOW | Add page_number to extraction schema, update scroll logic — 2 hours |
| UMLS autocomplete network waterfall | LOW | Add useDebounce hook, AbortController, TanStack Query cache — 2 hours |
| Backwards compatibility explosion | HIGH | Add schema version, dual-write pattern, migration script, display layer versioning — 8 hours |
| Progressive disclosure state leak | MEDIUM | Refactor: use discriminated unions, add state transitions, step cleanup — 4 hours |
| Rationale orphaned from action | LOW | Move rationale to reducer state, add Cancel confirmation — 1 hour |
| Evidence linking without stability | HIGH | Add content hash, fuzzy matching, re-capture UI — 6 hours |
| No offline fallback | MEDIUM | Add localStorage cache, manual entry fields, offline indicator — 3 hours |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Form state explosion | Phase defining field mapping editor architecture | Review component has single useReducer, not 10+ useState |
| PDF scroll coordinate mismatch | Phase adding extraction schema for evidence | Extraction stores page_number + coordinates, test scroll on multi-page PDF |
| UMLS autocomplete waterfall | Phase implementing UMLS integration | Network tab shows <3 requests per search, no overlapping requests |
| Backwards compatibility explosion | Phase defining review data migration strategy | Old reviews display correctly, audit log readable, no null pointer crashes |
| Progressive disclosure state leak | Phase implementing 3-step editor | Changing relation from "range" to "=" clears min/max fields |
| Rationale orphaned from action | Phase implementing rationale capture | Cancel after typing rationale clears textarea on next edit |
| Evidence linking instability | Phase implementing evidence capture | Evidence has content hash, shows warning when protocol updated |
| No offline fallback | Phase implementing UMLS autocomplete | Works offline with cached results, manual entry available |

## Sources

### React State Management
- [Managing State – React](https://react.dev/learn/managing-state)
- [Complex State Management in React - Telerik](https://www.telerik.com/blogs/complex-state-management-react)
- [Managing Complex State in React with useReducer - Aleksandr Hovhannisyan](https://www.aleksandrhovhannisyan.com/blog/managing-complex-state-react-usereducer/)
- [State Management in 2026 - Nucamp](https://www.nucamp.co/blog/state-management-in-2026-redux-context-api-and-modern-patterns)

### PDF Viewer Integration
- [react-pdf-highlighter-extended - GitHub](https://github.com/DanielArnould/react-pdf-highlighter-extended)
- [React PDF Viewer scrollToPage - KendoReact](https://www.telerik.com/kendo-react-ui/components/pdfviewer/api/scrolltopage)
- [Programmatically scroll/change page - react-pdf-viewer Issue #491](https://github.com/react-pdf-viewer/react-pdf-viewer/issues/491)

### Autocomplete & Debouncing
- [Debounce Your Search - Atomic Object](https://spin.atomicobject.com/automplete-timing-debouncing/)
- [Autocomplete Pattern - GreatFrontEnd](https://www.greatfrontend.com/questions/system-design/autocomplete)
- [How to debounce in React - Developer Way](https://www.developerway.com/posts/debouncing-in-react)

### Database Migrations
- [Backward Compatible Database Changes - PlanetScale](https://planetscale.com/blog/backward-compatible-databases-changes)
- [Database Design Patterns for Backward Compatibility - PingCAP](https://www.pingcap.com/article/database-design-patterns-for-ensuring-backward-compatibility/)
- [Backward-Compatible Schema Migrations - With a Twist](https://withatwist.dev/backward-compatible-database-migrations.html)

### HITL Systems
- [Human-in-the-Loop AI - Best Practices & Pitfalls - Parseur](https://parseur.com/blog/hitl-best-practices)
- [Human in the Loop UX - Enterprise AI Design - aufait UX](https://www.aufaitux.com/blog/human-in-the-loop-ux/)

### Progressive Disclosure
- [Progressive Disclosure - Nielsen Norman Group](https://www.nngroup.com/articles/progressive-disclosure/)
- [Progressive Disclosure in UX Design - LogRocket](https://blog.logrocket.com/ux-design/progressive-disclosure-ux-types-use-cases/)

### UMLS Integration
- [Terminology Service Updates in Medplum v5](https://www.medplum.com/blog/v5-terminology)
- [UMLS Terminology Services - NLM](https://uts.nlm.nih.gov/)

### Optimistic Updates
- [Optimistic Updates - TanStack Query](https://tanstack.com/query/v4/docs/framework/react/guides/optimistic-updates)
- [Concurrent Optimistic Updates - TkDodo](https://tkdodo.eu/blog/concurrent-optimistic-updates-in-react-query)

### Audit Trails
- [Audit Trail Requirements - HybridForms](https://www.hybridforms.net/en/audit-trail/)
- [Audit Trail Complete Guide 2025 - Mysa](https://www.mysa.io/glossary/audit-trail)

---
*Pitfalls research for: Adding structured field mapping editor to existing HITL review system*
*Researched: 2026-02-13*
