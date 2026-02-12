# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-12)

**Core value:** Clinical researchers can upload a protocol PDF and get accurately extracted, UMLS-grounded eligibility criteria that they can review and approve in a single workflow -- replacing manual extraction that takes hours per protocol.
**Current focus:** v1.4 Structured Entity Display & Grounding Fixes

## Current Position

Phase: 19-extraction-structured-output (COMPLETE)
Plan: 1 of 1 in Phase 19 (DONE)
Status: Phase 19 complete, v1.4 milestone 3/3 phases done
Last activity: 2026-02-12 — Phase 19 Plan 01 executed (few-shot examples + Field descriptions)

Progress: ████████████████████ 100% (v1.4: 3/3 phases complete)

## Performance Metrics

**Overall Velocity:**
- Total plans completed: 33
- Average duration: 7.6 min
- Total execution time: 4.38 hours

| Phase | Plan | Duration | Tasks | Files |
|-------|------|----------|-------|-------|
| 17 | 01 | 2min | 2 | 1 |
| 19 | 01 | 4min | 2 | 2 |

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

### Investigation Results (v1.4)

- 3 protocols processed: 103 criteria, 266 entities
- UMLS grounding: 0/266 entities have CUI or SNOMED (100% failure)
- numeric_thresholds: 0/103 criteria populated (LLM returned empty lists) -- NOW ADDRESSED with 5 few-shot examples + enhanced Field descriptions (Phase 19)
- temporal_constraint: 47/103 criteria have data, NOW DISPLAYED in UI (Phase 17)
- Entity display works but shows "Low (0%)" and "expert_review" for all entities

### Pending Todos

None.

### Blockers/Concerns

- UMLS MCP server may need UMLS_API_KEY configured (needs investigation in Phase 18)

## Session Continuity

Last session: 2026-02-12
Stopped at: Completed 19-01-PLAN.md (Phase 19 complete, v1.4 milestone complete)
Resume file: .planning/ROADMAP.md
Next action: Validate extraction improvement with Gemini access, or plan next milestone
