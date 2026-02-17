---
phase: 31-terminologyrouter-pipeline-consolidation
plan: 01
subsystem: pipeline
tags: [langgraph, pydantic, yaml, terminology-routing, umls, pipeline-state]

# Dependency graph
requires:
  - phase: 29-backend-bug-fixes
    provides: grounding service umls_client and medgemma patterns used here
provides:
  - protocol-processor-service package skeleton with importable PipelineState
  - Pydantic grounding schemas (GroundingCandidate, EntityGroundingResult, GroundingBatchResult)
  - YAML-based entity routing config covering all 7 entity types
  - TerminologyRouter class with UMLS/SNOMED direct Python import paths
affects:
  - 31-02 (extraction tools use PipelineState and ExtractionResult schemas)
  - 31-03+ (ground node will use TerminologyRouter directly)
  - All future phases building on protocol-processor-service

# Tech tracking
tech-stack:
  added:
    - pyyaml (YAML routing config loading)
    - structlog (structured logging)
    - protocol-processor-service workspace member added to root pyproject.toml
  patterns:
    - Minimal flat PipelineState TypedDict with JSON string fields (not nested dicts)
    - YAML-first entity routing config (no hardcoded if/elif chains)
    - TransientAPIError / PermanentAPIError exception classification for tenacity
    - Demographic entities explicitly logged and skipped (not silently dropped)
    - ToolUniverse stub pattern for pending API validation

key-files:
  created:
    - services/protocol-processor-service/pyproject.toml
    - services/protocol-processor-service/src/protocol_processor/state.py
    - services/protocol-processor-service/src/protocol_processor/schemas/grounding.py
    - services/protocol-processor-service/src/protocol_processor/config/routing.yaml
    - services/protocol-processor-service/src/protocol_processor/tools/terminology_router.py
    - services/protocol-processor-service/tests/test_terminology_router.py
  modified:
    - pyproject.toml (added workspace member, pythonpath, mypy overrides, coverage)

key-decisions:
  - "ToolUniverse _query_tooluniverse is a stub — medical tool availability unconfirmed per 31-RESEARCH Open Question 1. UMLS/SNOMED direct Python paths are fully functional."
  - "SNOMED lookup is two-step: UMLS concept_search → CUI → get_snomed_code_for_cui (reuses umls_mcp_server + grounding_service patterns)"
  - "PipelineState uses str | None for JSON fields, not nested dicts, to minimize LangGraph state serialization overhead"

patterns-established:
  - "PipelineState pattern: flat TypedDict with JSON string fields populated on-demand per node"
  - "TerminologyRouter pattern: YAML config + class with get_apis_for_entity() returning list of API names"
  - "Error classification: TransientAPIError (retried) vs PermanentAPIError (skipped with log)"

# Metrics
duration: 6min
completed: 2026-02-17
---

# Phase 31 Plan 01: Service Skeleton, PipelineState, and TerminologyRouter Summary

**protocol-processor-service scaffold with minimal PipelineState TypedDict, Pydantic grounding schemas, YAML entity routing config, and TerminologyRouter routing Medication/Condition/Lab_Value/Biomarker/Procedure/Phenotype to UMLS/SNOMED via direct Python import**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-17T06:54:47Z
- **Completed:** 2026-02-17T07:00:47Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments

- New service `protocol-processor-service` registered as uv workspace member with full dependency list (langgraph, pydantic, google-genai, tenacity, structlog, pyyaml, jinja2)
- Minimal `PipelineState` TypedDict with flat JSON string fields for 5-node pipeline (ingest/extract/parse/ground/persist)
- Pydantic grounding schemas (`GroundingCandidate`, `EntityGroundingResult`, `GroundingBatchResult`) for machine-readable agent communication
- YAML routing config covering 7 entity types: Medication/Condition/Lab_Value/Biomarker/Procedure/Phenotype (grounded) + Demographic (explicitly skipped)
- `TerminologyRouter` with full UMLS path via `umls_mcp_server.umls_api` direct import and SNOMED path via `grounding_service.umls_client`, ToolUniverse stub for future validation
- 12 tests covering: routing correctness per entity type, Demographic skip logging, unknown type warning, custom config path

## Task Commits

Each task was committed atomically:

1. **Task 1: Create service skeleton with PipelineState and grounding schemas** - `7288aa0` (feat)
2. **Task 2: Create YAML routing config and TerminologyRouter with tests** - `2b3846a` (feat)

## Files Created/Modified

- `services/protocol-processor-service/pyproject.toml` - Service dependencies and build config
- `services/protocol-processor-service/src/protocol_processor/state.py` - PipelineState TypedDict
- `services/protocol-processor-service/src/protocol_processor/schemas/grounding.py` - GroundingCandidate, EntityGroundingResult, GroundingBatchResult
- `services/protocol-processor-service/src/protocol_processor/config/routing.yaml` - Entity type → API mapping
- `services/protocol-processor-service/src/protocol_processor/tools/terminology_router.py` - TerminologyRouter class
- `services/protocol-processor-service/tests/test_terminology_router.py` - 12 routing logic tests
- `services/protocol-processor-service/src/protocol_processor/__init__.py` - Package init
- `pyproject.toml` - Workspace member addition, pythonpath, mypy overrides, coverage

## Decisions Made

- ToolUniverse stub pattern chosen for `_query_tooluniverse` — per 31-RESEARCH Open Question 1, ToolUniverse medical tool availability (RxNorm, ICD-10, LOINC, HPO) has not been confirmed via direct testing. The UMLS/SNOMED direct Python paths are fully implemented.
- SNOMED query uses two-step approach: UMLS `concept_search` → CUI → `get_snomed_code_for_cui()` from existing `grounding_service.umls_client`. This reuses validated code rather than reimplementing SNOMED lookup.
- `PipelineState` uses `str | None` for JSON fields (not nested dicts) per LangGraph best practice to minimize state serialization overhead per node transition.

## Deviations from Plan

None — plan executed exactly as written. The pre-existing files in the service directory (pdf_parser.py, gemini_extractor.py, schemas/extraction.py, nodes/*.py) were already present and were not created or modified by this plan.

**Out-of-scope items found and deferred:**
- E501 lint error in pre-existing `nodes/parse.py:55` — not caused by this plan's changes, deferred to next relevant plan.
- Mypy `import-untyped` warnings in pre-existing `tools/pdf_parser.py` and `tools/gemini_extractor.py` (shared.resilience, inference.factory) — pre-existing issue in workspace, deferred.

## Issues Encountered

- `README.md` referenced in service pyproject.toml but file didn't exist — caused hatchling build failure on first `uv sync`. Fixed by removing `readme = "README.md"` from pyproject.toml (auto-fixed inline, Rule 3 - Blocking).

## User Setup Required

None — no external service configuration required for this plan.

## Next Phase Readiness

- `PipelineState` TypedDict ready for use by all 5 pipeline nodes
- `TerminologyRouter` ready for use by the ground node (Plan 31-03+)
- Grounding schemas ready for MedGemma agent communication
- YAML routing config editable without code changes
- ToolUniverse integration requires validation (see Open Question 1 in 31-RESEARCH.md) before ground node can use RxNorm/ICD-10/LOINC/HPO paths

---
*Phase: 31-terminologyrouter-pipeline-consolidation*
*Completed: 2026-02-17*
