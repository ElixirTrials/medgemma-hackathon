# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-13)

**Core value:** Clinical researchers can upload a protocol PDF and get accurately extracted, UMLS-grounded eligibility criteria that they can review and approve in a single workflow -- replacing manual extraction that takes hours per protocol.
**Current focus:** v1.6 Correction Workflow & Corpus Building — Editor polish + gold-standard corpus for prompt iteration

## Current Position

Phase: 28 (complete)
Plan: —
Status: Phase 28 complete, all v1.5 plans done
Last activity: 2026-02-13 — Completed quick task 2: Fix MedGemma entity decomposition

## Performance Metrics

**Overall Velocity:**
- Total plans completed: 45
- Average duration: 6.6 min
- Total execution time: 5.33 hours

**Recent Plans:**
| Phase | Plan | Duration | Date       | Notes                                           |
| ----- | ---- | -------- | ---------- | ----------------------------------------------- |
| 28    | 02   | 8 min    | 2026-02-13 | Evidence linking UI with click-to-scroll        |
| 27    | 01   | 6 min    | 2026-02-13 | Multi-mapping support for structured criteria   |
| 28    | 01   | 4 min    | 2026-02-13 | Page number data pipeline                       |
| 26    | 01   | 3 min    | 2026-02-13 | Rationale capture for review actions            |

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
- [Phase 24]: 3-mode editMode state (none/text/structured) prevents impossible states like both modes active simultaneously
- [Phase 24]: useEffect to sync local edit state when criterion prop changes ensures text fields reflect latest data after mutation
- [Phase 25-01]: UMLS search proxy uses "Clinical Finding" as semantic_type default (search API doesn't return semantic types)
- [Phase 25-01]: Error mapping: 502 for UMLS API errors, 503 for missing UMLS_API_KEY configuration
- [Phase 25-02]: useState + useEffect + setTimeout for debouncing (simpler than external library)
- [Phase 25-02]: 300ms debounce with 3-character minimum for UMLS autocomplete
- [Phase 25-02]: UmlsCombobox as primary input, CUI/SNOMED as secondary editable fields (visual hierarchy)
- [Phase 26-01]: Reuse existing comment field for rationale (backward compatibility, no schema changes)
- [Phase 26-01]: Map comment to rationale key in AuditLog.details (semantic clarity in audit trail)
- [Phase 26-01]: Optional rationale textarea with (optional) label and placeholder text pattern
- [Phase 27-01]: useFieldArray for dynamic mapping management (robust array handling with minimal re-renders)
- [Phase 27-01]: Store field_mappings in conditions JSONB column (general-purpose field, separate from legacy temporal/threshold)
- [Phase 27-01]: Minimum 1 mapping enforcement via disabled remove button (UI constraint clearer than validation error)
- [Phase 27-01]: v1.5-multi schema_version for audit logs (enables filtering multi-mapping edits)
- [Phase 28-01]: page_number as optional int | None for backward compatibility
- [Phase 28-02]: Use first 40 chars of criterion text for highlight matching (full criteria text can be very long)
- [Phase 28-02]: Toggle selection pattern (clicking same criterion deselects it)
- [Phase 28-02]: Only show click affordance when page_number exists (graceful degradation)

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

- ~~CriterionCard: text/type/category editable, but NOT relation/value/threshold~~ ✅ Done (24-01 - structured editor toggle added)
- ~~EntityCard: UMLS CUI/SNOMED/preferred_term editable (modify mode exists)~~ ✅ Done (25-02 - UMLS autocomplete integrated)
- ~~No API endpoint for modified_numeric_thresholds or modified_temporal_constraint~~ ✅ Done (22-01)
- ~~No UMLS autocomplete in entity field~~ ✅ Done (25-02 - autocomplete with debounced search)
- ~~No rationale capture for edits~~ ✅ Done (26-01 - optional rationale textarea in modify mode)
- ~~No page_number data pipeline~~ ✅ Done (28-01 - page_number flows from extraction to API)
- ~~No multi-mapping per criterion~~ ✅ Done (27-01 - useFieldArray with add/remove buttons, field_mappings array storage)
- ~~No PDF viewer with scroll-to-source~~ ✅ Done (28-02 - click-to-scroll with text highlighting)
- No display of field_mappings in non-edit mode (saved mappings not shown as badges)
- No initialValues population from saved field_mappings (editor always starts with 1 empty mapping)

### Pending Todos

None.

### Blockers/Concerns

None.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 2 | Fix MedGemma entity extraction to split compound criteria into individual UMLS/SNOMED concepts | 2026-02-13 | 8f0ee8b | [2-fix-medgemma-entity-extraction-to-split-](./quick/2-fix-medgemma-entity-extraction-to-split-/) |
| 3 | Switch PDF extraction to Gemini File API (google.genai.Client, removes 20MB base64 limit) | 2026-02-13 | d65042f | [3-switch-pdf-extraction-to-gemini-file-api](./quick/3-switch-pdf-extraction-to-gemini-file-api/) |

## Session Continuity

Last session: 2026-02-13
Stopped at: Completed quick task 3: Switch PDF extraction to Gemini File API
Resume file: .planning/quick/3-switch-pdf-extraction-to-gemini-file-api/3-SUMMARY.md
Next action: Ready for v1.6 planning or next quick task.
