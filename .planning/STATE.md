# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-12)

**Core value:** Clinical researchers can upload a protocol PDF and get accurately extracted, UMLS-grounded eligibility criteria that they can review and approve in a single workflow -- replacing manual extraction that takes hours per protocol.
**Current focus:** v1.4 Structured Entity Display & Grounding Fixes — COMPLETE

## Current Position

Phase: 21-gemini-3-flash-upgrade (COMPLETE)
Plan: 1 of 1 in Phase 21
Status: v1.4 milestone complete — all 5 phases (17-21) executed
Last activity: 2026-02-13 — Completed 21-01: upgrade Gemini model to gemini-3-flash-preview

Progress: ████████████████████ 100% (v1.4: 5/5 phases complete)

## Performance Metrics

**Overall Velocity:**
- Total plans completed: 37
- Average duration: 7.3 min
- Total execution time: 4.8 hours

| Phase | Plan | Duration | Tasks | Files |
|-------|------|----------|-------|-------|
| 17 | 01 | 2min | 2 | 1 |
| 18 | 01 | 10min | 3 | 6 |
| 19 | 01 | 4min | 2 | 2 |
| 20 | 01 | 3min | 2 | 5 |
| 20 | 02 | 8min | 2 | 9 |
| 21 | 01 | 1min | 1 | 5 |

## Accumulated Context

### Decisions

- v1.0: Google OAuth for authentication (fits GCP ecosystem)
- v1.0: Docker Compose infrastructure with PostgreSQL, MLflow, PubSub emulator
- v1.2: Terraform for GCP Cloud Run deployment (paused, phases 13-15)
- v1.3: Direct PDF multimodal extraction replaces pymupdf4llm markdown conversion
- v1.3: Base64 PDF data URIs for Gemini multimodal input
- v1.4: Investigation found 4 problems — grounding 100% failed, thresholds never populated, temporal constraints not displayed, no threshold UI
- v1.4: Display-only for temporal constraints and thresholds (no inline editing in CriterionCard)
- v1.4: Indigo color for temporal badges, teal for numeric thresholds (distinct from existing color scheme)
- v1.4: extractThresholdsList handles 3 possible data shapes defensively (wrapper, array, single-object)
- v1.4: XML-style few-shot examples for Gemini structured output (5 examples covering age, lab, score, conditional, combined)
- v1.4: Dual approach for structured output improvement (prompt examples + Pydantic Field descriptions)
- v1.4: langchain-mcp-adapters 0.2.x ainvoke() returns list-of-content-blocks, not dict/string
- v1.4: UMLS atoms API returns code as full URL; extract trailing segment for SNOMED code
- v1.4: MedGemma as agentic reasoner — drives grounding via iterative UMLS MCP calls (not passive entity extractor)
- v1.4: ModelGardenChatModel + AgentConfig ported from gemma-hackathon for Vertex endpoint integration
- v1.4: MedGemma doesn't support native tool calling — programmatic agentic loop (code orchestrates MedGemma ↔ UMLS MCP turns)
- v1.4: concept_search returns both CUI and SNOMED — map_to_snomed direct API call becomes redundant
- v1.4: Criteria extraction upgraded to gemini-3-flash-preview
- v1.4: ModelGardenChatModel as top-level class in libs/inference (not nested in factory function) for clean imports
- v1.4: criterion_id field on ExtractedEntityAction for entity-to-criteria mapping in agentic loop
- v1.4: Grounding graph simplified from 4 nodes to 2 (medgemma_ground -> validate_confidence)
- v1.4: Old grounding node files preserved for reference/rollback (removed from exports only)

### Investigation Results (v1.4)

- 3 protocols processed: 103 criteria, 266 entities
- UMLS grounding: 0/266 entities had CUI or SNOMED (100% failure) -- FIXED in Phase 18 (MCP result parsing + SNOMED extraction)
- numeric_thresholds: 0/103 criteria populated -- ADDRESSED in Phase 19 (few-shot examples + enhanced Field descriptions)
- temporal_constraint: 47/103 criteria have data -- DISPLAYED in Phase 17
- MedGemma endpoint configured but NOT wired -- FIXED in Phase 20 (agentic grounding with ModelGardenChatModel)
- Gemini model upgraded from gemini-2.5-flash to gemini-3-flash-preview in Phase 21

### Pending Todos

None.

### Blockers/Concerns

None.

## Session Continuity

Last session: 2026-02-13
Stopped at: Completed Phase 21 — v1.4 milestone fully executed
Resume file: .planning/phases/21-gemini-3-flash-upgrade/21-01-SUMMARY.md
Next action: /gsd:complete-milestone or /gsd:new-milestone for next iteration
