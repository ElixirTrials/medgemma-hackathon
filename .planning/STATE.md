# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-16)

**Core value:** Clinical researchers can upload a protocol PDF and get accurately extracted, UMLS-grounded eligibility criteria that they can review and approve in a single workflow — replacing manual extraction that takes hours per protocol.

**Current focus:** Phase 29 - Backend Bug Fixes

## Current Position

Phase: 29 of 34 (Backend Bug Fixes)
Plan: 1 of 2 in current phase
Status: In progress
Last activity: 2026-02-16 — Completed Plan 29-02 (audit trail and pending count fixes)

Progress: [████████████████████████░░░░░░░░░░] 82% (28/34 phases complete)

## Performance Metrics

**Overall Velocity:**
- Total plans completed: 59 (through Phase 28)
- Average duration: ~15 min
- Total execution time: ~14.8 hours (across v1.0, v1.3, v1.4, v1.5)

**By Milestone:**

| Milestone | Phases | Plans | Total Time | Status |
|-----------|--------|-------|------------|--------|
| v1.0 | 1-7 | 24 | ~3.6 hours | Shipped 2026-02-12 |
| v1.1 | 8-10 | 6 | ~45 min | Paused |
| v1.3 | 16 | 1 | ~7 min | Shipped 2026-02-12 |
| v1.4 | 17-21 | 7 | ~2 hours | Shipped 2026-02-13 |
| v1.5 | 22-28 | 11 | ~8 hours | Shipped 2026-02-13 |
| v2.0 | 29-34 | 1/TBD | ~4 min | In progress |

**Recent Plans:**
| Phase | Plan | Duration | Date       | Notes                                           |
| ----- | ---- | -------- | ---------- | ----------------------------------------------- |
| 29    | 02   | 4 min    | 2026-02-16 | Audit trail visibility and pending count fixes  |
| 28    | 02   | 8 min    | 2026-02-13 | Evidence linking UI with click-to-scroll        |
| 27    | 01   | 6 min    | 2026-02-13 | Multi-mapping support for structured criteria   |
| 28    | 01   | 4 min    | 2026-02-13 | Page number data pipeline                       |

*Metrics from MILESTONES.md and previous roadmaps*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.

**v2.0 Architecture (2026-02-16):**
- ToolUniverse Python API with selective loading (not MCP subprocess)
- Flat 5-node LangGraph pipeline (ingest→extract→parse→ground→persist)
- UMLS retained via direct Python import (not MCP subprocess)
- Store errors in state, use Command for routing
- Remove criteria_extracted outbox, retain protocol_uploaded

**Phase 29 Bug Fixes (2026-02-16):**
- Batch status auto-transition: `in_progress → reviewed/approved/rejected` when all criteria reviewed
- Criteria-level pending count query (not batch status) for dashboard accuracy
- Per-criterion audit history (collapsed by default, Radix Collapsible)
- Audit log batch_id filter via `AuditLog → Criteria` join query

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

### Pending Todos

None.

### Blockers/Concerns

**Known Critical Issues (from research and E2E testing):**
- **BUGF-01**: Grounding confidence 0% for all entities — blocks regulatory compliance
- ~~**BUGF-02**: Audit trail entries invisible on UI — violates 21 CFR Part 11~~ **FIXED in 29-02**
- ~~**BUGF-03**: Dashboard pending count semantic confusion — users miss work~~ **FIXED in 29-02**

**Pipeline Consolidation Risks:**
- Phases 31-32 are HIGH complexity (from research SUMMARY.md)
- Outbox removal creates data loss window (Pitfall 1 from PITFALLS.md)
- Entity type mismatch between extraction and tool routing (Pitfall 3)
- Pipeline state schema merge causes type safety regression (Pitfall 10)

**Research Flags:**
- Phase 31: API response format verification needed via test calls
- Phase 32: Research spike required (Gemini vs MedGemma for entity extraction)

### Current System Gaps (v2.0 scope)

- No display of field_mappings in non-edit mode (badges for saved mappings)
- No initialValues population from saved field_mappings (editor always starts empty)
- No re-extraction tooling (script to re-run extraction/grounding on existing protocols)
- No corpus comparison (view/export AI vs human corrected data)

## Session Continuity

Last session: 2026-02-16
Stopped at: Completed Phase 29 Plan 02 (audit trail and pending count fixes)
Resume file: None
Next action: Execute Phase 29 Plan 01 (grounding confidence bug fix)

---

*Last updated: 2026-02-16 after completing Phase 29 Plan 02*
