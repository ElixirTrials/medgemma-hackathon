# Project Research Summary

**Project:** v1.5 Structured Criteria Editor with Evidence Linking
**Domain:** Clinical trial HITL review system enhancement
**Researched:** 2026-02-13
**Confidence:** HIGH

## Executive Summary

The v1.5 milestone extends the existing HITL review system with structured field mapping capabilities inspired by Cauldron's progressive disclosure pattern. This is a form complexity upgrade: moving from simple text editing to entity-relation-value triplets with UMLS grounding, adaptive value inputs (single/range/temporal), and PDF evidence linking. The existing stack (React 18 + Vite, Tailwind, Radix UI, TanStack Query, react-hook-form, react-pdf) requires ZERO new dependencies—all capabilities are achievable with current packages.

The recommended approach follows existing architecture patterns: extend ReviewActionRequest with `modified_structured_fields`, replace CriterionCard's simple textarea with a StructuredFieldEditor component using React Hook Form's useReducer + useFieldArray pattern, and add imperative scroll methods to PdfViewer using react-pdf's text layer APIs. This is NOT a greenfield feature—it's an inline enhancement to the existing review workflow, maintaining backward compatibility with v1.4 text-only reviews.

The primary risk is form state explosion (10+ fields with nested structures) leading to synchronization bugs. Mitigation: use useReducer with discriminated action types rather than multiple useState hooks, implement proper state cleanup when relation changes (range → equals should clear min/max fields), and validate form state at each step. Secondary risks include PDF scroll coordinate mismatches (mitigated by storing page_number + coordinates during extraction), UMLS autocomplete network waterfalls (mitigated by 300ms debouncing + AbortController), and backwards compatibility issues (mitigated by dual-write pattern with schema versioning).

## Key Findings

### Recommended Stack

**ZERO new npm packages required.** The existing stack fully supports all v1.5 capabilities. Three new features need implementation strategies using current dependencies:

**Core technologies (already installed):**
- **react-hook-form 7.55.0**: Form state management with useFieldArray for dynamic threshold arrays — handles nested structures with validation
- **cmdk 1.1.1 + @radix-ui/react-popover 1.1.6**: UMLS autocomplete UI — cmdk provides command palette functionality, Radix Popover positions dropdown
- **react-pdf 10.3.0**: PDF scroll-to-source via imperative refs — text layer already rendered, use `scrollIntoView()` + `customTextRenderer` for highlights
- **@radix-ui/react-select 2.1.6**: Relation/comparator dropdowns — accessible, keyboard navigable, already integrated with react-hook-form Controller pattern
- **lucide-react 0.487.0**: Icons for UI affordances (CheckCircle, Clock, Hash, etc.)

**Implementation patterns:**
- PDF scroll-to-source: DOM refs + `document.querySelector('[data-page-number="${page}"]')` + native `scrollIntoView()` API
- UMLS autocomplete: TanStack Query hook `useUmlsSearch(query)` calling existing UMLS MCP + cmdk Command.Input with debounced onValueChange
- Adaptive forms: react-hook-form `useWatch` to subscribe to relation field changes, conditional rendering of value inputs

### Expected Features

**Must have (table stakes) — v1.5 launch:**
- Entity → Relation → Value triplet editing — Standard EAV pattern expected in clinical data capture systems
- UMLS/SNOMED concept search with autocomplete — Medical terminology editors require semantic search (SNOMED CT saves 18% keystrokes)
- Adaptive value input (single/range/temporal) — Relation type dictates input structure; prevents data entry errors
- Rationale text field for audit trail — 21 CFR Part 11 compliance requires timestamp + user + reason for all changes
- Multi-mapping support (add/remove) — Complex criteria often have multiple constraints (e.g., "18-65 years AND BMI <30")
- Read-only display of existing structured fields — Already implemented (temporal_constraint, numeric_thresholds badges in CriterionCard)

**Should have (competitive advantage) — v1.6:**
- Evidence linking: click criterion → scroll PDF to source — Regulatory audit requirement; competitors require manual navigation
- AI-assisted field pre-population from selected text — AI coding platforms show 30-70% FTE reduction
- Inline UMLS validation feedback — Real-time validation against UMLS API prevents invalid codes in database
- Visual confidence indicators on AI suggestions — Explainable AI standard for 2026 medical coding compliance

**Defer (v2+):**
- Interactive SNOMED hierarchy browser — UMLS MCP doesn't provide hierarchy; autocomplete sufficient for v1
- Undo/redo for edit sessions — Nice to have but not blocking (add if user testing shows frequent mistakes)
- Batch operations with audit trail — Complex coordination; validate single-item workflow first

### Architecture Approach

The structured field mapping editor integrates as an inline enhancement to the existing ReviewPage → CriterionCard → review action flow. No new API endpoints or database tables required—extend ReviewActionRequest with `modified_structured_fields` (optional JSON field), update `_apply_review_action()` to handle structured updates, and use existing JSONB columns (temporal_constraint, numeric_thresholds, conditions) for storage. Frontend state management uses React Hook Form for complex nested forms, TanStack Query for server sync (no new Zustand store needed), and prop-driven PDF highlighting (no global state).

**Major components:**
1. **StructuredFieldEditor** — Replaces simple textarea in CriterionCard edit mode; uses useReducer + useFieldArray for threshold arrays; renders sub-components (TemporalConstraintFields, NumericThresholdsFields, ConditionsFields)
2. **CriterionCard (extended)** — Adds edit mode toggle (text vs structured); handles structured save callback; passes criterion data to editor
3. **PdfViewer (enhanced)** — Adds imperative `scrollToText(page, startChar, endChar)` method using DOM refs; highlights text via customTextRenderer prop
4. **UMLS autocomplete integration** — TanStack Query hook `useUmlsSearch()` proxies to existing UMLS MCP; UI uses cmdk + Radix Popover for dropdown

### Critical Pitfalls

1. **Form State Explosion** — Multiple useState hooks for nested field mappings (entity/relation/value/unit/min/max) lead to synchronization bugs (relation changes from "=" to "range" but min/max fields don't initialize). Prevention: Use useReducer with discriminated action types; single state shape for all mappings; explicit state transitions (EDIT_RELATION clears value fields).

2. **PDF Scroll Coordinate Mismatch** — Click criterion → PDF scrolls to wrong page/location because extraction stores text spans without page numbers, and developers use HTML scrollTop instead of PDF page-level coordinates. Prevention: Store page_number + page_coordinates during extraction; use react-pdf's page-aware scroll APIs; test with multi-page PDFs, zoom, multi-column layouts.

3. **UMLS Autocomplete Network Waterfall** — User types "acet..." → 6 sequential API calls (one per keystroke) → results arrive out-of-order → UI shows stale results. Prevention: Debounce 300ms + AbortController for in-flight requests + TanStack Query cache (staleTime: 5min) + no search for queries <3 chars.

4. **Backwards Compatibility Explosion** — Existing reviews have modified_text/modified_type/modified_category; new system adds modified_field_mappings; old reviews crash in new UI expecting field_mappings but finding null. Prevention: Dual-write pattern (write both formats); add review_format_version field; UI checks version to decide which editor to show; audit logs include schema_version.

5. **Progressive Disclosure State Leak** — User selects "age" entity → "range" relation → enters min=18/max=65 → changes relation to ">=" → step 3 still shows min/max fields instead of single value field → saves invalid data. Prevention: Reducer with state transitions; discriminated unions (StandardValue vs RangeValue vs TemporalValue); relation change action explicitly clears value-related fields.

## Implications for Roadmap

Based on research, suggested phase structure for v1.5 milestone:

### Phase 1: Backend Data Model + API Extension
**Rationale:** Foundation must be in place before frontend can submit structured updates. This is low-risk (backward compatible) and unblocks all frontend work.

**Delivers:**
- ReviewActionRequest extended with optional `modified_structured_fields: Dict[str, Any]` field
- `_apply_review_action()` updated to handle temporal_constraint, numeric_thresholds, conditions updates
- Integration tests for structured modify actions
- Backend deployed (backward compatible—field is optional)

**Addresses:**
- Table stakes requirement: ability to persist structured field edits
- Pitfall 4 (backwards compatibility): Establishes dual-write pattern early

**Avoids:**
- Creating separate endpoint (anti-pattern identified in ARCHITECTURE.md)
- Breaking existing text-only modify flow

**Research flags:** SKIP — Straightforward Pydantic model extension + SQLModel JSONB updates, no complex integration

---

### Phase 2: Core Structured Editor Component
**Rationale:** Builds the foundational form component with all field types before integrating into review workflow. Allows isolated testing of form state management patterns.

**Delivers:**
- StructuredFieldEditor.tsx component with useForm + useFieldArray
- Sub-components: TemporalConstraintFields, NumericThresholdsFields, ConditionsFields
- Radix UI Select wrappers for relation/comparator dropdowns
- Form validation with Zod schema
- Storybook stories for all field types and states

**Uses:**
- react-hook-form 7.55.0 (already in package.json)
- @radix-ui/react-select 2.1.6 (already in package.json)

**Implements:**
- ARCHITECTURE.md "Inline Structured Editor" pattern
- State management via useReducer to avoid Pitfall 1 (form state explosion)
- Discriminated unions to avoid Pitfall 5 (state leak between steps)

**Avoids:**
- Using separate useState for each field (documented anti-pattern)
- Modal/drawer pattern (keeps context visible per ARCHITECTURE.md)

**Research flags:** SKIP — React Hook Form useFieldArray pattern is well-documented, Radix UI integration is standard

---

### Phase 3: CriterionCard Integration + Review Workflow
**Rationale:** Wires structured editor into existing review flow with minimal disruption. Enables end-to-end testing of structured modify actions.

**Delivers:**
- Edit mode toggle in CriterionCard (text vs structured)
- Conditional rendering: simple textarea OR StructuredFieldEditor
- handleStructuredSave callback wiring to existing onAction handler
- TypeScript types updated in useReviews.ts (ReviewActionRequest interface)
- End-to-end test: edit structured fields → save → verify persistence

**Addresses:**
- Table stakes: users can edit and save structured fields
- Extends existing approve/reject/modify workflow (no new actions)

**Implements:**
- ARCHITECTURE.md "Extend Existing Request Model" pattern
- Integration with existing TanStack Query mutation (useReviewAction)

**Avoids:**
- Creating new Zustand store (form state is local per ARCHITECTURE.md)

**Research flags:** SKIP — Follows established CriterionCard edit pattern (text/type/category already implemented)

---

### Phase 4: UMLS Concept Search Autocomplete
**Rationale:** Enhances entity field with semantic search. Dependent on Phase 3 (structured editor must exist). High user value but isolated feature (no dependencies from other phases).

**Delivers:**
- useUmlsSearch TanStack Query hook (debounced, cached)
- UmlsCombobox component (cmdk + Radix Popover)
- Entity field replaced with autocomplete in StructuredFieldEditor
- AbortController for in-flight request cancellation
- Loading states + error handling

**Uses:**
- cmdk 1.1.1 (already in package.json)
- @radix-ui/react-popover 1.1.6 (already in package.json)
- Existing UMLS MCP integration (concept_search tool)

**Addresses:**
- Table stakes: UMLS/SNOMED autocomplete (18% keystroke savings)
- FEATURES.md differentiator: semantic search vs flat text input

**Avoids:**
- Pitfall 3 (network waterfall): 300ms debounce + AbortController
- Separate autocomplete library (cmdk already available per STACK.md)

**Research flags:** SKIP — cmdk + Radix Popover pattern documented in shadcn/ui examples, debouncing is standard React pattern

---

### Phase 5: Rationale Capture + Audit Trail Enhancement
**Rationale:** Compliance requirement for 21 CFR Part 11. Must be tied to review actions but separate feature from field mapping logic.

**Delivers:**
- Rationale textarea added to StructuredFieldEditor
- Required validation: can't save modify action without rationale
- Rationale included in ReviewActionRequest.comment field (or new rationale field)
- Audit log displays rationale for structured field changes
- Cancel confirmation dialog when rationale has content

**Addresses:**
- Table stakes: 21 CFR Part 11 audit trail requirement (timestamp + user + reason)
- FEATURES.md compliance requirement

**Implements:**
- Rationale as part of reducer state (not separate useState) to avoid Pitfall 6

**Avoids:**
- Rationale orphaned from review action (Pitfall 6)

**Research flags:** SKIP — Simple form field + validation, standard audit trail pattern

---

### Phase 6: Multi-Mapping Support (Add/Remove Mappings)
**Rationale:** Complex criteria often require multiple structured fields (e.g., "18-65 years AND BMI <30"). Builds on Phase 2-5 (editor must work for single mapping first).

**Delivers:**
- useFieldArray for mappings array (not just thresholds within one mapping)
- Add/Remove mapping buttons in StructuredFieldEditor
- Backend handles array of field_mappings in modified_structured_fields
- UI validation: can't add empty mapping, can't remove last mapping
- Visual grouping: cards/borders around each mapping

**Addresses:**
- Table stakes: multi-threshold support for complex criteria
- FEATURES.md differentiator: granular CDISC export via multiple mappings

**Implements:**
- react-hook-form useFieldArray at mapping level (nested array)

**Avoids:**
- Creating separate component for each mapping (use repeater pattern)

**Research flags:** SKIP — useFieldArray is well-documented for nested arrays

---

### Phase 7: PDF Scroll-to-Source (Evidence Linking)
**Rationale:** High-value competitive feature but requires extraction schema updates (page_number, coordinates). Can be added after core editing workflow is validated.

**Delivers:**
- Extraction schema update: add page_number + source_coordinates to Criterion model
- Extraction service stores page/coordinates during PDF parsing
- PdfViewer enhanced with scrollToText(page, startChar, endChar) imperative method
- CriterionCard criterion text click handler
- ReviewPage wires highlight prop to PdfViewer
- Text highlighting via customTextRenderer prop

**Uses:**
- react-pdf 10.3.0 customTextRenderer (already in package.json)
- Native scrollIntoView() API

**Addresses:**
- FEATURES.md differentiator: click criterion → scroll PDF to source
- Competitive advantage: regulatory audit acceleration

**Avoids:**
- Pitfall 2 (coordinate mismatch): Store page_number + page-level coordinates, not document offsets
- react-pdf-highlighter library (heavy dependency per STACK.md anti-patterns)

**Research flags:** REQUIRES RESEARCH — Extraction service needs investigation for how to capture page numbers and bounding boxes during multimodal extraction; coordinate transform logic for react-pdf text layer may need experimentation

---

### Phase 8: AI-Assisted Field Suggestions (v1.6 feature, optional)
**Rationale:** Deferred to v1.6—validates manual workflow first before adding AI assistance. High complexity (MedGemma integration, text selection handling).

**Delivers:**
- Text selection handler in PdfViewer
- POST /api/suggest-fields endpoint (MedGemma entity extraction + UMLS MCP)
- "Suggest Fields" button in StructuredFieldEditor
- AI suggestion cards with confidence indicators
- Accept/Modify/Reject actions for suggestions

**Addresses:**
- FEATURES.md differentiator: AI-assisted field population (30-70% FTE reduction)
- v1.6 competitive advantage

**Deferred rationale:**
- Not blocking for v1.5 launch (manual editing is table stakes)
- Requires text selection UX design
- MedGemma prompt engineering for entity extraction

**Research flags:** REQUIRES RESEARCH — MedGemma entity extraction prompt design, confidence calibration for medical coding domain

---

### Phase Ordering Rationale

- **Phase 1 before all**: Backend must accept structured data before frontend can submit it
- **Phase 2 before 3**: Isolated component development before integration reduces debugging complexity
- **Phase 3 before 4-6**: Core workflow must work before enhancing with autocomplete, rationale, multi-mapping
- **Phase 4-6 parallel-friendly**: UMLS autocomplete, rationale, multi-mapping are independent features (can be built simultaneously if resourced)
- **Phase 7 after 3**: Evidence linking requires extraction schema changes (higher risk); core editing must be validated first
- **Phase 8 deferred to v1.6**: AI assistance not blocking; manual workflow proven before automating

**Dependency graph:**
```
Phase 1 (Backend)
    ↓
Phase 2 (Component)
    ↓
Phase 3 (Integration) ← MINIMUM VIABLE
    ↓
Phase 4, 5, 6 (Enhancements — parallel)
    ↓
Phase 7 (Evidence Linking — requires extraction changes)
    ↓
Phase 8 (AI Assist — v1.6)
```

### Research Flags

**Phases needing deeper research during planning:**
- **Phase 7 (PDF Scroll-to-Source):** Extraction service investigation required—how to capture page numbers and bounding boxes during multimodal extraction? Current extraction returns structured data without coordinates. May need new graph node or modify extract node.
- **Phase 8 (AI Suggestions):** MedGemma prompt engineering for entity extraction from selected text; confidence calibration for medical coding domain; text selection UX patterns.

**Phases with standard patterns (skip research-phase):**
- **Phase 1:** Pydantic model extension + SQLModel JSONB updates are well-documented
- **Phase 2:** React Hook Form useFieldArray + Radix UI integration are established patterns with extensive documentation
- **Phase 3:** Follows existing CriterionCard edit mode pattern (text/type/category already implemented)
- **Phase 4:** cmdk + Radix Popover autocomplete pattern documented in shadcn/ui examples; UMLS MCP already integrated
- **Phase 5:** Simple form validation + audit trail enhancement (standard pattern)
- **Phase 6:** useFieldArray for nested arrays is well-documented in React Hook Form docs

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All capabilities achievable with existing package.json (verified line-by-line); zero new dependencies required |
| Features | MEDIUM | WebSearch verification of clinical trial standards, UMLS autocomplete patterns, audit trail requirements; no Context7 or official Cauldron documentation (reference implementation from project context) |
| Architecture | HIGH | Based on verified existing codebase patterns (CriterionCard edit mode, TanStack Query mutations, react-pdf setup); mature library documentation (React Hook Form, Radix UI) |
| Pitfalls | HIGH | Derived from React state management best practices, PDF viewer integration gotchas, autocomplete patterns, database migration patterns—all well-documented in community sources |

**Overall confidence:** HIGH

### Gaps to Address

- **Extraction schema for evidence linking:** Current multimodal extraction (extraction-service) returns structured data but not page numbers or bounding boxes. Phase 7 planning needs investigation: Can we extract page metadata from LangGraph extraction context? Or add separate PDF text layer parsing step?

- **UMLS MCP response format:** Assumed UMLS MCP `concept_search` returns `{cui, preferred_term, semantic_types}` but not verified against actual MCP implementation. Phase 4 planning should verify response schema or add mapping layer.

- **Backward compatibility strategy validation:** Proposed dual-write pattern (write both modified_text and modified_structured_fields) needs validation with product team—is maintaining text representation of structured fields acceptable? Or should structured edits only write structured data?

- **Rationale field location:** Unclear if rationale should use existing ReviewActionRequest.comment field (currently for review-level comments) or new dedicated rationale field. Phase 5 planning should decide based on audit trail requirements.

## Sources

### Primary (HIGH confidence)

**From STACK-STRUCTURED-EDITOR.md:**
- [react-pdf documentation](https://github.com/wojtekmaj/react-pdf) — customTextRenderer for text layer manipulation
- [cmdk - Fast, unstyled command menu](https://github.com/dip/cmdk) — Command palette library for autocomplete
- [Radix UI documentation](https://www.radix-ui.com/) — Popover, Select components
- [React Hook Form documentation](https://react-hook-form.com/) — useFieldArray, useWatch, Controller patterns
- [shadcn/ui Combobox component](https://ui.shadcn.com/docs/components/radix/combobox) — Reference implementation for cmdk + Radix Popover

**From ARCHITECTURE.md:**
- [React Hook Form useFieldArray](https://react-hook-form.com/docs/usefieldarray) — Dynamic array management
- [TanStack Query Documentation](https://tanstack.com/query/latest) — Server state patterns
- [react-pdf-highlighter-extended GitHub](https://github.com/DanielArnould/react-pdf-highlighter-extended) — PDF highlighting library

**From PITFALLS.md:**
- [Managing Complex State in React with useReducer](https://www.aleksandrhovhannisyan.com/blog/managing-complex-state-react-usereducer/) — Form state patterns
- [Debounce Your Search - Atomic Object](https://spin.atomicobject.com/automplete-timing-debouncing/) — Autocomplete best practices
- [Backward Compatible Database Changes - PlanetScale](https://planetscale.com/blog/backward-compatible-databases-changes) — Migration patterns

### Secondary (MEDIUM confidence)

**From FEATURES.md:**
- [CDISC Data Standards](https://www.allucent.com/resources/blog/what-cdisc-and-what-are-cdisc-data-standards) — Clinical trial data standards
- [21 CFR Part 11 Audit Trail Requirements](https://www.remdavis.com/news/21-cfr-part-11-audit-trail-requirements) — Regulatory compliance
- [SNOMED CT Saves Keystrokes](https://pmc.ncbi.nlm.nih.gov/articles/PMC3041304/) — Semantic autocompletion benefits
- [OHDSI ATLAS cohort editor](https://www.nature.com/articles/s41598-023-49560-w) — Reference implementation patterns
- [Progressive Disclosure - Nielsen Norman Group](https://www.nngroup.com/articles/progressive-disclosure/) — UX pattern

---
*Research completed: 2026-02-13*
*Ready for roadmap: YES*
