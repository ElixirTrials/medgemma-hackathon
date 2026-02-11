---
phase: 03-criteria-extraction-workflow
plan: 01
subsystem: agent
tags: [pydantic, langgraph, pymupdf4llm, diskcache, jinja2, gemini, criteria-extraction]

# Dependency graph
requires:
  - phase: 01-infrastructure-data-models
    provides: "SQLModel domain models (Protocol, CriteriaBatch, Criteria), OutboxEvent"
  - phase: 01-infrastructure-data-models
    provides: "events-py outbox pattern with persist_with_outbox and OutboxProcessor"
provides:
  - "ExtractionState TypedDict defining 7-field data contract for graph nodes"
  - "Pydantic ExtractionResult schema with nested ExtractedCriterion, TemporalConstraint, NumericThreshold"
  - "AssertionStatus enum (PRESENT, ABSENT, HYPOTHETICAL, HISTORICAL, CONDITIONAL)"
  - "PDF parser with pymupdf4llm and diskcache (7-day TTL)"
  - "fetch_pdf_bytes supporting local:// and gs:// URI schemes"
  - "Jinja2 system prompt with assertion status classification guidance"
  - "Trigger handler bridging sync outbox to async graph via asyncio.run()"
affects: [03-criteria-extraction-workflow, 05-grounding]

# Tech tracking
tech-stack:
  added: [pymupdf4llm, langchain-google-vertexai]
  patterns: [ExtractionState TypedDict for graph data flow, Pydantic schema for Gemini structured output, diskcache PDF caching, Jinja2 prompt templates, sync-to-async bridge via asyncio.run]

key-files:
  created:
    - services/agent-a-service/src/agent_a_service/schemas/__init__.py
    - services/agent-a-service/src/agent_a_service/schemas/criteria.py
    - services/agent-a-service/src/agent_a_service/pdf_parser.py
    - services/agent-a-service/src/agent_a_service/prompts/system.jinja2
    - services/agent-a-service/src/agent_a_service/prompts/user.jinja2
    - services/agent-a-service/src/agent_a_service/trigger.py
  modified:
    - services/agent-a-service/src/agent_a_service/state.py
    - services/agent-a-service/src/agent_a_service/__init__.py
    - services/agent-a-service/src/agent_a_service/graph.py
    - services/agent-a-service/src/agent_a_service/nodes.py
    - services/agent-a-service/pyproject.toml
    - pyproject.toml

key-decisions:
  - "Replaced AgentState placeholder with ExtractionState TypedDict carrying 7 typed fields"
  - "Kept Pydantic nesting to max 2 levels to avoid ChatVertexAI serialization issues"
  - "Used asyncio.run() in trigger handler to bridge sync outbox to async graph (simplest for Phase 3)"
  - "PDF parser self-contained in agent-a-service with no dependency on api-service"

patterns-established:
  - "ExtractionState TypedDict: Typed state contract between LangGraph nodes"
  - "Pydantic schema with Field(description=...) for Gemini structured output guidance"
  - "diskcache for caching immutable PDF parsing results with TTL"
  - "Jinja2 prompt templates with assertion status classification examples"
  - "Sync-to-async bridge pattern for outbox event handlers"

# Metrics
duration: 5min
completed: 2026-02-11
---

# Phase 3 Plan 1: Extraction Workflow Foundation Summary

**ExtractionState TypedDict, Pydantic ExtractionResult with assertion status enum, pymupdf4llm PDF parser with diskcache, Jinja2 extraction prompts with assertion guidance, and ProtocolUploaded trigger handler**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-11T11:46:01Z
- **Completed:** 2026-02-11T11:51:54Z
- **Tasks:** 2
- **Files modified:** 12

## Accomplishments
- ExtractionState TypedDict with 7 typed fields defines complete data contract for 4-node extraction graph
- Nested Pydantic schema (ExtractionResult -> ExtractedCriterion -> TemporalConstraint/NumericThreshold) with Field descriptions for Gemini structured output
- AssertionStatus enum covers all 5 required values: PRESENT, ABSENT, HYPOTHETICAL, HISTORICAL, CONDITIONAL
- PDF parser uses pymupdf4llm with table_strategy="lines_strict" and diskcache with 7-day TTL
- System prompt provides explicit assertion detection guidance with 3+ examples per status and negation/conditionality markers
- Trigger handler bridges sync outbox to async graph via asyncio.run()

## Task Commits

Each task was committed atomically:

1. **Task 1: ExtractionState, Pydantic schemas, and PDF parser** - `2618a21` (feat)
2. **Task 2: Jinja2 extraction prompts and trigger handler** - `3fe39b2` (feat)

## Files Created/Modified
- `services/agent-a-service/src/agent_a_service/state.py` - ExtractionState TypedDict with 7 fields for graph node data flow
- `services/agent-a-service/src/agent_a_service/schemas/__init__.py` - Re-exports ExtractionResult and related types
- `services/agent-a-service/src/agent_a_service/schemas/criteria.py` - Pydantic models: ExtractionResult, ExtractedCriterion, AssertionStatus, TemporalConstraint, NumericThreshold
- `services/agent-a-service/src/agent_a_service/pdf_parser.py` - pymupdf4llm wrapper with diskcache and fetch_pdf_bytes (local:// + gs://)
- `services/agent-a-service/src/agent_a_service/prompts/system.jinja2` - System prompt for criteria extraction with assertion classification
- `services/agent-a-service/src/agent_a_service/prompts/user.jinja2` - User prompt template with title and markdown_content injection
- `services/agent-a-service/src/agent_a_service/trigger.py` - handle_protocol_uploaded event handler with asyncio.run() bridge
- `services/agent-a-service/src/agent_a_service/__init__.py` - Updated to export ExtractionState instead of AgentState
- `services/agent-a-service/src/agent_a_service/graph.py` - Updated to use ExtractionState
- `services/agent-a-service/src/agent_a_service/nodes.py` - Updated placeholder nodes to use ExtractionState
- `services/agent-a-service/pyproject.toml` - Added events-py, pymupdf, pymupdf4llm, diskcache, jinja2, langchain-google-vertexai deps
- `pyproject.toml` - Added pymupdf4llm to workspace deps, mypy overrides for new imports

## Decisions Made
- Replaced AgentState placeholder with ExtractionState TypedDict -- the old state was for a generic chat agent, the new one carries criteria extraction data between graph nodes
- Kept Pydantic model nesting to max 2 levels (ExtractionResult -> ExtractedCriterion -> TemporalConstraint/NumericThreshold) to avoid known ChatVertexAI serialization issues
- Used asyncio.run() in trigger handler rather than modifying OutboxProcessor to support async handlers -- simpler for Phase 3, can be revisited later
- PDF parser is self-contained in agent-a-service with lazy GCS imports to avoid hard dependency on google-cloud-storage in dev/test

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated nodes.py, graph.py, __init__.py to use ExtractionState**
- **Found during:** Task 1 (ExtractionState creation)
- **Issue:** Replacing AgentState with ExtractionState broke imports in nodes.py (references AgentState), graph.py (imports from nodes), and __init__.py (exports AgentState)
- **Fix:** Updated all three files to reference ExtractionState instead of AgentState. Nodes remain placeholders (will be replaced in Plan 03-02)
- **Files modified:** nodes.py, graph.py, __init__.py
- **Verification:** All imports succeed without errors
- **Committed in:** 2618a21 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Essential fix to maintain importability after state type change. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All building blocks for Plan 03-02 (LangGraph nodes) are in place
- ExtractionState defines the complete data flow contract for ingest, extract, parse, and queue nodes
- Pydantic schema ready for ChatVertexAI.with_structured_output()
- PDF parser ready for ingest node to call
- Prompts ready for extract node to render
- Trigger handler ready for graph wiring

## Self-Check: PASSED

All 8 created/modified files verified on disk. Both task commits (2618a21, 3fe39b2) verified in git log.

---
*Phase: 03-criteria-extraction-workflow*
*Completed: 2026-02-11*
