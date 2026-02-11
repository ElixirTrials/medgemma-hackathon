---
phase: 05-entity-grounding-workflow
plan: 02
subsystem: api
tags: [pydantic, langgraph, umls, jinja2, httpx, entity-extraction, grounding]

# Dependency graph
requires:
  - phase: 03-criteria-extraction-workflow
    provides: ExtractionState TypedDict pattern, Pydantic schema 2-level nesting, trigger handler asyncio.run() bridge
provides:
  - GroundingState TypedDict with 8 fields for grounding workflow data flow
  - Pydantic entity schemas (EntityType, ExtractedEntity, EntityExtractionResult, BatchEntityExtractionResult)
  - Jinja2 prompts for medical entity extraction (system + user templates)
  - CriteriaExtracted trigger handler bridging outbox events to grounding graph
  - UMLS validation client with mock mode for dev without API key
affects: [05-entity-grounding-workflow, 06-matchmaking-service]

# Tech tracking
tech-stack:
  added: [httpx (UMLS client), jinja2 (prompt rendering), events-py (outbox), langchain-google-vertexai]
  patterns: [GroundingState TypedDict for graph data flow, UMLS mock mode pattern, trigger handler asyncio.run() bridge]

key-files:
  created:
    - services/agent-b-service/src/agent_b_service/schemas/entities.py
    - services/agent-b-service/src/agent_b_service/schemas/__init__.py
    - services/agent-b-service/src/agent_b_service/prompts/system.jinja2
    - services/agent-b-service/src/agent_b_service/prompts/user.jinja2
    - services/agent-b-service/src/agent_b_service/trigger.py
    - services/agent-b-service/src/agent_b_service/umls_client.py
  modified:
    - services/agent-b-service/src/agent_b_service/state.py
    - services/agent-b-service/src/agent_b_service/__init__.py
    - services/agent-b-service/src/agent_b_service/graph.py
    - services/agent-b-service/src/agent_b_service/nodes.py
    - services/agent-b-service/pyproject.toml

key-decisions:
  - "Replaced AgentState with GroundingState TypedDict following Phase 3 ExtractionState pattern"
  - "UMLS client mock mode returns True/placeholder SNOMED when no API key set for local dev"
  - "Updated placeholder nodes and graph to reference GroundingState without changing topology (deferred to 05-03)"
  - "Entity schemas use 2-level nesting max (Batch -> Result -> Entity) matching Phase 3 constraint"

patterns-established:
  - "GroundingState TypedDict: same pattern as ExtractionState for LangGraph data flow"
  - "UMLS mock mode: global flag + _log_mock_warning() for dev without credentials"
  - "trigger asyncio.run() bridge: identical pattern to agent-a for outbox handler -> async graph"

# Metrics
duration: 6min
completed: 2026-02-11
---

# Phase 5 Plan 2: Agent-B Foundation Summary

**GroundingState TypedDict, Pydantic entity schemas (6 types), Jinja2 extraction prompts, UMLS validation client with mock mode, and CriteriaExtracted trigger handler for agent-b grounding workflow**

## Performance

- **Duration:** 6 min
- **Started:** 2026-02-11T14:03:50Z
- **Completed:** 2026-02-11T14:09:25Z
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments

- GroundingState TypedDict with 8 typed fields replaces placeholder AgentState, carrying data through the 4-node grounding pipeline
- Pydantic entity schemas with EntityType enum (Condition, Medication, Procedure, Lab_Value, Demographic, Biomarker) and 2-level nesting for ChatVertexAI structured output
- Jinja2 system prompt covering all 6 entity types with extraction rules and output format; user template for batch criteria input
- CriteriaExtracted trigger handler with asyncio.run() bridge following proven agent-a pattern
- UMLS REST API validation client with automatic mock mode when UMLS_API_KEY not set

## Task Commits

Each task was committed atomically:

1. **Task 1: GroundingState, Pydantic entity schemas, and Jinja2 prompts** - `e1e96e5` (feat)
2. **Task 2: Trigger handler, UMLS validation client, and package updates** - `a91dff3` (feat)

## Files Created/Modified

- `services/agent-b-service/src/agent_b_service/state.py` - GroundingState TypedDict with 8 fields for grounding workflow
- `services/agent-b-service/src/agent_b_service/schemas/entities.py` - EntityType enum, ExtractedEntity, EntityExtractionResult, BatchEntityExtractionResult
- `services/agent-b-service/src/agent_b_service/schemas/__init__.py` - Re-exports for entity schemas
- `services/agent-b-service/src/agent_b_service/prompts/system.jinja2` - System prompt for medical entity extraction
- `services/agent-b-service/src/agent_b_service/prompts/user.jinja2` - User prompt template with criteria iteration
- `services/agent-b-service/src/agent_b_service/trigger.py` - CriteriaExtracted event handler with asyncio.run() bridge
- `services/agent-b-service/src/agent_b_service/umls_client.py` - validate_cui and get_snomed_code_for_cui with mock fallback
- `services/agent-b-service/src/agent_b_service/__init__.py` - Updated exports: GroundingState, handle_criteria_extracted
- `services/agent-b-service/src/agent_b_service/graph.py` - Updated to use GroundingState (placeholder topology preserved)
- `services/agent-b-service/src/agent_b_service/nodes.py` - Updated to use GroundingState (placeholder logic preserved)
- `services/agent-b-service/pyproject.toml` - Added events-py, langchain-google-vertexai, jinja2, httpx deps

## Decisions Made

- **GroundingState over AgentState**: Replaced message-based AgentState with purpose-built GroundingState TypedDict matching the Phase 3 ExtractionState pattern. This removes the `add_messages` reducer dependency that was not needed for data-pipeline-style workflows.
- **UMLS mock mode for dev**: When UMLS_API_KEY is empty, validate_cui returns True and get_snomed_code_for_cui returns "73211009" (placeholder). Warning logged once on first mock call. This enables full pipeline testing without UMLS credentials.
- **Preserved placeholder graph topology**: Updated graph.py and nodes.py to reference GroundingState but kept the 2-node placeholder (process -> finalize). The real 4-node graph assembly is Plan 05-03.
- **2-level nesting for Pydantic schemas**: BatchEntityExtractionResult -> EntityExtractionResult -> ExtractedEntity matches Phase 3 constraint that prevents ChatVertexAI serialization issues.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated graph.py, nodes.py, and __init__.py during Task 1**
- **Found during:** Task 1 (GroundingState creation)
- **Issue:** graph.py imported AgentState, nodes.py imported AgentState, __init__.py exported AgentState -- all would fail after state.py was replaced
- **Fix:** Updated all three files to reference GroundingState. __init__.py was listed under Task 2 but needed updating in Task 1 for import verification to pass
- **Files modified:** graph.py, nodes.py, __init__.py
- **Verification:** `from agent_b_service.state import GroundingState` succeeds
- **Committed in:** e1e96e5 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Auto-fix was necessary to keep imports working after AgentState removal. No scope creep.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. UMLS client operates in mock mode without API key.

## Next Phase Readiness

- GroundingState, schemas, prompts, trigger, and UMLS client are ready for Plan 05-03 (graph nodes and assembly)
- Plan 05-03 will implement the 4 graph nodes (extract_entities, ground_to_umls, map_to_snomed, validate_confidence) and wire them into the StateGraph
- UMLS_API_KEY environment variable will be needed for production validation (mock mode sufficient for development)

## Self-Check: PASSED

All 12 files verified present. Both task commits (e1e96e5, a91dff3) verified in git log.

---
*Phase: 05-entity-grounding-workflow*
*Completed: 2026-02-11*
