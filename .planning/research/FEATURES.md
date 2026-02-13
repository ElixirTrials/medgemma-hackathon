# Feature Research

**Domain:** Structured criteria field mapping editor for clinical trial HITL UI
**Researched:** 2026-02-13
**Confidence:** MEDIUM

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Entity → Relation → Value triplet editing | Standard EAV/CR pattern in clinical data capture; OHDSI ATLAS uses criterion → concept set → temporal structure | MEDIUM | Progressive disclosure (3-step) reduces cognitive load; already exists as display-only in CriterionCard |
| UMLS/SNOMED concept search with autocomplete | SNOMED CT saves 18% keystrokes via semantic autocompletion; expected in medical terminology editors | MEDIUM | UMLS MCP already integrated; needs autocomplete UI wrapper with debouncing |
| Read-only display of existing structured fields | Thresholds/temporal constraints already extracted; users expect to see them before editing | LOW | Already complete in CriterionCard (temporal_constraint, numeric_thresholds badges) |
| Approve/reject/modify workflow per criterion | Standard HITL pattern for review interfaces; already exists for text/type/category | LOW | Extend existing CriterionCard modify mode to include structured fields |
| Rationale/reason field for audit trail | 21 CFR Part 11 requires timestamp + user + reason for all clinical data changes | MEDIUM | New field; integrate with existing review action endpoints |
| Inline validation feedback | Medical coding audit trails require validation against UMLS API before storage; prevents invalid codes | MEDIUM | UMLS validation client already exists; add real-time validation to concept search |
| Multi-threshold support | Clinical criteria often have multiple numeric constraints (e.g., "18-65 years AND BMI <30") | LOW | Backend already stores arrays; UI needs add/remove controls |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valuable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Evidence linking: click criterion → scroll PDF to source | Regulatory audit requirement; competitors require manual navigation | HIGH | Needs span positions from extraction + PDF text layer sync + scroll-to-position logic |
| AI-assisted field pre-population from selected text | AI coding platforms show 30-70% FTE reduction; accelerates review workflow | MEDIUM | Extract selected text → prompt MedGemma → suggest entity/relation/value; requires text selection handler |
| Adaptive value input (single/range/temporal) | Context-aware inputs reduce errors; standard in CDASH-compliant eCRF systems | MEDIUM | Relation dictates input type: "=" → single, "range" → min/max, "within" → duration + unit |
| Visual confidence indicators on AI suggestions | Explainable AI with MEAT evidence standard for 2026 medical coding compliance | LOW | Reuse existing confidence badge component; attach to AI suggestions |
| Multi-mapping per criterion | Complex criteria map to multiple structured fields; enables granular CDISC export | MEDIUM | Add/remove mappings UI; backend stores array of triplets per criterion |
| Interactive SNOMED hierarchy browser | Contextual search performs better than flat autocomplete for medical coders | HIGH | UMLS MCP doesn't provide hierarchy; would need additional API or defer to v2 |
| Undo/redo for edit sessions | Reduces fear of making mistakes; standard in professional editing tools | MEDIUM | Local state management with history stack; not persisted |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Bulk edit for all criteria at once | "Faster workflow" appeal | Breaks audit trail (can't track which reviewer approved which criterion); high error rate | Keyboard shortcuts for approve/next, filter by confidence to batch-review similar items |
| Custom UMLS code entry without validation | "Expert users know best" | Violates 21 CFR Part 11 audit trail requirements; allows invalid codes into database | Allow custom codes but require UMLS validation API check before save; flag unvalidated codes for expert review |
| Real-time collaborative editing | "Like Google Docs" | Conflict resolution complexity; clinical review requires single reviewer per decision for regulatory compliance | Session locking per criterion; show "In review by [user]" badge |
| Free-text relation field | "More flexible than dropdown" | Breaks structured export to CDISC; no standardization for queries | Fixed relation vocabulary (=, !=, >, >=, <, <=, within, not_in_last, contains, not_contains); add "other" with expert review flag |

## Feature Dependencies

```
[Evidence linking]
    └──requires──> [Span positions from extraction]
                       └──requires──> [PDF text layer parsing]

[AI-assisted field suggestions]
    └──requires──> [Text selection handler]
    └──requires──> [MedGemma entity extraction]
    └──requires──> [UMLS MCP concept search]

[Adaptive value input]
    └──requires──> [Relation selection]

[Multi-mapping per criterion]
    └──requires──> [Triplet editor UI]
    └──requires──> [Backend API for array storage]

[Rationale capture] ──enhances──> [Audit trail logging]

[Inline validation] ──enhances──> [UMLS concept search]

[Undo/redo] ──conflicts──> [Auto-save] (must choose: explicit save or auto-save)
```

### Dependency Notes

- **Evidence linking requires span positions:** Extraction must store character offsets or bounding boxes; current multimodal extraction doesn't return positions
- **AI suggestions require text selection:** User must select source text in PDF viewer before triggering suggestion engine
- **Adaptive value input requires relation selection:** Relation type (e.g., "range") determines whether to show single input, min/max inputs, or duration + unit
- **Multi-mapping requires triplet editor:** Can't add multiple mappings without base triplet editing workflow
- **Undo/redo conflicts with auto-save:** If changes auto-save, undo must interact with backend state; if no auto-save, undo is purely client-side

## MVP Definition

### Launch With (v1.5 - Current Milestone)

Minimum viable product — what's needed to validate the concept.

- [x] **Read-only structured field display** — Already complete (temporal constraints, numeric thresholds badges in CriterionCard)
- [ ] **Entity → Relation → Value triplet editor** — Core functionality; enables structured field editing
- [ ] **UMLS concept search for entity field** — Table stakes for medical terminology editing
- [ ] **Adaptive value input (single/range/temporal)** — Prevents data entry errors; standard in clinical data capture
- [ ] **Rationale text field** — 21 CFR Part 11 compliance requirement
- [ ] **Modify action with structured fields** — Extend existing review workflow to save triplets
- [ ] **Multi-mapping support (add/remove)** — Complex criteria need multiple structured mappings

### Add After Validation (v1.6+)

Features to add once core is working.

- [ ] **Evidence linking (click → scroll PDF)** — High value but complex; validate workflow first
- [ ] **AI-assisted field suggestions** — Accelerates review but not blocking; add after manual editing works
- [ ] **Inline UMLS validation feedback** — Enhance UX after base search works
- [ ] **Visual confidence indicators on suggestions** — Add when AI suggestions implemented
- [ ] **Undo/redo for edit sessions** — Nice to have; add if user testing shows frequent mistakes

### Future Consideration (v2+)

Features to defer until product-market fit is established.

- [ ] **Interactive SNOMED hierarchy browser** — Needs additional API integration; autocomplete sufficient for v1
- [ ] **Batch operations with audit trail** — Complex coordination; validate single-item workflow first
- [ ] **Custom validation rules per protocol** — Enterprise feature; not needed for 50-protocol pilot

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority | Dependencies |
|---------|------------|---------------------|----------|--------------|
| Triplet editor (entity → relation → value) | HIGH | MEDIUM | P1 | None (base feature) |
| UMLS concept search autocomplete | HIGH | MEDIUM | P1 | UMLS MCP (exists) |
| Adaptive value input | HIGH | MEDIUM | P1 | Triplet editor |
| Rationale text field | HIGH | LOW | P1 | None |
| Multi-mapping (add/remove) | HIGH | MEDIUM | P1 | Triplet editor |
| Modify action API extension | HIGH | LOW | P1 | Triplet editor |
| Evidence linking | HIGH | HIGH | P2 | Span positions (not implemented) |
| AI field suggestions | MEDIUM | MEDIUM | P2 | Text selection, MedGemma |
| Inline UMLS validation | MEDIUM | MEDIUM | P2 | Concept search |
| Confidence indicators on suggestions | MEDIUM | LOW | P2 | AI suggestions |
| Undo/redo | LOW | MEDIUM | P3 | None |
| SNOMED hierarchy browser | LOW | HIGH | P3 | Additional API |

**Priority key:**
- P1: Must have for v1.5 launch (structured editing workflow)
- P2: Should have, add in v1.6 (evidence linking, AI assist)
- P3: Nice to have, future consideration (advanced UX)

## Existing System Integration

### Already Built (v1.4 - Leverage These)

| Component | Current State | Use For |
|-----------|---------------|---------|
| CriterionCard | Text/type/category edit mode; temporal constraint + threshold badges (display-only) | Extend modify mode to include triplet editing |
| EntityCard | UMLS CUI/SNOMED/preferred_term edit mode with text inputs | Reference implementation for concept editing UX |
| UMLS MCP integration | concept_search, concept_linking tools wired to grounding-service | Backend for autocomplete; add frontend query wrapper |
| Review action endpoints | POST /criteria/:id/review with approve/reject/modify actions | Extend ReviewActionRequest schema to include modified_field_mappings |
| PDF viewer (split-screen) | Left panel shows PDF via GCS signed URL | Evidence linking target; needs scroll-to-position enhancement |
| Confidence badges | High/medium/low display with percentage | Reuse for AI suggestion confidence |
| Audit log | reviewer_id, timestamp, action, before/after values | Extend to log structured field changes |

### Gaps to Close (New Implementation Needed)

| Gap | Why It's Missing | What's Needed |
|-----|------------------|---------------|
| Span positions from extraction | Multimodal extraction returns structured data without character offsets | Add bounding box or text span extraction to extraction-service; store in criteria.source_spans JSONB |
| Structured field editing UI | CriterionCard modify mode only edits text/type/category | New FieldMappingEditor component with progressive disclosure |
| Autocomplete concept search | UMLS MCP tools are backend-only; no frontend autocomplete | TanStack Query hook + debounced input + Combobox component |
| Adaptive value inputs | No conditional input rendering based on relation type | InputByRelationType component with single/range/temporal variants |
| Multi-mapping storage | Database stores single temporal_constraint and numeric_thresholds array | Add criteria.field_mappings JSONB column for array of {entity, relation, value, unit?, upper_value?} |
| Rationale field in review actions | Review actions don't require reason text | Add optional rationale field to ReviewActionRequest; make required for modify actions |
| Text selection handler | PDF viewer is read-only; no text selection hooks | Add onTextSelect callback to PDF viewer; pass selected text to suggestion engine |

## Competitor Feature Analysis

| Feature | OHDSI ATLAS | Clinical Trial Design Software (Medidata) | Our Approach |
|---------|-------------|-------------------------------------------|--------------|
| Structured criteria editor | Cohort criteria with domain → concept set → temporal requirements; UI forms for criteria attributes | AI-powered modeling with scenario testing; not focused on manual structured editing | Cauldron-style progressive disclosure (field → relation → value) with UMLS autocomplete |
| Evidence linking | No source document linking; criteria are created from scratch | Source documents not in HITL loop; focus on protocol design optimization | Click criterion → scroll PDF to source text with span highlighting |
| Terminology search | Requires concept sets to be pre-defined; uses OMOP CDM vocabulary | Proprietary medical coding; not UMLS-based | UMLS MCP autocomplete with semantic search; 18% keystroke savings via autocompletion |
| Audit trail | Not applicable (research use, not regulatory) | FDA-compliant audit trail with timestamps and user tracking | 21 CFR Part 11 compliant: timestamp + user + reason + before/after values |
| AI assistance | No AI features | AI for protocol optimization, patient subpopulation modeling | MedGemma agentic grounding for entity extraction + field suggestions |
| Multi-mapping | Single criterion can have multiple inclusion criteria; modular approach | Not applicable (focuses on protocol design, not extraction validation) | Multiple entity → relation → value triplets per criterion with add/remove UI |

## UX Flow: Editing Entity/Relation/Value Triplets

### 3-Step Progressive Disclosure Pattern

Based on Cauldron reference implementation and OHDSI ATLAS cohort editor patterns:

```
Step 1: Select Entity (Medical Concept)
┌────────────────────────────────────────┐
│ Entity: [Acetaminophen         ▼]     │  ← Autocomplete search via UMLS MCP
│         Type to search UMLS...         │     Shows: preferred_term, CUI, SNOMED
│                                        │     Semantic autocomplete (18% keystroke savings)
└────────────────────────────────────────┘
         ↓ (on selection)

Step 2: Select Relation (Comparator)
┌────────────────────────────────────────┐
│ Relation: [Greater than or equal ▼]   │  ← Dropdown with 10 options
│           (=, !=, >, >=, <, <=,        │     Relation type determines Step 3 input
│            within, not_in_last,        │
│            contains, not_contains)     │
└────────────────────────────────────────┘
         ↓ (on selection)

Step 3: Enter Value (Adaptive Input)
┌────────────────────────────────────────┐
│ If relation = standard (=, !=, >, <, >=, <=):
│   Value: [1000] Unit: [mg ▼]           │  ← Single input + unit dropdown
│
│ If relation = range:
│   Min: [500]  Max: [1000]  Unit: [mg]  │  ← Min/max inputs + unit
│
│ If relation = temporal (within, not_in_last):
│   Duration: [6]  Unit: [months ▼]      │  ← Number + temporal unit (hours/days/weeks/months/years)
│   Reference: [screening ▼]             │  ← Optional reference point
└────────────────────────────────────────┘
```

### Complete Editing Workflow

```
┌─────────────────────────────────────────────────────────────┐
│ CriterionCard (Modify Mode)                                 │
├─────────────────────────────────────────────────────────────┤
│ Text: [Age 18-65 years, BMI <30, no acetaminophen >1g/day] │
│ Type: [Inclusion ▼]  Category: [Demographic]               │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Structured Field Mappings                               │ │
│ ├─────────────────────────────────────────────────────────┤ │
│ │ Mapping 1:                                              │ │
│ │   Entity:   [Age (C0001779) ▼]                          │ │
│ │   Relation: [range ▼]                                   │ │
│ │   Value:    Min: [18]  Max: [65]  Unit: [years ▼]      │ │
│ │   [Remove Mapping]                                      │ │
│ │                                                         │ │
│ │ Mapping 2:                                              │ │
│ │   Entity:   [Body Mass Index (C0005893) ▼]             │ │
│ │   Relation: [< ▼]                                       │ │
│ │   Value:    [30]  Unit: [kg/m² ▼]                      │ │
│ │   [Remove Mapping]                                      │ │
│ │                                                         │ │
│ │ Mapping 3:                                              │ │
│ │   Entity:   [Acetaminophen (C0000970) ▼]               │ │
│ │   Relation: [> ▼]                                       │ │
│ │   Value:    [1]  Unit: [g/day ▼]                       │ │
│ │   [Remove Mapping]                                      │ │
│ │                                                         │ │
│ │ [+ Add Mapping]                                         │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ Rationale for changes (required):                          │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Corrected acetaminophen threshold to match protocol     │ │
│ │ Section 5.3 (extraction had wrong unit conversion)      │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ [Save]  [Cancel]                                            │
└─────────────────────────────────────────────────────────────┘
```

### AI-Assisted Suggestion Flow (v1.6+)

```
User selects text in PDF viewer: "patients aged 18-65 years"
         ↓
Click "Suggest Fields" button
         ↓
Frontend: POST /api/suggest-fields { selected_text: "...", criterion_id: "..." }
         ↓
Backend: MedGemma extracts entities → UMLS MCP concept_search
         ↓
Frontend receives:
[
  { entity: "Age", cui: "C0001779", snomed: "397669002", relation: "range",
    min: 18, max: 65, unit: "years", confidence: 0.92 }
]
         ↓
UI shows suggestion card:
┌─────────────────────────────────────────┐
│ AI Suggestion (92% confidence)          │
│ Entity: Age (C0001779)                  │
│ Relation: range                         │
│ Value: 18-65 years                      │
│ [Accept] [Modify] [Reject]              │
└─────────────────────────────────────────┘
         ↓
On accept: pre-populate triplet editor with suggestion
```

## Sources

### Clinical Trial Standards and Compliance
- [A Guide to CDISC Standards Used in Clinical Research | Certara](https://www.certara.com/blog/a-guide-to-cdisc-standards-used-in-clinical-research/)
- [CDISC Data Standards Explained: CDASH, SDTM, SEND, and ADaM](https://www.allucent.com/resources/blog/what-cdisc-and-what-are-cdisc-data-standards)
- [21 CFR Part 11 Audit Trail Requirements | Remington-Davis](https://www.remdavis.com/news/21-cfr-part-11-audit-trail-requirements)
- [Audit Trails & Transparency: Tracking Changes in Clinical Data - OpenClinica](https://www.openclinica.com/blog/audit-trails-transparency-tracking-changes-in-clinical-data/)

### UMLS and Medical Terminology Interfaces
- [Find Concepts | SNOMED CT Terminology Services Guide | SNOMED International](https://docs.snomed.org/snomed-ct-practical-guides/snomed-ct-terminology-services-guide/4-terminology-service-types/4.8-find-concepts)
- [SNOMED CT Saves Keystrokes: Quantifying Semantic Autocompletion - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC3041304/)
- [UMLS Metathesaurus Browser](https://uts.nlm.nih.gov/uts/umls/home)

### Clinical Trial Software and Structured Editors
- [Implementation of inclusion and exclusion criteria in clinical studies in OHDSI ATLAS software | Scientific Reports](https://www.nature.com/articles/s41598-023-49560-w)
- [ATLAS Documentation | OHDSI](https://www.ohdsi.org/web/wiki/doku.php?id=documentation:software:atlas:cohorts)
- [Clinical Trial Design Software - Medidata](https://www.medidata.com/en/clinical-trial-products/medidata-ai/real-world-data/clinical-trial-design-software/)

### AI-Assisted Medical Coding
- [Top 10 AI in Medical Coding Software for 2026](https://www.aptarro.com/insights/top-ai-in-medical-coding-software)
- [AI in Medical Coding and Billing: Implementation Guide 2026](https://topflightapps.com/ideas/ai-in-medical-billing-and-coding/)
- [Understanding Medical Coding Audit Trails — AMBCI](https://ambci.org/medical-billing-and-coding-certification-blog/understanding-medical-coding-audit-trails)

### Entity-Attribute-Value (EAV) Clinical Data Models
- [Data Model Considerations for Clinical Effectiveness Researchers - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC3824370/)
- [Entity–attribute–value model - Wikipedia](https://en.wikipedia.org/wiki/Entity%E2%80%93attribute%E2%80%93value_model)

### Adaptive Data Capture and Progressive Disclosure
- [Progressive Disclosure - NN/G](https://www.nngroup.com/articles/progressive-disclosure/)
- [Progressive disclosure in UX design: Types and use cases - LogRocket Blog](https://blog.logrocket.com/ux-design/progressive-disclosure-ux-types-use-cases/)
- [Predictive modeling of biomedical temporal data in healthcare applications - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC11519529/)

---
*Feature research for: Structured criteria field mapping editor (v1.5 milestone)*
*Researched: 2026-02-13*
*Confidence: MEDIUM — WebSearch verification of clinical trial standards, UMLS autocomplete patterns, and audit trail requirements; no Context7 or official Cauldron documentation available (reference implementation from project context)*
