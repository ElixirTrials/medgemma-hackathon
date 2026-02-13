# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-13)

**Core value:** Clinical researchers can upload a protocol PDF and get accurately extracted, UMLS-grounded eligibility criteria that they can review and approve in a single workflow -- replacing manual extraction that takes hours per protocol.
**Current focus:** v1.5 Structured Criteria Editor — Full field mapping editor with evidence linking

## Current Position

Phase: 23 — Core Structured Editor Component
Plan: 01 of 1
Status: Plan 01 complete
Last activity: 2026-02-13 — Completed 23-01: Core Structured Editor Component

Progress: ████████████████████ 100%

## Performance Metrics

**Overall Velocity:**
- Total plans completed: 39
- Average duration: 7.1 min
- Total execution time: 4.92 hours

**Recent Plans:**
| Phase | Plan | Duration | Date       | Notes                                      |
| ----- | ---- | -------- | ---------- | ------------------------------------------ |
| 23    | 01   | 4 min    | 2026-02-13 | Core structured editor component           |
| 22    | 01   | 3 min    | 2026-02-13 | Backend API extension for structured edits |

## Accumulated Context

### Decisions

- v1.0: Google OAuth for authentication (fits GCP ecosystem)
- v1.0: Docker Compose infrastructure with PostgreSQL, MLflow, PubSub emulator
- v1.2: Terraform for GCP Cloud Run deployment (paused, phases 13-15)
- v1.3: Direct PDF multimodal extraction replaces pymupdf4llm markdown conversion
- v1.3: Base64 PDF data URIs for Gemini multimodal input
- v1.4: Investigation found 4 problems — grounding 100% failed, thresholds never populated, temporal constraints not displayed, no threshold UI
- v1.4: Display-only for temporal constraints and thresholds (no inline editing in CriterionCard)
- v1.4: MedGemma as agentic reasoner — drives grounding via iterative UMLS MCP calls
- v1.4: Grounding graph simplified from 4 nodes to 2 (medgemma_ground -> validate_confidence)
- v1.5: Cauldron-style field mapping editor as reference implementation for HITL editing
- v1.5: Keep side-by-side view, add scroll-to-source on criterion click
- v1.5: Three editable structured components: entity (SNOMED/UMLS), relation (comparator), value
- [Phase 22-01]: Use optional modified_structured_fields field for backward compatibility
- [Phase 22-01]: Add schema_version to AuditLog details for versioned audit trail
- [Phase 22-01]: Support dual-write pattern (text + structured in same request)
- [Phase 23-01]: Discriminated union types for relation categories (standard/range/temporal)
- [Phase 23-01]: State cleanup via useEffect prevents value leak between relation categories
- [Phase 23-01]: Co-located sub-components in ValueInput.tsx for simplicity

### Cauldron Reference (v1.5)

Key patterns from Cauldron's CriteriaEditPanel:
- Field mapping triplets: targetField → relation → targetValue (with unit, min, max)
- 3-step progressive disclosure: select field → select relation → enter value
- Adaptive value input: standard (single), range (min/max), temporal (number + unit)
- 10 relations: =, !=, >, >=, <, <=, within, not_in_last, contains, not_contains
- AI suggestion engine pre-fills fields based on selected text patterns
- Rationale textarea required for all edits (audit trail)
- Interactive text selection from source document for evidence linking

### Current System Gaps (v1.5 scope)

- CriterionCard: text/type/category editable, but NOT relation/value/threshold
- EntityCard: UMLS CUI/SNOMED/preferred_term editable (modify mode exists)
- ~~No API endpoint for modified_numeric_thresholds or modified_temporal_constraint~~ ✅ Done (22-01)
- No evidence linking (click-to-scroll to protocol source text)
- No rationale capture for edits
- No multi-mapping per criterion

### Pending Todos

None.

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-02-13
Stopped at: Completed Phase 23-01 (Core Structured Editor Component)
Resume file: .planning/phases/23-core-structured-editor-component/23-01-SUMMARY.md
Next action: Review ROADMAP.md to identify next phase for v1.5 (likely Phase 24: CriterionCard integration)
