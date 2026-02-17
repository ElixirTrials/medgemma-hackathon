# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-16)

**Core value:** Clinical researchers can upload a protocol PDF and get accurately extracted, UMLS-grounded eligibility criteria that they can review and approve in a single workflow — replacing manual extraction that takes hours per protocol.

**Current focus:** Phase 32 - Entity Model, Ground Node & Multi-Code Display

## Current Position

Phase: 32 of 34 (Entity Model, Ground Node & Multi-Code Display)
Plan: Completed Plan 02 of TBD
Status: In Progress
Last activity: 2026-02-17 — Completed Plan 32-02 (PostgreSQL checkpointing, retry-from-checkpoint endpoint)

Progress: [█████████████████████████░░░░░░░░░] 85% (29/34 phases complete)

## Performance Metrics

**Overall Velocity:**
- Total plans completed: 63 (through Phase 29)
- Average duration: ~13 min
- Total execution time: ~15.6 hours (across v1.0, v1.3, v1.4, v1.5, v2.0)

**By Milestone:**

| Milestone | Phases | Plans | Total Time | Status |
|-----------|--------|-------|------------|--------|
| v1.0 | 1-7 | 24 | ~3.6 hours | Shipped 2026-02-12 |
| v1.1 | 8-10 | 6 | ~45 min | Paused |
| v1.3 | 16 | 1 | ~7 min | Shipped 2026-02-12 |
| v1.4 | 17-21 | 7 | ~2 hours | Shipped 2026-02-13 |
| v1.5 | 22-28 | 11 | ~8 hours | Shipped 2026-02-13 |
| v2.0 | 29-34 | 4/TBD | ~52 min | In progress |

**Recent Plans:**
| Phase | Plan | Duration | Date       | Notes                                                       |
| ----- | ---- | -------- | ---------- | ----------------------------------------------------------- |
| 32    | 01   | 4 min    | 2026-02-17 | Real NLM API terminology lookups (RxNorm/ICD-10/LOINC/HPO), terminology search proxy endpoints |
| 32    | 02   | 4 min    | 2026-02-17 | PostgreSQL checkpointing, retry-from-checkpoint, async retry endpoint |
| 31    | 03   | 8 min    | 2026-02-17 | Ground node, persist node, 5-node graph, unified trigger, PIPE-03 |
| 31    | 02   | 20 min   | 2026-02-17 | Extraction tools (pdf_parser, gemini_extractor), ingest/extract/parse nodes |
| 31    | 01   | 6 min    | 2026-02-17 | Service skeleton, PipelineState, TerminologyRouter          |
| 30    | 01   | 2 min    | 2026-02-17 | Review status borders + sticky filter bar + section grouping |
| 29    | 04   | 4 min    | 2026-02-16 | Medical entity filtering for high CUI rate                  |
| 29    | 03   | 15 min   | 2026-02-16 | Gemini structured output for MedGemma grounding             |
| 29    | 02   | 8 min    | 2026-02-16 | Audit trail and pending count bug fixes                     |
| 29    | 01   | 9 min    | 2026-02-16 | Grounding confidence bug fix with diagnostic logging        |

*Metrics from MILESTONES.md and previous roadmaps*
| Phase 30-ux-polish-editor-pre-loading P02 | 2 | 3 tasks | 4 files |
| Phase 32 P01 | 4 | 2 tasks | 6 files |
| Phase 32 P02 | 4 | 2 tasks | 4 files |
| Phase 31 P03 | 8 | 2 tasks | 13 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.

**v2.0 Architecture (2026-02-16):**
- ToolUniverse Python API with selective loading (not MCP subprocess)
- Flat 5-node LangGraph pipeline (ingest→extract→parse→ground→persist)
- UMLS retained via direct Python import (not MCP subprocess)
- Store errors in state, use Command for routing
- Remove criteria_extracted outbox, retain protocol_uploaded

**Phase 32 Terminology API (2026-02-17) - Plan 01:**
- NLM direct API over ToolUniverse: ToolUniverse medical tool availability unconfirmed; NLM REST APIs (RxNav, Clinical Tables, JAX HPO) are free, no-auth, well-documented (32-01)
- routing.yaml source: tooluniverse → source: direct_api for rxnorm/icd10/loinc/hpo (32-01)
- diskcache optional: if not installed, caching silently disabled (graceful degradation) (32-01)
- SNOMED /api/terminology/snomed/search delegates to get_umls_client().search_snomed() — same existing working path (32-01)
- Frontend /api/terminology/{system}/search available for all 6 systems: rxnorm, icd10, loinc, hpo, umls, snomed (32-01)

**Phase 32 Checkpointing (2026-02-17) - Plan 02:**
- PostgresSaver singleton (not per-invocation) to avoid connection pool exhaustion (32-02)
- DATABASE_URL fallback: get_graph() compiles without checkpointer if DATABASE_URL not set — maintains testability (32-02)
- retry_from_checkpoint raises exceptions for API to handle; endpoint stores error_reason[:500] and returns retry_started (32-02)
- No outbox event on retry — retry bypasses outbox, goes directly to graph via checkpoint (32-02)
- thread_id = protocol_id — deterministic checkpoint lookup without separate tracking (32-02)
- pdf_bytes serialization concern resolved: parse_node clears pdf_bytes before ground runs (PIPE-03), so checkpoint saved after bytes are None (32-02)

**Phase 31 Pipeline Consolidation (2026-02-17) - Plan 01:**
- TerminologyRouter loads YAML config and returns correct API list per entity type (31-01)
- ToolUniverse _query_tooluniverse is a stub — medical tool availability unconfirmed; UMLS/SNOMED direct Python paths are fully functional (31-01)
- SNOMED lookup is two-step: UMLS concept_search → CUI → get_snomed_code_for_cui (reuses umls_mcp_server + grounding_service) (31-01)
- Demographic entities explicitly logged at INFO level and skipped — not silently dropped (GRND-06 pattern) (31-01)
- PipelineState uses str | None JSON fields (not nested dicts) for minimal LangGraph state serialization overhead (31-01)

**Phase 30 UX Polish (2026-02-17) - COMPLETE:**
- Review status colored left borders on CriterionCard: green=approved, red=rejected, blue=modified, yellow=pending (30-01)
- Status border supersedes low-confidence border — review_status is more actionable, ConfidenceBadge already shows confidence (30-01)
- Client-side useMemo filtering with 300ms debounced text search and 3 dropdowns (status/type/confidence) (30-01)
- Criteria grouped into Inclusion/Exclusion/To Be Sorted sections with pending-first sort and reviewed/total progress counts (30-01)
- Fixed API sort (confidence asc), removed server sort controls UI — client-side grouping replaces it (30-01)
- RejectDialog uses predefined checkboxes (5 reason codes) for structured audit trail; Approve stays one-click per user decision (30-02)
- FieldMappingBadges returns null when no field_mappings exist; AND connector is static in read mode, editable in structured editor (30-02)

**Phase 29 Bug Fixes (2026-02-16) - COMPLETE:**
- Three-pronged entity filtering: prompt + code + evaluate for high CUI rate (29-04)
- Removed Demographic entity type (no UMLS CUIs for demographics) (29-04)
- Post-extraction filter with 3 rules: Demographics, non-medical keywords, age thresholds (29-04)
- Confidence scoring guidelines in evaluate prompt (0.9-1.0 exact, 0.7-0.8 synonym) (29-04)
- Two-model architecture: MedGemma for medical reasoning, Gemini for JSON structuring (29-03)
- Zero JSON parse errors via Gemini with_structured_output (29-03)
- Batch status auto-transition: `in_progress → reviewed/approved/rejected` when all criteria reviewed (29-02)
- Criteria-level pending count query (not batch status) for dashboard accuracy (29-02)
- Per-criterion audit history (collapsed by default, Radix Collapsible) (29-02)
- Audit log batch_id filter via `AuditLog → Criteria` join query (29-02)
- Enhanced grounding confidence handling with diagnostic logging (29-01)

**v1.5 Editor Patterns (2026-02-13):**
- Cauldron-style field mapping editor with entity/relation/value triplets
- Three-mode editMode state (none/text/structured) prevents impossible states
- useFieldArray for dynamic mapping management
- Field_mappings stored in conditions JSONB column
- Optional rationale textarea (reuse existing comment field)
- Page number data pipeline for scroll-to-source
- UMLS autocomplete with 300ms debounce, 3-char minimum

**v1.4 Grounding (2026-02-13):**
- MedGemma as agentic reasoner driving iterative UMLS MCP calls
- Grounding graph simplified from 4 nodes to 2 (medgemma_ground → validate_confidence)
- Display-only for temporal constraints and numeric thresholds

**v1.3 Extraction (2026-02-12):**
- Direct PDF multimodal extraction replaces pymupdf4llm
- Base64 PDF data URIs for Gemini input (later: File API in quick-3)
- [Phase 29]: Added diagnostic logging to grounding pipeline for root cause visibility
- [Phase 29]: Enhanced MedGemma prompts with explicit search term guidelines and directive evaluate instructions
- [Phase 31]: Nodes as thin orchestration with business logic in tools (pdf_parser, gemini_extractor)
- [Phase 31]: extraction_json and entities_json stored as JSON strings in PipelineState (not dicts) for minimal state size
- [Phase 31]: parse_node clears pdf_bytes and does NOT publish CriteriaExtracted outbox (PIPE-03 complete)
- [Phase 30]: RejectDialog uses predefined checkboxes (5 reason codes) for structured audit trail; Approve stays one-click per user decision (30-02)
- [Phase 30]: FieldMappingBadges returns null when no field_mappings exist; AND connector is static in read mode, editable in structured editor (30-02)
- [Phase 31]: ground_node delegates to tools (TerminologyRouter+MedGemma+field_mapper); error accumulation; AuditLog per entity
- [Phase 31]: criteria_extracted outbox removed from api-service; protocol_processor.trigger.handle_protocol_uploaded is sole handler (PIPE-03)

### Pending Todos

None.

### Blockers/Concerns

**Known Critical Issues (from research and E2E testing):**
- ~~**BUGF-01**: Grounding confidence 0% for all entities — blocks regulatory compliance~~ **FIXED in 29-01 (diagnostic logging), 29-03 (Gemini structured output)**
- ~~**BUGF-02**: Audit trail entries invisible on UI — violates 21 CFR Part 11~~ **FIXED in 29-02**
- ~~**BUGF-03**: Dashboard pending count semantic confusion — users miss work~~ **FIXED in 29-02**
- ~~**BUGF-04**: Low CUI rate (7.7%) due to non-medical entity extraction~~ **FIXED in 29-04 (three-pronged filtering)**

**Pipeline Consolidation Risks:**
- Phases 31-32 are HIGH complexity (from research SUMMARY.md)
- Outbox removal creates data loss window (Pitfall 1 from PITFALLS.md)
- Entity type mismatch between extraction and tool routing (Pitfall 3)
- Pipeline state schema merge causes type safety regression (Pitfall 10)

**Grounding Quality Notes (for Phase 31+):**
- Gemini free tier rate limit (20 req/day for 2.5-flash) blocks E2E testing — upgrade to paid tier on consumer API (NOT Vertex AI — extraction service needs File API for PDF upload, which is consumer-API-only)
- Prompt improvements confirmed working in raw MedGemma output: correctly excludes clinical statuses, uses canonical UMLS search terms
- Remaining CUI rate unknowns: UMLS concept_search may not find some terms (e.g., "PCR test result" returned 0 candidates) — may need search term retry logic or UMLS API tuning
- MCP subprocess startup is slow (~2s per entity per iteration) — direct Python import in Phase 31 will fix
- Non-deterministic: MedGemma outputs vary between runs, so CUI rate will fluctuate

**Research Flags:**
- Phase 31: API response format verification needed via test calls
- Phase 31: Must stay on consumer API (GOOGLE_API_KEY) — extraction service uses Google AI File API for PDF upload, which is not available on Vertex AI
- Phase 32: Research spike required (Gemini vs MedGemma for entity extraction)

### Current System Gaps (v2.0 scope)

- ~~No display of field_mappings in non-edit mode (badges for saved mappings)~~ **FIXED in 30-02 (FieldMappingBadges)**
- ~~No initialValues population from saved field_mappings (editor always starts empty)~~ **VERIFIED WORKING in 30-02 (buildInitialValues Priority 1)**
- No re-extraction tooling (script to re-run extraction/grounding on existing protocols)
- No corpus comparison (view/export AI vs human corrected data)

## Session Continuity

Last session: 2026-02-17
Stopped at: Completed Phase 32 Plan 01 (real NLM API terminology lookups + frontend proxy endpoints)
Resume file: None
Next action: Phase 32 Plan 03 (next plan per ROADMAP)

---

*Last updated: 2026-02-17 after completing Phase 32 Plan 01*
