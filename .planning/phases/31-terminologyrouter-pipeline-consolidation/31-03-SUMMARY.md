---
phase: 31-terminologyrouter-pipeline-consolidation
plan: 03
subsystem: pipeline
tags: [langgraph, medgemma, grounding, terminology-router, field-mapper, audit-log]

# Dependency graph
requires:
  - phase: 31-02
    provides: ingest, extract, parse nodes + entities_json format
  - phase: 31-01
    provides: PipelineState TypedDict, TerminologyRouter, GroundingCandidate schemas
provides:
  - ground_node: entity grounding via TerminologyRouter + MedGemma (nodes/ground.py)
  - persist_node: Entity persistence + protocol status update (nodes/persist.py)
  - medgemma_decide: MedGemma best-match selection tool (tools/medgemma_decider.py)
  - generate_field_mappings: Gemini AutoCriteria field mapping tool (tools/field_mapper.py)
  - grounding prompts: grounding_system.jinja2, grounding_evaluate.jinja2
  - create_graph/get_graph: 5-node compiled StateGraph (graph.py)
  - handle_protocol_uploaded: unified pipeline trigger (trigger.py)
affects:
  - api-service: criteria_extracted outbox removed, protocol_processor.trigger wired

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Delegation pattern: ground_node calls tools (medgemma_decider, field_mapper)"
    - "Error accumulation: entity grounding failures logged + continue, not fatal"
    - "Two-model architecture: MedGemma reasons, Gemini structures output"
    - "AuditLog entries per grounding decision (full candidates + selection)"
    - "Field mappings stored in Criteria.conditions JSONB under field_mappings key"
    - "Partial success: pending_review even with accumulated errors"
    - "Unified trigger: one handler replaces extraction_service + grounding_service"

key-files:
  created:
    - services/protocol-processor-service/src/protocol_processor/nodes/ground.py
    - services/protocol-processor-service/src/protocol_processor/nodes/persist.py
    - services/protocol-processor-service/src/protocol_processor/tools/medgemma_decider.py
    - services/protocol-processor-service/src/protocol_processor/tools/field_mapper.py
    - services/protocol-processor-service/src/protocol_processor/prompts/grounding_system.jinja2
    - services/protocol-processor-service/src/protocol_processor/prompts/grounding_evaluate.jinja2
    - services/protocol-processor-service/src/protocol_processor/graph.py
    - services/protocol-processor-service/src/protocol_processor/trigger.py
    - services/protocol-processor-service/src/protocol_processor/main.py
    - services/protocol-processor-service/tests/test_graph.py
    - services/protocol-processor-service/tests/conftest.py
  modified:
    - services/api-service/src/api_service/main.py
    - services/protocol-processor-service/pyproject.toml

key-decisions:
  - "ground_node delegates to tools: TerminologyRouter.route_entity -> medgemma_decide -> generate_field_mappings"
  - "Error accumulation: each entity failure logged + appended to state.errors; processing continues"
  - "AuditLog written per entity: event_type=entity_grounded, full candidates + selection details"
  - "persist_node uses helper functions to reduce complexity below C901 threshold"
  - "criteria_extracted outbox removed from api-service (PIPE-03 complete)"
  - "protocol_processor.trigger.handle_protocol_uploaded wired as sole outbox handler"
  - "pytest pythonpath updated to include api-service/src for cross-service import tests"
  - "conftest.py sets DATABASE_URL env var so api_service.storage imports in tests"

# Metrics
duration: 8min
completed: 2026-02-17
---

# Phase 31 Plan 03: Ground Node, Persist Node, 5-Node Graph, and Trigger Summary

**Complete 5-node LangGraph pipeline with TerminologyRouter + MedGemma grounding, field mapping generation, AuditLog trail, unified outbox trigger, and criteria_extracted removal**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-02-17
- **Completed:** 2026-02-17
- **Tasks:** 2
- **Files modified:** 13 created, 2 modified

## Accomplishments

- Created `tools/medgemma_decider.py` with `medgemma_decide()`: MedGemma evaluates TerminologyRouter candidates, Gemini structures decision via with_structured_output
- Created `tools/field_mapper.py` with `generate_field_mappings()`: Gemini generates AutoCriteria Entity-Relation-Value-Unit decomposition from grounded entity + criterion text
- Created `nodes/ground.py` with `ground_node()`: thin orchestration routing entities through TerminologyRouter -> medgemma_decide -> generate_field_mappings with per-entity error accumulation and AuditLog entries
- Created `nodes/persist.py` with `persist_node()`: commits Entity records, updates Criteria.conditions JSONB with field_mappings, sets protocol status (pending_review or grounding_failed)
- Created `graph.py`: 5-node StateGraph (ingest->extract->parse->ground->persist) with conditional error routing; ground always proceeds to persist
- Created `trigger.py`: unified `handle_protocol_uploaded` replaces both extraction_service and grounding_service triggers; invokes full 5-node pipeline
- Updated `api_service/main.py`: removed criteria_extracted outbox handler and old service imports; wired protocol_processor.trigger (PIPE-03)
- Created 12 graph compilation and routing tests in `tests/test_graph.py`
- Added `tests/conftest.py` for DATABASE_URL env setup and updated pyproject.toml pythonpath

## Task Commits

Each task was committed atomically:

1. **Task 1: Ground node, persist node, MedGemma decider, field mapper, prompts** - `b53f812` (feat)
2. **Task 2: 5-node graph, unified trigger, api-service outbox update, graph tests** - `35826bb` (feat)

## Files Created/Modified

- `nodes/ground.py` - entity grounding with TerminologyRouter + MedGemma + AuditLog
- `nodes/persist.py` - Entity DB persistence, field_mappings in JSONB, protocol status
- `tools/medgemma_decider.py` - MedGemma evaluates candidates, Gemini structures output
- `tools/field_mapper.py` - Gemini generates AutoCriteria field mappings
- `prompts/grounding_system.jinja2` - MedGemma system prompt for terminology selection
- `prompts/grounding_evaluate.jinja2` - evaluation prompt with candidates list
- `graph.py` - 5-node StateGraph with conditional error routing
- `trigger.py` - unified handle_protocol_uploaded replacing two-service pattern
- `main.py` - minimal service entrypoint exposing create_graph/get_graph
- `tests/test_graph.py` - 12 tests: compilation, node count, routing, state shape
- `tests/conftest.py` - DATABASE_URL env setup for cross-service import tests
- `api_service/main.py` - removed criteria_extracted outbox, wired new trigger
- `pyproject.toml` - added api-service/src to pytest pythonpath

## Decisions Made

- ground_node uses delegation pattern: thin orchestration calling tools (medgemma_decider, field_mapper)
- Error accumulation: entity grounding failures appended to state.errors, processing continues
- AuditLog entry per entity: event_type=entity_grounded, includes all candidates + selected code
- persist_node refactored with helper functions (_create_entity_record, _find_criterion_and_update_mappings, _update_batch_and_protocol) to satisfy C901 complexity limit
- criteria_extracted outbox completely removed from api-service (PIPE-03)
- Single handle_protocol_uploaded wired as sole outbox handler in api-service

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added conftest.py and api-service/src to pytest pythonpath**
- **Found during:** Task 2 test run
- **Issue:** Graph tests failed with ModuleNotFoundError for api_service because ground.py and persist.py import api_service.storage at module level; pytest pythonpath did not include api-service/src
- **Fix:** Created tests/conftest.py to set DATABASE_URL env var before module collection; added api-service/src to pyproject.toml [tool.pytest.ini_options].pythonpath
- **Files modified:** tests/conftest.py (new), pyproject.toml (modified)
- **Commit:** Part of Task 2 commit (35826bb)

**2. [Rule 3 - Blocking] Extracted helper functions to reduce C901 complexity**
- **Found during:** Task 1 ruff check
- **Issue:** persist_node exceeded complexity limit (C901: 19 > 10)
- **Fix:** Extracted _update_batch_and_protocol, _find_criterion_and_update_mappings, _get_fallback_criterion_id, _persist_entities as standalone helpers
- **Files modified:** nodes/persist.py
- **Commit:** Part of Task 1 commit (b53f812)

---

**Total deviations:** 2 (both Rule 3 - Blocking, zero scope creep)

## Self-Check

---

## Self-Check: PASSED

Files verified:
- `services/protocol-processor-service/src/protocol_processor/nodes/ground.py` - EXISTS
- `services/protocol-processor-service/src/protocol_processor/nodes/persist.py` - EXISTS
- `services/protocol-processor-service/src/protocol_processor/tools/medgemma_decider.py` - EXISTS
- `services/protocol-processor-service/src/protocol_processor/tools/field_mapper.py` - EXISTS
- `services/protocol-processor-service/src/protocol_processor/graph.py` - EXISTS
- `services/protocol-processor-service/src/protocol_processor/trigger.py` - EXISTS
- `services/protocol-processor-service/tests/test_graph.py` - EXISTS

Commits verified:
- `b53f812` - feat(31-03): ground node, persist node, MedGemma decider, field mapper
- `35826bb` - feat(31-03): 5-node graph, unified trigger, api-service outbox update

Tests: 24 passed (12 graph + 12 routing)
Ruff: All checks passed
---
*Phase: 31-terminologyrouter-pipeline-consolidation*
*Completed: 2026-02-17*
