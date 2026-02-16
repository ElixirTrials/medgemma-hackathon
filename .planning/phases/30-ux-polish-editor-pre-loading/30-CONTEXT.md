# Phase 30: UX Polish & Editor Pre-Loading - Context

**Gathered:** 2026-02-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Essential UX improvements for the review workflow: visual review status distinction, rationale for reject actions, criteria search/filter, section sorting with headers, editor pre-loading from saved data, and read-mode structured mini-cards for field mappings. Frontend-only work running parallel with Phase 31.

</domain>

<decisions>
## Implementation Decisions

### Review status visuals
- Left border color to distinguish status: green=approved, red/orange=rejected, yellow=pending (three states)
- No rationale prompt for approve actions — approve is one click
- Reject shows a popup with predefined reason checkboxes (multi-select): "Not a criteria", "Incorrect entity grounding", "Poor splitting into composites", etc. — plus optional free-text
- Modify retains existing rationale pattern

### Section sorting & headers
- Bold headers with review progress count: "Inclusion Criteria (8/12 reviewed)", "Exclusion Criteria (3/8 reviewed)"
- Inclusion section first, then Exclusion
- Within each section: pending criteria first, then reviewed
- Uncategorized criteria go into a "To be sorted" panel where the reviewer must assign as inclusion, exclusion, modify, or reject
- "To be sorted" panel appears at the top if any uncategorized criteria exist

### Search & filtering
- Sticky search/filter bar above criteria sections
- Text search plus filter dropdowns for: status (pending/reviewed/all), type (inclusion/exclusion), confidence level
- Client-side filtering (instant, on already-loaded data)
- Show/hide non-matching cards (no text highlighting)
- Debounced text input (300ms)

### Field mapping display
- Structured mini-cards in read mode showing entity/relation/value per mapping
- Mini-cards are clickable — clicking opens the structured editor focused on that mapping
- All saved mappings load when entering modify mode (not just the clicked one)
- Each criterion should display one or more entity/relation/value rows with a modifiable composite connector (AND/OR) between them — lowest cognitive load
- Design assumption: AI will pre-populate suggested field mappings for most criteria (extraction-side work is deferred to Phase 31/32)

### Claude's Discretion
- Exact chip/card styling for field mapping mini-cards
- Debounce timing for filters
- Animation/transition when filtering cards
- Exact placement of "To be sorted" panel

</decisions>

<specifics>
## Specific Ideas

- Reject reasons should be predefined checkboxes: "Not a criteria", "Incorrect entity grounding", "Poor splitting into composites" — plus optional free-text for other reasons
- Every criterion should have AI-suggested field mappings to reduce reviewer clicks/edits — even low-confidence suggestions are better than empty
- Composite criteria should show triplet rows joined by modifiable AND/OR connectors

</specifics>

<deferred>
## Deferred Ideas

- AI auto-generating field mappings during extraction (pipeline-side work for Phase 31/32)
- Server-side search for scaling to very large batches

</deferred>

---

*Phase: 30-ux-polish-editor-pre-loading*
*Context gathered: 2026-02-16*
