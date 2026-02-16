# Requirements: Clinical Trial Criteria Extraction System

**Defined:** 2026-02-16
**Core Value:** Clinical researchers can upload a protocol PDF and get accurately extracted, UMLS-grounded eligibility criteria that they can review and approve in a single workflow — replacing manual extraction that takes hours per protocol.

## v2.0 Requirements

Requirements for v2.0 Pipeline Consolidation & E2E Quality. Each maps to roadmap phases.

### Bug Fixes

- [ ] **BUGF-01**: Grounding produces real terminology codes with >0% confidence for extracted entities
- [ ] **BUGF-02**: Audit trail entries are visible on the Review page after approve/reject/modify actions
- [ ] **BUGF-03**: Dashboard pending count includes batches with any unreviewed criteria (not just status='pending_review')

### UX Polish

- [ ] **UX-01**: Reviewed criteria are visually distinct from pending criteria (e.g. left border color)
- [ ] **UX-02**: Reviewer can provide optional rationale when rejecting or approving criteria
- [ ] **UX-03**: Reviewer can search/filter criteria by text on the Review page
- [ ] **UX-04**: Criteria sections are sorted with headers (Inclusion/Exclusion)

### Pipeline Consolidation

- [ ] **PIPE-01**: Extraction and grounding run in a flat 5-node LangGraph (ingest→extract→parse→ground→persist) with no outbox hop
- [ ] **PIPE-02**: Minimal PipelineState TypedDict carries data through all nodes without redundant DB reads; ground node delegates to helper functions
- [ ] **PIPE-03**: criteria_extracted outbox event is removed; protocol_uploaded outbox is retained for async pipeline trigger
- [ ] **PIPE-04**: Pipeline failure at any stage leaves protocol in recoverable state (not stuck in "extracted" forever)

### Multi-Terminology Grounding

- [ ] **GRND-01**: Entities are routed to terminology APIs based on entity type (Medication→RxNorm, Condition→ICD-10+SNOMED, Lab→LOINC, Phenotype→HPO)
- [ ] **GRND-02**: UMLS/SNOMED grounding is retained and called via direct Python import (not MCP subprocess)
- [ ] **GRND-03**: Entity model stores multi-system codes (rxnorm_code, icd10_code, loinc_code, hpo_code alongside existing umls_cui and snomed_code)
- [ ] **GRND-04**: Grounding uses ToolUniverse Python API with selective tool loading (RxNorm, ICD-10, LOINC, HPO, UMLS REST) — not MCP subprocess
- [ ] **GRND-05**: Entity extraction uses Gemini structured output OR improved MedGemma prompting (approach determined during Phase research spike)
- [ ] **GRND-06**: Unroutable entity types (e.g. Demographic) are explicitly skipped with logging, not silently dropped

### Editor Polish

- [ ] **EDIT-01**: Saved field_mappings pre-populate the structured editor when entering modify mode
- [ ] **EDIT-02**: Saved field_mappings are displayed as badges/chips in read mode (outside edit mode)
- [ ] **EDIT-03**: Multi-terminology codes (RxNorm, ICD-10, LOINC, HPO) are visible per entity in the UI

### Re-Extraction

- [ ] **REXT-01**: Researcher can trigger re-extraction on an existing protocol without re-uploading the PDF
- [ ] **REXT-02**: Re-extraction creates a new batch alongside existing batches (does not replace)
- [ ] **REXT-03**: Batches with reviewed criteria are protected via archiving and auto-inheritance (old batches archived, review decisions inherited to new batch via fuzzy matching)
- [ ] **REXT-04**: Extraction uses temperature=0 and prompt granularity instructions for improved determinism

### Corpus Tooling

- [ ] **CORP-01**: Researcher can view side-by-side diff of AI-extracted vs human-corrected criteria
- [ ] **CORP-02**: Reviewed criteria can be exported as JSON/CSV corpus (criterion_text, ai_entities, human_entities)
- [ ] **CORP-03**: Metrics dashboard shows agreement rate and modification frequency by category/entity_type

## v3 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Advanced Grounding

- **AGRND-01**: Inter-annotator agreement (IAA) tracking with dual-review workflow and Cohen's Kappa
- **AGRND-02**: Selective per-criterion re-extraction (only low-confidence criteria, not entire protocol)
- **AGRND-03**: Per-criterion confidence calibration curve based on reviewed corpus

### Interoperability

- **INTR-01**: FHIR EvidenceVariable export for extracted criteria
- **INTR-02**: OMOP Circe integration for cohort definition
- **INTR-03**: Composite criteria expression trees (AND/OR boolean logic)

### Patient Matching

- **PMTCH-01**: Patient-level eligibility matching against extracted criteria
- **PMTCH-02**: Materialized views for batch matching performance

## Out of Scope

| Feature | Reason |
|---------|--------|
| Fully merging extraction/grounding Python packages | Destroys separation of concerns; share graph, keep packages separate |
| Real-time streaming extraction progress | Gemini structured output isn't streamable |
| Auto-save structured edits on blur | Pollutes audit trail with partial saves |
| Required rationale for approve actions | Kills review throughput; optional is sufficient |
| ToolUniverse as MCP subprocess | Same failure mode as current UMLS MCP (5-15s startup, zombie processes) |
| PII field-level encryption | Deferred to v3; acceptable risk for pilot with no real patient data |
| Mobile app | Web only for pilot |
| Real-time notifications | Not needed for small pilot |

## Traceability

Which phases cover which requirements. Updated after roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| BUGF-01 | Phase 29 | Pending |
| BUGF-02 | Phase 29 | Pending |
| BUGF-03 | Phase 29 | Pending |
| UX-01 | Phase 30 | Pending |
| UX-02 | Phase 30 | Pending |
| UX-03 | Phase 30 | Pending |
| UX-04 | Phase 30 | Pending |
| EDIT-01 | Phase 30 | Pending |
| EDIT-02 | Phase 30 | Pending |
| GRND-01 | Phase 31 | Pending |
| GRND-02 | Phase 31 | Pending |
| GRND-04 | Phase 31 | Pending |
| GRND-06 | Phase 31 | Pending |
| PIPE-01 | Phase 31 | Pending |
| PIPE-02 | Phase 31 | Pending |
| PIPE-03 | Phase 31 | Pending |
| GRND-03 | Phase 32 | Pending |
| GRND-05 | Phase 32 | Pending |
| PIPE-04 | Phase 32 | Pending |
| EDIT-03 | Phase 32 | Pending |
| REXT-01 | Phase 33 | Pending |
| REXT-02 | Phase 33 | Pending |
| REXT-03 | Phase 33 | Pending |
| REXT-04 | Phase 33 | Pending |
| CORP-01 | Phase 34 | Pending |
| CORP-02 | Phase 34 | Pending |
| CORP-03 | Phase 34 | Pending |

**Coverage:**
- v2.0 requirements: 27 total
- Mapped to phases: 27
- Unmapped: 0

**Coverage validation:** ✓ All 27 v2.0 requirements mapped to phases 29-34 (Phases 30 ‖ 31 run in parallel)

---
*Requirements defined: 2026-02-16*
*Last updated: 2026-02-16 after parallel roadmap restructuring*
