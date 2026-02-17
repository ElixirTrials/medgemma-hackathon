---
phase: 31-terminologyrouter-pipeline-consolidation
plan: 02
subsystem: pipeline
tags: [langgraph, gemini, pydantic, pdf, extraction, gcs, sqlmodel]

# Dependency graph
requires:
  - phase: 31-01
    provides: PipelineState TypedDict and service skeleton for protocol-processor-service
  - phase: 29-03
    provides: Gemini structured output pattern with ExtractionResult schema
provides:
  - ExtractionResult Pydantic schema for Gemini structured output (schemas/extraction.py)
  - fetch_pdf_bytes async tool supporting GCS and local URIs (tools/pdf_parser.py)
  - extract_criteria_structured tool returning JSON string via Gemini File API (tools/gemini_extractor.py)
  - Jinja2 prompts with composite criteria splitting instruction (prompts/system.jinja2, user.jinja2)
  - ingest_node: fetches PDF bytes, updates protocol status (nodes/ingest.py)
  - extract_node: thin orchestration delegating to gemini_extractor tool (nodes/extract.py)
  - parse_node: creates CriteriaBatch+Criteria DB records, builds entities_json (nodes/parse.py)
affects:
  - 31-03 (ground node, persist node — consume entities_json from parse_node)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Nodes as thin orchestration: nodes call tools, tools contain business logic"
    - "JSON string state fields: extraction_json and entities_json as str not dict"
    - "State size optimization: pdf_bytes cleared by parse_node after extraction"
    - "No CriteriaExtracted outbox: pipeline continues directly to ground node (PIPE-03)"
    - "Composite criteria splitting: system prompt instructs Gemini to split independent AND/OR criteria"

key-files:
  created:
    - services/protocol-processor-service/src/protocol_processor/schemas/extraction.py
    - services/protocol-processor-service/src/protocol_processor/tools/pdf_parser.py
    - services/protocol-processor-service/src/protocol_processor/tools/gemini_extractor.py
    - services/protocol-processor-service/src/protocol_processor/prompts/__init__.py
    - services/protocol-processor-service/src/protocol_processor/prompts/system.jinja2
    - services/protocol-processor-service/src/protocol_processor/prompts/user.jinja2
    - services/protocol-processor-service/src/protocol_processor/nodes/ingest.py
    - services/protocol-processor-service/src/protocol_processor/nodes/extract.py
    - services/protocol-processor-service/src/protocol_processor/nodes/parse.py
  modified: []

key-decisions:
  - "Nodes are thin orchestration — all business logic in tools (pdf_parser, gemini_extractor)"
  - "extraction_json returned as JSON string (not dict) to minimize LangGraph state overhead"
  - "pdf_bytes cleared from state by parse_node after extraction is complete"
  - "parse_node does NOT publish CriteriaExtracted outbox event (PIPE-03: criteria_extracted outbox removed)"
  - "entities_json is a JSON string list of {criterion_id, text, criteria_type, category} for ground node"
  - "Composite criteria splitting instruction added to system prompt per user decision"
  - "Category field excludes 'demographics' in new schema — demographics not grounded to terminology"

patterns-established:
  - "Tool pattern: pure async functions in tools/ with no PipelineState dependency"
  - "Node pattern: guard on state.get('error'), delegate to tool, return minimal dict"
  - "gemini_extractor: upload PDF via File API, use response_schema=ExtractionResult, return model_dump_json()"

# Metrics
duration: 20min
completed: 2026-02-17
---

# Phase 31 Plan 02: Extraction Tools and Pipeline Nodes Summary

**Gemini File API extraction pipeline nodes (ingest, extract, parse) with tools-based architecture, ExtractionResult Pydantic schema, and composite criteria splitting prompts using PipelineState**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-02-17
- **Completed:** 2026-02-17
- **Tasks:** 2
- **Files modified:** 9 created

## Accomplishments
- Created ExtractionResult Pydantic schema adapted from extraction-service with composite criteria splitting support and no demographics category
- Created tools/pdf_parser.py with async fetch_pdf_bytes supporting GCS (with circuit breaker + retry) and local URIs
- Created tools/gemini_extractor.py with extract_criteria_structured returning JSON string via Gemini File API structured output
- Created prompts/system.jinja2 with composite criteria splitting instruction and AutoCriteria decomposition guidance
- Created three pipeline nodes (ingest, extract, parse) using PipelineState TypedDict
- parse_node creates CriteriaBatch and Criteria DB records without publishing CriteriaExtracted outbox event (PIPE-03)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create extraction tools (pdf_parser, gemini_extractor) and schemas** - `dee651d` (feat)
2. **Task 2: Create ingest, extract, and parse pipeline nodes using PipelineState** - `5d73ac8` (feat)

## Files Created/Modified
- `schemas/extraction.py` - ExtractionResult + ExtractedCriterion Pydantic models for Gemini structured output
- `tools/pdf_parser.py` - async fetch_pdf_bytes: GCS download with circuit breaker + retry, local file read
- `tools/gemini_extractor.py` - extract_criteria_structured: File API upload, structured output, returns JSON string
- `prompts/__init__.py` - Jinja2 Environment utility (render_system_prompt, render_user_prompt)
- `prompts/system.jinja2` - System prompt with composite criteria splitting rules and AutoCriteria decomposition guidance
- `prompts/user.jinja2` - User prompt requesting criteria extraction from PDF
- `nodes/ingest.py` - ingest_node: fetch PDF bytes, update protocol status to 'extracting'
- `nodes/extract.py` - extract_node: thin wrapper around extract_criteria_structured tool
- `nodes/parse.py` - parse_node: DB persistence for CriteriaBatch+Criteria, builds entities_json, clears pdf_bytes

## Decisions Made
- Nodes are thin orchestration — all business logic in tools per tools-based architecture pattern
- extraction_json stored as JSON string (not dict) to minimize LangGraph state size
- pdf_bytes cleared from state by parse_node after extraction (state size optimization)
- parse_node does NOT publish CriteriaExtracted outbox event — pipeline flows directly to ground node
- entities_json format: `[{"criterion_id": str, "text": str, "criteria_type": str, "category": str|None}]`
- Category field in ExtractedCriterion excludes 'demographics' — demographic criteria not grounded
- Protocol status set to 'grounding' by parse_node (not 'extracted') since grounding is next node

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Created minimal service skeleton not yet built by plan 01**
- **Found during:** Pre-execution check
- **Issue:** protocol-processor-service directory existed but was empty; directories needed for plan 02 tools/nodes/prompts were missing
- **Fix:** Created directory structure and discovered plan 01 had already partially run (pyproject.toml, state.py, __init__.py files existed as committed)
- **Files modified:** None additional — plan 01's work was already in place
- **Verification:** `uv run python -c "from protocol_processor.schemas.extraction import ExtractionResult"` succeeded
- **Committed in:** Part of task 1 commit

---

**Total deviations:** 1 (Rule 3 - Blocking — service skeleton check)
**Impact on plan:** Zero scope creep — only checked that plan 01 prerequisites were in place.

## Issues Encountered
- `uv run python -c "from protocol_processor.nodes.ingest import ingest_node"` fails without `services/api-service/src` in pythonpath — this is the same cross-service import pattern used in extraction-service nodes (known limitation; works at runtime via full pythonpath)
- extract_node imports cleanly since it doesn't depend on api_service

## Next Phase Readiness
- ingest, extract, parse nodes ready for plan 03 (ground node, persist node)
- entities_json format established: `[{"criterion_id", "text", "criteria_type", "category"}]`
- ground node will consume entities_json from state to route entities to terminology APIs
- Protocol status set to 'grounding' by parse_node — persist_node should set final status

---
*Phase: 31-terminologyrouter-pipeline-consolidation*
*Completed: 2026-02-17*
