# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-17)

**Core value:** Clinical researchers can upload a protocol PDF and get accurately extracted, UMLS-grounded eligibility criteria that they can review and approve in a single workflow — replacing manual extraction that takes hours per protocol.

**Current focus:** Phase 42 — Pipeline Stability + UMLS Resilience (In Progress)

## Current Position

Phase: 42 of 43 in current milestone
Plan: 01 complete (01 of 02 plans complete)
Status: In Progress
Last activity: 2026-02-18 — 42-01 complete (MLflow trace leak fixed via try/finally, upload bind mount + SHA-256 dedup added)

Progress: [█████████████████████████████░] Phase 42 — Plan 01/02 complete

## Performance Metrics

**Overall Velocity:**
- Total plans completed: 68 (through Phase 38-02)
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
| v2.1 | 36-39 | 5 | ~16 min | In progress |
| Phase 39 P01 | 121s | 2 tasks | 1 files |
| Phase 40 P02 | 3 | 2 tasks | 0 files |

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
- [Phase 39]: Bug Catalog placed after LLM Assessment; orphan detection skipped per plan constraints

**Phase 40-01 Key Decisions (2026-02-17):**
- All 6 terminology systems accessed via ToolUniverse SDK (single dependency, single pattern)
- TTLCache(ttl=300) for autocomplete caching — 5-minute TTL appropriate for real-time use
- Demographic entities routed to umls+snomed (NOT skipped); MedGemma handles derived mapping
- Consent entities skipped before grounding — not groundable to medical terminology codes
- MedGemma 3-question agentic reasoning loop in single prompt (minimize token usage)
- Gemini collaborates on reasoning structuring via gemini_suggestion field
- expert_review routing as reasoning string marker (not new field) — avoids schema change

**Phase 40-02 Key Decisions (2026-02-17):**
- Docker container is running stale pre-Phase-40 image; code verification done via direct uv run calls (correct approach)
- 5/5 tested systems return real codes (ICD10, RxNorm, HPO, LOINC, UMLS) — all pass, plan required only 3
- [Phase 40]: Docker container running stale pre-Phase-40 image; code verification done via direct uv run calls (correct approach)
- [Phase 40]: 5/5 tested systems return real codes (ICD10, RxNorm, HPO, LOINC, UMLS) — all pass, plan required only 3

**Phase 42-01 Key Decisions (2026-02-18):**
- end_trace() inside finally is a no-op when span closes normally via context manager — safe to always call
- MLFLOW_TRACE_TIMEOUT_SECONDS=300 is safety net only (process-kill), not primary fix (try/finally is primary)
- Bind mount (../data/uploads:/app/uploads) over named volume — dev workflow benefits from browsable host directory
- SHA-256 symlink deduplication preserves URI compatibility while saving disk space via .hash-index.json

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

Last session: 2026-02-18
Last activity: 2026-02-18 — completed 42-01 (MLflow trace leak fixed, upload bind mount + SHA-256 dedup, gaps B14/B13 resolved)
Stopped at: Completed 42-01-PLAN.md
Resume file: None
Next action: Phase 42-02 — ToolUniverse resilience
