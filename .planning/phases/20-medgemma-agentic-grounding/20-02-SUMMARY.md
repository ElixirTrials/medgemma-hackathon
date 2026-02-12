---
phase: 20-medgemma-agentic-grounding
plan: 02
subsystem: grounding
tags: [medgemma, umls, snomed, mcp, langgraph, agentic, pydantic, jinja2]

# Dependency graph
requires:
  - phase: 20-01
    provides: ModelGardenChatModel + AgentConfig in libs/inference for MedGemma endpoint integration
provides:
  - medgemma_ground_node implementing agentic extract-search-evaluate loop
  - Pydantic schemas for MedGemma agentic JSON responses (AgenticAction, ExtractedEntityAction, GroundingSelection)
  - 3 Jinja2 prompt templates for agentic system, extract, and evaluate turns
  - Simplified 2-node grounding graph (medgemma_ground -> validate_confidence)
  - GroundingState with iteration_history for telemetry
affects: [grounding-service, api-service]

# Tech tracking
tech-stack:
  added: []
  patterns: [programmatic-agentic-loop, json-structured-output-parsing, criterion-id-entity-mapping]

key-files:
  created:
    - services/grounding-service/src/grounding_service/schemas/agentic_actions.py
    - services/grounding-service/src/grounding_service/prompts/agentic_system.jinja2
    - services/grounding-service/src/grounding_service/prompts/agentic_extract.jinja2
    - services/grounding-service/src/grounding_service/prompts/agentic_evaluate.jinja2
    - services/grounding-service/src/grounding_service/nodes/medgemma_ground.py
  modified:
    - services/grounding-service/src/grounding_service/nodes/__init__.py
    - services/grounding-service/src/grounding_service/graph.py
    - services/grounding-service/src/grounding_service/state.py
    - services/grounding-service/tests/test_grounding_graph.py

key-decisions:
  - "criterion_id field added to ExtractedEntityAction for entity-to-criteria mapping"
  - "Programmatic agentic loop (code orchestrates MedGemma <-> UMLS MCP) since MedGemma lacks native tool calling"
  - "concept_search used for both CUI and SNOMED in one call, replacing separate map_to_snomed node"
  - "Old node files preserved for reference/rollback (extract_entities, ground_to_umls, map_to_snomed)"
  - "Refactored complex functions to satisfy ruff C901 complexity limits"

patterns-established:
  - "Agentic loop: MedGemma extract -> UMLS MCP search -> MedGemma evaluate/refine, max 3 iterations"
  - "JSON parsing with markdown fence stripping for LLM responses"
  - "Fallback to expert_review when JSON parsing or max iterations fail"

# Metrics
duration: 8min
completed: 2026-02-12
---

# Phase 20 Plan 02: Create Agentic Grounding Node + Rewire Graph Summary

**MedGemma agentic grounding node with iterative UMLS MCP concept_search loop, replacing 4-node pipeline with 2-node graph**

## Performance

- **Duration:** 8 min
- **Started:** 2026-02-12T22:40:31Z
- **Completed:** 2026-02-12T22:48:30Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments
- Created medgemma_ground_node implementing a programmatic agentic loop: MedGemma extracts entities -> code searches UMLS via MCP concept_search -> MedGemma evaluates and selects best matches (max 3 iterations with refine capability)
- Simplified grounding graph from 4 nodes (extract_entities -> ground_to_umls -> map_to_snomed -> validate_confidence) to 2 nodes (medgemma_ground -> validate_confidence)
- Built comprehensive Pydantic schemas (AgenticAction, ExtractedEntityAction with criterion_id, GroundingSelection) and 3 Jinja2 prompt templates with few-shot examples
- All 5 graph tests pass with new 2-node structure; ruff clean across all files

## Task Commits

1. **Tasks 1+2: Create agentic node + rewire graph** - `1c0b25f` (feat)

**Plan metadata:** pending

## Files Created/Modified
- `services/grounding-service/src/grounding_service/schemas/agentic_actions.py` - Pydantic models for MedGemma agentic JSON responses
- `services/grounding-service/src/grounding_service/prompts/agentic_system.jinja2` - System prompt with entity types, JSON schema, few-shot examples
- `services/grounding-service/src/grounding_service/prompts/agentic_extract.jinja2` - User prompt for initial entity extraction turn
- `services/grounding-service/src/grounding_service/prompts/agentic_evaluate.jinja2` - User prompt for UMLS result evaluation/refinement
- `services/grounding-service/src/grounding_service/nodes/medgemma_ground.py` - Agentic grounding node with MedGemma + UMLS MCP loop
- `services/grounding-service/src/grounding_service/nodes/__init__.py` - Updated exports to 2-node set
- `services/grounding-service/src/grounding_service/graph.py` - Simplified 2-node graph with error routing
- `services/grounding-service/src/grounding_service/state.py` - Added iteration_history field to GroundingState
- `services/grounding-service/tests/test_grounding_graph.py` - Updated tests for 2-node graph structure

## Decisions Made
- Added `criterion_id` field to `ExtractedEntityAction` schema so MedGemma can tag each entity with its source criterion ID from the XML id attribute -- simpler than post-hoc matching by span positions
- Used programmatic agentic loop pattern (code orchestrates MedGemma <-> UMLS MCP turns) because MedGemma Model Garden endpoint doesn't support native tool calling
- concept_search returns both CUI and SNOMED code, making the separate map_to_snomed node and its UMLS REST API call redundant
- Preserved old node files (extract_entities.py, ground_to_umls.py, map_to_snomed.py) for reference -- removed from exports only
- Refactored _normalize_search_results and medgemma_ground_node into smaller helpers to satisfy ruff C901 complexity limit (max 10)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Refactored functions exceeding ruff C901 complexity limit**
- **Found during:** Task 1 (ruff verification)
- **Issue:** _normalize_search_results (complexity 12) and medgemma_ground_node (complexity 12) exceeded ruff's max of 10
- **Fix:** Extracted _parse_json_as_list, _normalize_tool_message_content, _fallback_entities_for_criteria, _fallback_from_entities, and _run_evaluate_loop helper functions
- **Files modified:** services/grounding-service/src/grounding_service/nodes/medgemma_ground.py
- **Verification:** uv run ruff check passes clean
- **Committed in:** 1c0b25f

---

**Total deviations:** 1 auto-fixed (1 bug/lint)
**Impact on plan:** Refactoring improved code quality with no behavioral change. No scope creep.

## Issues Encountered
- grounding_service.__init__.py imports trigger.py which imports api_service.storage at module level, causing import errors when running tests without api-service on PYTHONPATH. Pre-existing issue resolved by setting PYTHONPATH to include api-service/src during test runs. Not a regression from this plan.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Agentic grounding node is complete and graph is rewired
- Ready for end-to-end integration testing with live MedGemma endpoint and UMLS MCP server
- MedGemma endpoint requires MODEL_BACKEND=vertex and VERTEX_ENDPOINT_ID env vars to be configured

---
*Phase: 20-medgemma-agentic-grounding*
*Completed: 2026-02-12*
