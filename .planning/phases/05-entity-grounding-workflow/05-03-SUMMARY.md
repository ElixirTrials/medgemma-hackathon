---
phase: 05-entity-grounding-workflow
plan: 03
subsystem: agents
tags: [langgraph, umls, snomed, mcp, vertexai, entity-grounding, structured-output]

# Dependency graph
requires:
  - phase: 05-01
    provides: UMLS MCP server with tiered concept linking tools
  - phase: 05-02
    provides: GroundingState, entity schemas, prompts, trigger handler, UMLS client
  - phase: 03-02
    provides: Graph assembly pattern, node implementation patterns, outbox integration
provides:
  - 4-node grounding StateGraph (extract_entities -> ground_to_umls -> map_to_snomed -> validate_confidence)
  - Entity extraction using ChatVertexAI with structured output and span validation
  - UMLS grounding via MCP server with direct client fallback
  - SNOMED-CT code mapping for grounded entities
  - CUI validation, Entity record persistence, EntitiesGrounded event publishing
  - CriteriaExtracted event handler registration in api-service OutboxProcessor
affects: [06-metrics-grounding-feedback, 07-end-to-end-integration]

# Tech tracking
tech-stack:
  added: [langchain-mcp-adapters (MCP server integration)]
  patterns: [MCP-with-direct-fallback grounding, span validation post-processing, helper function extraction for C901 compliance]

key-files:
  created:
    - services/agent-b-service/src/agent_b_service/nodes/__init__.py
    - services/agent-b-service/src/agent_b_service/nodes/extract_entities.py
    - services/agent-b-service/src/agent_b_service/nodes/ground_to_umls.py
    - services/agent-b-service/src/agent_b_service/nodes/map_to_snomed.py
    - services/agent-b-service/src/agent_b_service/nodes/validate_confidence.py
  modified:
    - services/agent-b-service/src/agent_b_service/graph.py
    - services/api-service/src/api_service/main.py

key-decisions:
  - "MCP grounding with direct UMLS client fallback for resilience"
  - "Helper function extraction (_load_criteria_texts, _validate_span, _validate_cui_codes, _create_entity_record) to pass ruff C901 complexity checks"
  - "context_window stored as dict wrapper when string to match Entity model JSON column"

patterns-established:
  - "MCP-with-fallback: Try MCP server first, fall back to direct client API on failure"
  - "Span validation: Post-process LLM spans with criterion_text.find() correction"
  - "Complexity refactoring: Extract helpers from complex nodes per Phase 4 pattern"

# Metrics
duration: 8min
completed: 2026-02-11
---

# Phase 5 Plan 3: Grounding Workflow Nodes and Graph Assembly Summary

**4-node LangGraph grounding pipeline with MCP/direct UMLS fallback, span validation, SNOMED mapping, and EntitiesGrounded event publishing via outbox**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-11T14:12:16Z
- **Completed:** 2026-02-11T14:20:09Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- Complete 4-node grounding pipeline: extract_entities -> ground_to_umls -> map_to_snomed -> validate_confidence
- Entity extraction with ChatVertexAI structured output, env-toggled model (gemini/medgemma), and LLM span correction
- UMLS grounding via MCP server with automatic fallback to direct tiered client (exact -> word -> expert_review)
- CUI validation, Entity DB persistence, CriteriaBatch status update, and EntitiesGrounded event via transactional outbox
- CriteriaExtracted events now trigger the full grounding pipeline end-to-end via OutboxProcessor handler registration

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement 4 grounding workflow nodes** - `4e2fafc` (feat)
2. **Task 2: Graph assembly and api-service handler registration** - `cdd31d0` (feat)

## Files Created/Modified
- `services/agent-b-service/src/agent_b_service/nodes/__init__.py` - Re-exports all 4 node functions
- `services/agent-b-service/src/agent_b_service/nodes/extract_entities.py` - ChatVertexAI structured extraction with span validation
- `services/agent-b-service/src/agent_b_service/nodes/ground_to_umls.py` - MCP server + direct client fallback grounding
- `services/agent-b-service/src/agent_b_service/nodes/map_to_snomed.py` - SNOMED-CT code lookup per CUI
- `services/agent-b-service/src/agent_b_service/nodes/validate_confidence.py` - CUI validation, Entity persistence, outbox event
- `services/agent-b-service/src/agent_b_service/graph.py` - 4-node StateGraph with conditional error routing
- `services/api-service/src/api_service/main.py` - criteria_extracted handler registration in OutboxProcessor

## Decisions Made
- MCP grounding with direct UMLS client fallback: Provides resilience when MCP server unavailable (common in dev/test)
- Helper function extraction: Extracted _load_criteria_texts, _validate_span, _validate_cui_codes, _create_entity_record to pass ruff C901 (max complexity 10)
- context_window stored as dict wrapper: Entity model column is JSON, so string context_window is wrapped as {"text": "..."} for consistency

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Graph.py updated in Task 1 to unblock node imports**
- **Found during:** Task 1 (Node implementation)
- **Issue:** The package __init__.py imports from graph.py which imported placeholder nodes (process_node, finalize_node). After replacing nodes.py with nodes/ package, imports broke.
- **Fix:** Updated graph.py to full 4-node implementation during Task 1 instead of deferring to Task 2
- **Files modified:** services/agent-b-service/src/agent_b_service/graph.py
- **Verification:** All imports resolve, graph compiles as CompiledStateGraph
- **Committed in:** 4e2fafc (Task 1 commit)

**2. [Rule 1 - Bug] Fixed ruff C901 complexity violations**
- **Found during:** Task 1 (Node implementation)
- **Issue:** extract_entities_node (complexity 13) and validate_confidence_node (complexity 12) exceeded ruff C901 max of 10
- **Fix:** Extracted helper functions (_load_criteria_texts, _get_model_name, _validate_span, _validate_cui_codes, _create_entity_record)
- **Files modified:** extract_entities.py, validate_confidence.py
- **Verification:** ruff check passes clean
- **Committed in:** 4e2fafc (Task 1 commit)

**3. [Rule 1 - Bug] Fixed graph.py docstring line length**
- **Found during:** Task 2 (Graph assembly verification)
- **Issue:** Two lines in graph.py docstring exceeded 88 char ruff line length limit
- **Fix:** Rewrapped docstring lines
- **Files modified:** services/agent-b-service/src/agent_b_service/graph.py
- **Verification:** ruff check passes clean
- **Committed in:** cdd31d0 (Task 2 commit)

---

**Total deviations:** 3 auto-fixed (1 blocking, 2 bugs)
**Impact on plan:** All auto-fixes necessary for correctness and lint compliance. No scope creep.

## Issues Encountered
None -- all blocking issues resolved via deviation rules.

## User Setup Required
None -- no external service configuration required. UMLS operations use mock mode when UMLS_API_KEY is not set.

## Next Phase Readiness
- Phase 5 entity grounding workflow is complete
- End-to-end pipeline wired: protocol upload -> criteria extraction -> entity grounding
- Ready for Phase 6 (metrics/feedback) and Phase 7 (end-to-end integration)
- No blockers

## Self-Check: PASSED

All 7 created/modified files verified present. Both task commits (4e2fafc, cdd31d0) verified in git log. All 4 nodes import successfully. Graph compiles as CompiledStateGraph. 44 tests pass with 0 regressions.

---
*Phase: 05-entity-grounding-workflow*
*Completed: 2026-02-11*
