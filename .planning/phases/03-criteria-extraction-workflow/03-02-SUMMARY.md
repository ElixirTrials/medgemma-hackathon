---
phase: 03-criteria-extraction-workflow
plan: 02
subsystem: agent
tags: [langgraph, gemini, criteria-extraction, stategraph, outbox, structured-output, assertion-refinement]

# Dependency graph
requires:
  - phase: 03-criteria-extraction-workflow
    plan: 01
    provides: "ExtractionState TypedDict, Pydantic ExtractionResult schema, PDF parser, Jinja2 prompts, trigger handler"
  - phase: 01-infrastructure-data-models
    provides: "SQLModel domain models (Protocol, CriteriaBatch, Criteria), OutboxEvent, persist_with_outbox"
provides:
  - "4-node LangGraph StateGraph: ingest -> extract -> parse -> queue with conditional error routing"
  - "Ingest node: PDF fetch + parse + cache + status update to 'extracting'"
  - "Extract node: ChatVertexAI.with_structured_output(ExtractionResult) with Jinja2 prompts"
  - "Parse node: assertion refinement (negation/conditionality markers), confidence calibration, deduplication"
  - "Queue node: CriteriaBatch + Criteria persistence + CriteriaExtracted event via outbox"
  - "OutboxProcessor handler registration for protocol_uploaded -> extraction workflow"
  - "End-to-end extraction pipeline: ProtocolUploaded event -> persisted CriteriaBatch + CriteriaExtracted event"
affects: [04-criteria-review-ui, 05-grounding]

# Tech tracking
tech-stack:
  added: [langchain-google-vertexai]
  patterns: [4-node LangGraph StateGraph with conditional error routing, graph nodes as cross-service integration glue, assertion refinement post-processing, confidence calibration heuristics, outbox handler registration]

key-files:
  created:
    - services/agent-a-service/src/agent_a_service/nodes/__init__.py
    - services/agent-a-service/src/agent_a_service/nodes/ingest.py
    - services/agent-a-service/src/agent_a_service/nodes/extract.py
    - services/agent-a-service/src/agent_a_service/nodes/parse.py
    - services/agent-a-service/src/agent_a_service/nodes/queue.py
  modified:
    - services/agent-a-service/src/agent_a_service/graph.py
    - services/api-service/src/api_service/main.py
    - pyproject.toml
  deleted:
    - services/agent-a-service/src/agent_a_service/nodes.py

key-decisions:
  - "Graph nodes import from api-service for DB access -- intentional cross-service integration glue pattern"
  - "Added langchain-google-vertexai to root pyproject.toml for workspace-wide availability"
  - "Parse node uses pure Python post-processing (no LLM) for assertion refinement and dedup"
  - "Conditional error routing after ingest and extract; parse->queue always proceeds"

patterns-established:
  - "Graph nodes as integration glue: allowed to import cross-service (e.g., api_service.storage.engine)"
  - "Assertion refinement: negation/conditionality marker detection as LLM output post-processing"
  - "Confidence calibration: heuristic score adjustments for unusual extraction patterns"
  - "Deduplication: normalized text comparison keeping higher-confidence entries"
  - "OutboxProcessor handler registration in api-service lifespan for event-driven workflow triggers"

# Metrics
duration: 9min
completed: 2026-02-11
---

# Phase 3 Plan 2: LangGraph Nodes and Extraction Pipeline Summary

**4-node LangGraph StateGraph (ingest/extract/parse/queue) with Gemini structured output, assertion refinement post-processing, CriteriaBatch persistence via outbox, and ProtocolUploaded handler registration in api-service**

## Performance

- **Duration:** 9 min
- **Started:** 2026-02-11T11:55:17Z
- **Completed:** 2026-02-11T12:04:19Z
- **Tasks:** 3 (2 auto + 1 checkpoint verified)
- **Files modified:** 8

## Accomplishments
- 4-node LangGraph StateGraph compiles and routes correctly with conditional error paths after ingest and extract nodes
- Ingest node fetches PDF bytes, parses to markdown with diskcache, and sets protocol status to "extracting"
- Extract node invokes ChatVertexAI.with_structured_output(ExtractionResult) with Jinja2-rendered system/user prompts
- Parse node refines assertion status using negation marker detection (10 patterns) and conditionality markers (6 patterns), calibrates confidence scores, and deduplicates near-identical criteria
- Queue node persists CriteriaBatch + Criteria records and publishes CriteriaExtracted event via outbox pattern, updates protocol status to "extracted"
- OutboxProcessor in api-service lifespan now dispatches "protocol_uploaded" events to the extraction workflow handler
- All 44 existing tests pass with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement 4 LangGraph nodes and assemble graph** - `59345d9` (feat)
2. **Task 2: Register trigger handler in api-service outbox processor** - `ef87f5a` (feat)
3. **Task 3: Verify extraction workflow end-to-end** - checkpoint verified by user

## Files Created/Modified
- `services/agent-a-service/src/agent_a_service/nodes/__init__.py` - Re-exports all 4 node functions
- `services/agent-a-service/src/agent_a_service/nodes/ingest.py` - PDF ingestion node: fetch + parse + cache + status update
- `services/agent-a-service/src/agent_a_service/nodes/extract.py` - Gemini extraction node with structured output
- `services/agent-a-service/src/agent_a_service/nodes/parse.py` - Post-processing: assertion refinement, confidence calibration, dedup
- `services/agent-a-service/src/agent_a_service/nodes/queue.py` - Persistence: CriteriaBatch + Criteria + CriteriaExtracted event
- `services/agent-a-service/src/agent_a_service/graph.py` - Replaced 2-node placeholder with 4-node StateGraph + error routing
- `services/api-service/src/api_service/main.py` - Added handle_protocol_uploaded handler to OutboxProcessor
- `pyproject.toml` - Added langchain-google-vertexai dependency
- `services/agent-a-service/src/agent_a_service/nodes.py` - DELETED (replaced by nodes/ package)

## Decisions Made
- Graph nodes (ingest, extract, parse, queue) intentionally import from api-service for DB access -- they are integration glue, unlike utility modules like pdf_parser.py which must stay self-contained
- Added langchain-google-vertexai to root pyproject.toml because uv workspace member dependencies are not auto-installed at the root level
- Parse node uses pure Python post-processing (no LLM call) for assertion refinement and deduplication -- faster and deterministic
- Conditional error routing after ingest and extract nodes; parse and queue always proceed (they handle errors internally via early return)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added langchain-google-vertexai to root dependencies**
- **Found during:** Task 1 (verification step)
- **Issue:** `langchain-google-vertexai` was declared in agent-a-service's pyproject.toml but not installed in the workspace environment -- `uv run python` could not import the module
- **Fix:** Ran `uv add langchain-google-vertexai` to add it to root pyproject.toml
- **Files modified:** pyproject.toml
- **Verification:** Import succeeds, graph compiles as CompiledStateGraph
- **Committed in:** 59345d9 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Essential fix for module availability. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required. Gemini API credentials are only needed at runtime when actually invoking the extraction workflow.

## Next Phase Readiness
- Complete end-to-end extraction pipeline: ProtocolUploaded -> ingest -> extract -> parse -> queue -> CriteriaExtracted
- Protocol status lifecycle: uploaded -> extracting -> extracted
- CriteriaBatch with linked Criteria records persisted with pending_review status
- Ready for Phase 4 (Criteria Review UI) to display and allow human review of extracted criteria
- Ready for Phase 5 (Grounding) to consume CriteriaExtracted events for UMLS entity grounding

## Self-Check: PASSED

All 7 created/modified files verified on disk. Deleted file (nodes.py) confirmed removed. Both task commits (59345d9, ef87f5a) verified in git log.

---
*Phase: 03-criteria-extraction-workflow*
*Completed: 2026-02-11*
