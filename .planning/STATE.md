# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-17)

**Core value:** Clinical researchers can upload a protocol PDF and get accurately extracted, UMLS-grounded eligibility criteria that they can review and approve in a single workflow — replacing manual extraction that takes hours per protocol.

**Current focus:** v2.1 E2E Testing & Quality Evaluation — Phase 38 (Quality Evaluation Script)

## Current Position

Phase: 38 of 39 in v2.1 (Quality Evaluation Script)
Plan: 01 complete
Status: In progress
Last activity: 2026-02-17 — 38-01 complete (quality eval script + API response fix)

Progress: [██████████████████████████░░] 67% of v2.1 (4/6 plans complete)

## Performance Metrics

**Overall Velocity:**
- Total plans completed: 67 (through Phase 38-01)
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
| v2.0 | 29-35 | 19 | ~2 hours | Shipped 2026-02-17 |
| v2.1 | 36-39 | 4 | ~13 min | In progress |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.

**v2.1 Roadmap (2026-02-17):**
- Phase 36 → 37 are the E2E pytest track (markers + fixtures first, then assertions + baseline)
- Phase 38 → 39 are the quality evaluation track (report script first, then bug catalog section)
- Tracks run independently; execution order is 36 → 37 then 38 → 39 (or in parallel)
- Quality script reads from existing DB output or triggers new pipeline runs on 2-3 PDFs from data/protocols/
- E2E tests require Docker Compose running (real PostgreSQL + real Gemini API); skip marker when not available

**v2.0 Key Decisions (2026-02-17):**
- Two-model architecture: MedGemma for medical reasoning, Gemini for JSON structuring
- uuid4 thread_id per pipeline run prevents checkpoint collision on re-extraction
- NLM direct APIs (RxNorm/ICD-10/LOINC/HPO) over ToolUniverse — free, no-auth, well-documented
- Read-only AI criterion re-run: Gemini proposes, reviewer commits via existing action endpoint

### Pending Todos

None.

### Blockers/Concerns

**E2E Test Constraints:**
- E2E tests require real Gemini API (paid tier recommended — free tier: 20 req/day for 2.5-flash)
- Docker Compose stack must be running with PostgreSQL and all services up
- Test PDFs in data/protocols/ are 90K-159K — Gemini multimodal ingestion should handle these without issue
- Pipeline is the unified 5-node LangGraph in protocol-processor-service (NOT extraction-service/grounding-service legacy paths)

**Quality Script Design Choice:**
- Script can read from existing DB data (no new pipeline runs) or trigger fresh pipeline runs
- Decision deferred to plan-phase: reading from DB is faster but requires prior pipeline runs; triggering is slower but self-contained

**v2.1 Key Decisions (2026-02-17):**
- Conservative regression baseline thresholds to avoid flaky E2E tests; tighten after stable runs
- Relative imports in test modules since tests/ lacks __init__.py

## Session Continuity

Last session: 2026-02-17
Last activity: 2026-02-17 — completed 38-01 (quality evaluation script)
Stopped at: Completed 38-01-PLAN.md
Resume file: None
Next action: Execute 38-02-PLAN.md (bug catalog section)
