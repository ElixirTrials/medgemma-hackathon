---
phase: 05-entity-grounding-workflow
plan: 01
subsystem: grounding
tags: [fastmcp, umls, mcp-server, httpx, medical-grounding]

# Dependency graph
requires:
  - phase: 01-infrastructure-data-models
    provides: Entity SQLModel with umls_cui, snomed_code, grounding fields
provides:
  - UMLS MCP server package with 3 tools (concept_search, concept_linking, semantic_type_prediction)
  - UMLS REST API client (UMLSClient) and mock fallback (MockUMLSClient)
  - Factory function get_umls_client() for environment-based client selection
  - fastmcp and langchain-mcp-adapters installed in workspace
affects: [05-entity-grounding-workflow, agent-b-service]

# Tech tracking
tech-stack:
  added: [fastmcp, langchain-mcp-adapters]
  patterns: [MCP server with FastMCP decorators, tiered grounding fallback, mock client factory pattern]

key-files:
  created:
    - services/umls-mcp-server/src/umls_mcp_server/server.py
    - services/umls-mcp-server/src/umls_mcp_server/umls_api.py
    - services/umls-mcp-server/pyproject.toml
    - services/umls-mcp-server/src/umls_mcp_server/__init__.py
  modified:
    - pyproject.toml

key-decisions:
  - "Mock client returns canned diabetes results (C0011849, SNOMED 73211009) for dev without UMLS credentials"
  - "Tools instantiate client per-request via factory (not module-level) so mock/real is env-determined at call time"
  - "Tiered grounding: exact match (0.95) -> word search (0.75) -> expert review (0.0) with clear method labels"

patterns-established:
  - "FastMCP tool pattern: @mcp.tool() decorator with typed signatures and docstrings"
  - "Mock/real client factory: get_umls_client() returns MockUMLSClient when env var unset"
  - "Tiered grounding: structured fallback with confidence scores and method labels for audit trail"

# Metrics
duration: 5min
completed: 2026-02-11
---

# Phase 5 Plan 1: UMLS MCP Server Summary

**FastMCP-based UMLS MCP server with concept_search, concept_linking (tiered grounding), and semantic_type_prediction tools backed by UMLS REST API with mock fallback**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-11T14:03:22Z
- **Completed:** 2026-02-11T14:09:07Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- UMLS REST API client (UMLSClient) with search, get_concept, and get_snomed_code methods using httpx async
- MockUMLSClient with identical interface returning canned responses for development without UMLS credentials
- FastMCP server exposing 3 tools: concept_search, concept_linking, semantic_type_prediction
- concept_linking implements tiered grounding: exact match (0.95) -> semantic similarity (0.75) -> expert review (0.0)
- fastmcp and langchain-mcp-adapters installed as workspace dependencies for downstream use in 05-03

## Task Commits

Each task was committed atomically:

1. **Task 1: UMLS REST API client and mock fallback** - `1ba77bc` (feat)
2. **Task 2: FastMCP server with 3 UMLS tools** - `3481a07` (feat)

## Files Created/Modified
- `services/umls-mcp-server/pyproject.toml` - Package definition with fastmcp and httpx deps
- `services/umls-mcp-server/src/umls_mcp_server/__init__.py` - Package init
- `services/umls-mcp-server/src/umls_mcp_server/umls_api.py` - UMLS REST API client, mock client, and factory function
- `services/umls-mcp-server/src/umls_mcp_server/server.py` - FastMCP server with 3 tools
- `services/umls-mcp-server/README.md` - Package readme
- `pyproject.toml` - Added workspace member, fastmcp/langchain-mcp-adapters deps, mypy ignores, pythonpath

## Decisions Made
- Mock client returns canned diabetes results (C0011849, SNOMED 73211009) for development without UMLS credentials
- Tools instantiate client per-request via get_umls_client() factory (not module-level) so mock/real is determined by environment at call time
- Tiered grounding strategy: exact match (0.95) -> word search (0.75) -> expert review (0.0) with clear method labels on each result for audit trail
- Added README.md to umls-mcp-server (required by hatchling build system)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added README.md for hatchling build**
- **Found during:** Task 1 (package setup)
- **Issue:** hatchling build system requires README.md referenced in pyproject.toml
- **Fix:** Created minimal README.md for the umls-mcp-server package
- **Files modified:** services/umls-mcp-server/README.md
- **Verification:** uv sync completes without errors
- **Committed in:** 1ba77bc (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Minimal -- required file for build system. No scope creep.

## Issues Encountered
- Workspace member not directly importable via `uv run python -c` without explicit PYTHONPATH -- the pythonpath entries in pyproject.toml only apply to pytest. Verified imports work correctly in pytest context and with PYTHONPATH set.

## User Setup Required

None - no external service configuration required. Mock mode works without UMLS_API_KEY.

## Next Phase Readiness
- UMLS MCP server ready for integration with agent-b-service grounding workflow (05-02, 05-03)
- fastmcp and langchain-mcp-adapters installed for MCP-to-LangGraph bridge in 05-03
- Mock mode enables full development/testing workflow without UMLS credentials

## Self-Check: PASSED

All 6 created files verified present. Both task commits (1ba77bc, 3481a07) verified in git log.

---
*Phase: 05-entity-grounding-workflow*
*Completed: 2026-02-11*
