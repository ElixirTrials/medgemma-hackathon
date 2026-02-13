# Requirements: v1.5 Structured Criteria Editor

**Defined:** 2026-02-13
**Core Value:** Clinical researchers can edit AI-extracted criteria using structured field mapping (entity/relation/value) with UMLS grounding and evidence linking to protocol source text.

## v1.5 Requirements

### EDIT — Structured Field Mapping Editor

- [ ] **EDIT-01**: Reviewer can toggle between text edit and structured edit modes on a criterion
- [ ] **EDIT-02**: Structured editor displays entity/relation/value triplet fields for each criterion
- [ ] **EDIT-03**: Relation dropdown offers full operator set (=, !=, >, >=, <, <=, within, not_in_last, contains, not_contains)
- [ ] **EDIT-04**: Value input adapts based on relation type — single value for standard operators, min/max for range, duration+unit for temporal
- [ ] **EDIT-05**: Reviewer can save structured edits via existing modify action workflow
- [ ] **EDIT-06**: Structured edits persist to database and display correctly after page refresh
- [ ] **EDIT-07**: Existing text-only reviews (pre-v1.5) continue to display correctly in the UI

### UMLS — UMLS/SNOMED Concept Search

- [ ] **UMLS-01**: Entity field in structured editor provides autocomplete search via UMLS MCP concept_search
- [ ] **UMLS-02**: Autocomplete results show preferred term + CUI code + semantic type
- [ ] **UMLS-03**: Search debounced (300ms minimum) with loading indicator
- [ ] **UMLS-04**: Minimum 3 characters required before search triggers
- [ ] **UMLS-05**: Selecting a UMLS concept populates entity fields (CUI, SNOMED code, preferred term)

### MULTI — Multi-Mapping Support

- [ ] **MULTI-01**: Reviewer can add multiple field mappings to a single criterion
- [ ] **MULTI-02**: Reviewer can remove individual field mappings from a criterion
- [ ] **MULTI-03**: Each mapping has independent entity/relation/value fields
- [ ] **MULTI-04**: Backend stores and returns array of field mappings per criterion

### RATL — Rationale Capture

- [ ] **RATL-01**: Rationale text field available when modifying structured fields
- [ ] **RATL-02**: Rationale persisted with the review action in audit log
- [ ] **RATL-03**: Cancel clears rationale along with all other form state

### EVID — Evidence Linking (PDF Scroll-to-Source)

- [ ] **EVID-01**: Clicking a criterion scrolls the PDF viewer to the source page
- [ ] **EVID-02**: Source text highlighted or visually indicated in PDF viewer
- [ ] **EVID-03**: Extraction service captures page number for each extracted criterion
- [ ] **EVID-04**: Evidence linking degrades gracefully when page data is unavailable

### API — Backend API Extensions

- [ ] **API-01**: ReviewActionRequest accepts optional modified_structured_fields (backward compatible)
- [ ] **API-02**: _apply_review_action() updates temporal_constraint, numeric_thresholds, and conditions from structured fields
- [ ] **API-03**: Audit log captures before/after values for structured field changes
- [ ] **API-04**: UMLS search proxy endpoint available for frontend autocomplete

## v1.6 Requirements (Deferred)

### AI — AI-Assisted Field Suggestions

- **AI-01**: User can select text in PDF and trigger AI field suggestion
- **AI-02**: MedGemma extracts entities from selected text and suggests triplet values
- **AI-03**: AI suggestions display with confidence indicators
- **AI-04**: User can accept, modify, or reject AI suggestions

### UX — Advanced UX Enhancements

- **UX-01**: Undo/redo for field mapping changes within an edit session
- **UX-02**: Inline UMLS validation feedback (real-time code verification)
- **UX-03**: Interactive SNOMED hierarchy browser for entity selection

## Out of Scope

| Feature | Reason |
|---------|--------|
| Bulk edit for all criteria | Breaks audit trail; can't track per-criterion reviewer decisions |
| Real-time collaborative editing | Conflict resolution complexity; clinical review requires single reviewer per decision |
| Free-text relation field | Breaks structured export; standardized operator set required |
| Custom UMLS code without validation | Allows invalid codes into database; violates audit requirements |
| Offline-first with IndexedDB | Desktop-only pilot environment; acceptable to require network |
| Required rationale validation | User chose optional rationale for v1.5; can tighten in v1.6 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| API-01 | Phase 22 | Pending |
| API-02 | Phase 22 | Pending |
| API-03 | Phase 22 | Pending |
| API-04 | Phase 25 | Pending |
| EDIT-01 | Phase 24 | Pending |
| EDIT-02 | Phase 23 | Pending |
| EDIT-03 | Phase 23 | Pending |
| EDIT-04 | Phase 23 | Pending |
| EDIT-05 | Phase 24 | Pending |
| EDIT-06 | Phase 24 | Pending |
| EDIT-07 | Phase 22 | Pending |
| UMLS-01 | Phase 25 | Pending |
| UMLS-02 | Phase 25 | Pending |
| UMLS-03 | Phase 25 | Pending |
| UMLS-04 | Phase 25 | Pending |
| UMLS-05 | Phase 25 | Pending |
| MULTI-01 | Phase 27 | Pending |
| MULTI-02 | Phase 27 | Pending |
| MULTI-03 | Phase 27 | Pending |
| MULTI-04 | Phase 27 | Pending |
| RATL-01 | Phase 26 | Pending |
| RATL-02 | Phase 26 | Pending |
| RATL-03 | Phase 26 | Pending |
| EVID-01 | Phase 28 | Pending |
| EVID-02 | Phase 28 | Pending |
| EVID-03 | Phase 28 | Pending |
| EVID-04 | Phase 28 | Pending |

**Coverage:**
- v1.5 requirements: 27 total
- Mapped to phases: 27
- Unmapped: 0

---
*Requirements defined: 2026-02-13*
*Last updated: 2026-02-13 after v1.5 milestone definition*
