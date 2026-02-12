---
phase: 18-grounding-pipeline-debug-fix
plan: 01
subsystem: grounding
tags: [umls, snomed, mcp, langchain-mcp-adapters, fastmcp, grounding-pipeline]

# Dependency graph
requires:
  - phase: 05-entity-grounding-workflow
    provides: "4-node LangGraph grounding graph, MCP server, UMLS client"
provides:
  - "Working UMLS grounding pipeline: entities resolve to CUI and SNOMED codes"
  - "Robust MCP tool result parsing (handles str, list, ToolMessage, dict)"
  - "Fixed SNOMED code extraction from UMLS atoms API URL-format responses"
  - "Diagnostic logging in map_to_snomed and MCP server"
  - "Integration tests proving end-to-end grounding with real UMLS API"
affects: [19-threshold-extraction, frontend-entity-display, grounding-pipeline]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "MCP tool result normalization via _normalize_tool_result (handles list/str/ToolMessage/dict)"
    - "Content block parsing for langchain-mcp-adapters 0.2.x list-of-blocks format"
    - "URL-to-code extraction for UMLS atoms API responses"
    - "Context manager pattern for UmlsClient (with get_umls_client())"

key-files:
  created:
    - "services/grounding-service/tests/test_grounding_integration.py"
  modified:
    - "services/grounding-service/src/grounding_service/nodes/ground_to_umls.py"
    - "services/grounding-service/src/grounding_service/nodes/map_to_snomed.py"
    - "services/grounding-service/src/grounding_service/umls_client.py"
    - "services/umls-mcp-server/src/umls_mcp_server/server.py"
    - "services/umls-mcp-server/src/umls_mcp_server/umls_api.py"

key-decisions:
  - "Handle list-of-content-blocks as primary MCP tool result format for langchain-mcp-adapters 0.2.x"
  - "Extract SNOMED codes from URL-format values in UMLS atoms API responses"
  - "Keep per-entity try/except but separate JSONDecodeError from generic exceptions"

patterns-established:
  - "_normalize_tool_result: canonical pattern for parsing MCP tool results across adapter versions"
  - "_extract_code_from_value: URL-to-code extraction for UMLS API fields"
  - "Per-entity error handling logs type(e).__name__, str(e), and exc_info=True"

# Metrics
duration: 10min
completed: 2026-02-12
---

# Phase 18 Plan 01: Grounding Pipeline Debug & Fix Summary

**Fixed UMLS/SNOMED grounding pipeline: MCP tool result parsing handles list-of-content-blocks format, SNOMED atoms extraction handles URL-format codes, 4/4 known medical terms now resolve to CUI and SNOMED codes**

## Performance

- **Duration:** 10 min
- **Started:** 2026-02-12T20:47:53Z
- **Completed:** 2026-02-12T20:58:32Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments
- Fixed the root cause of 100% grounding failure: langchain-mcp-adapters 0.2.x returns a list of content blocks, not a dict, so `isinstance(result, dict)` always failed
- Fixed SNOMED code extraction: UMLS atoms API returns codes as full URLs and result as direct list, not nested dict
- All 4 known medical terms (acetaminophen, osteoarthritis, Heparin, diabetes mellitus) now resolve to UMLS CUI
- SNOMED lookup for acetaminophen (CUI C0000970) returns code 387517004
- Added diagnostic logging across the pipeline for future debugging
- 9/9 tests pass (5 existing + 4 new integration tests)

## Task Commits

Each task was committed atomically:

1. **Task 1: Fix MCP tool result parsing and error handling** - `7de6791` (fix)
2. **Task 2: Add diagnostic logging to map_to_snomed and MCP server** - `f8fac77` (feat)
3. **Task 3: End-to-end verification with integration tests** - `957fa81` (test)

## Files Created/Modified
- `services/grounding-service/src/grounding_service/nodes/ground_to_umls.py` - Added _normalize_tool_result() and _parse_content_blocks() for robust MCP result parsing; improved error logging
- `services/grounding-service/src/grounding_service/umls_client.py` - Switched to context manager pattern (with get_umls_client())
- `services/grounding-service/src/grounding_service/nodes/map_to_snomed.py` - Added per-entity try/except with logging and summary breakdown
- `services/umls-mcp-server/src/umls_mcp_server/server.py` - Added debug logging to concept_linking tool
- `services/umls-mcp-server/src/umls_mcp_server/umls_api.py` - Fixed _extract_snomed_code_from_atoms to handle list response and URL-format codes
- `services/grounding-service/tests/test_grounding_integration.py` - 4 integration tests proving end-to-end grounding works

## Decisions Made
- **MCP result format**: langchain-mcp-adapters 0.2.x ainvoke() returns `list[{"type": "text", "text": "<json>"}]`, not a dict or string. Added list handling as first-class path in _normalize_tool_result.
- **SNOMED URL extraction**: UMLS atoms API returns `code` field as full URL (e.g., `https://uts-ws.nlm.nih.gov/rest/content/2025AB/source/SNOMEDCT_US/387517004`). Added _extract_code_from_value to parse the trailing code segment.
- **Keep per-entity exception handling**: Rather than removing the per-entity try/except (which the research suggested), kept it but improved it with full exception logging (type, message, stack trace) and separate JSONDecodeError handling.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] langchain-mcp-adapters 0.2.x returns list of content blocks, not string/dict**
- **Found during:** Task 3 (integration testing)
- **Issue:** Plan assumed MCP tool result would be a string or ToolMessage, but ainvoke() actually returns `list[{"type": "text", "text": "<json>"}]`. The initial fix in Task 1 handled str/ToolMessage/dict but missed the list format.
- **Fix:** Added `_parse_content_blocks()` helper and `isinstance(raw_result, list)` check to `_normalize_tool_result()`
- **Files modified:** `services/grounding-service/src/grounding_service/nodes/ground_to_umls.py`
- **Verification:** Integration test `test_mcp_concept_linking_returns_cui` passes
- **Committed in:** 957fa81 (Task 3 commit)

**2. [Rule 1 - Bug] UMLS atoms API returns different response structure and URL-format codes**
- **Found during:** Task 3 (SNOMED lookup test)
- **Issue:** `_extract_snomed_code_from_atoms` expected `{"result": {"results": [...]}}` but API returns `{"result": [...]}` (direct list). Also, `code` field contains full URL, not plain numeric code.
- **Fix:** Updated `_extract_snomed_code_from_atoms` to handle both response structures; added `_extract_code_from_value` to parse SNOMED code from URL strings.
- **Files modified:** `services/umls-mcp-server/src/umls_mcp_server/umls_api.py`
- **Verification:** `get_snomed_code('C0000970')` returns `'387517004'`; integration test `test_snomed_lookup_for_known_cui` passes
- **Committed in:** 957fa81 (Task 3 commit)

---

**Total deviations:** 2 auto-fixed (2 Rule 1 bugs)
**Impact on plan:** Both bugs were discovered through integration testing (Task 3) and were critical for the pipeline to work end-to-end. Without these fixes, grounding would still silently fail. No scope creep.

## Issues Encountered
- mypy reports pre-existing error on `shared.resilience` import (missing py.typed marker) - not related to this plan's changes
- pytest-asyncio runs in strict mode in grounding-service (despite root config having auto mode) - used explicit `@pytest.mark.asyncio` markers

## User Setup Required
None - UMLS_API_KEY was already configured in .env file.

## Next Phase Readiness
- Grounding pipeline is now functional: entities get real UMLS CUI and SNOMED codes
- Frontend entity display should now show actual confidence scores and grounding methods instead of "Low (0%)" and "expert_review"
- Ready for Phase 19 (threshold extraction) or re-grounding existing protocols
- To re-ground existing protocols, trigger the outbox processor or re-upload a protocol

## Self-Check: PASSED

- All 7 claimed files exist on disk
- All 3 task commits verified (7de6791, f8fac77, 957fa81)
- 9/9 tests pass (5 existing + 4 new)
- Linting clean across grounding-service and umls-mcp-server

---
*Phase: 18-grounding-pipeline-debug-fix*
*Completed: 2026-02-12*
