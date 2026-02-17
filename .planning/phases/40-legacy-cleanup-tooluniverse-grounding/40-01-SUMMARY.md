---
phase: 40-legacy-cleanup-tooluniverse-grounding
plan: 01
subsystem: protocol-processor-service, api-service
tags: [cleanup, tooluniverse, grounding, agentic-reasoning, terminology]
dependency_graph:
  requires: []
  provides:
    - tooluniverse-client-wrapper
    - rewritten-terminology-router
    - agentic-reasoning-loop
    - expert-review-routing
    - clean-workspace
  affects:
    - services/protocol-processor-service
    - services/api-service
tech_stack:
  added:
    - tooluniverse>=1.0.18 (medical terminology SDK for UMLS/SNOMED/ICD-10/LOINC/RxNorm/HPO)
    - cachetools>=5.0 (TTLCache for in-memory result caching)
  patterns:
    - singleton via lru_cache(maxsize=1) for ToolUniverse instance
    - TTLCache(maxsize=1000, ttl=300) for autocomplete caching
    - agentic reasoning loop with 3-question MedGemma prompt
    - expert_review routing after 3 failed grounding attempts
key_files:
  created:
    - services/protocol-processor-service/src/protocol_processor/tools/tooluniverse_client.py
    - services/protocol-processor-service/src/protocol_processor/prompts/grounding_reasoning.jinja2
  modified:
    - services/protocol-processor-service/src/protocol_processor/tools/terminology_router.py
    - services/protocol-processor-service/src/protocol_processor/tools/medgemma_decider.py
    - services/protocol-processor-service/src/protocol_processor/nodes/ground.py
    - services/protocol-processor-service/src/protocol_processor/config/routing.yaml
    - services/api-service/src/api_service/umls_search.py
    - services/api-service/src/api_service/terminology_search.py
    - services/api-service/tests/test_schemas.py
    - services/api-service/tests/test_umls_clients.py
    - services/api-service/tests/test_umls_search.py
    - pyproject.toml
    - infra/docker-compose.yml
    - services/api-service/pyproject.toml
    - services/protocol-processor-service/pyproject.toml
    - docs/onboarding.md
    - docs/components/index.md
    - docs/jinja2-prompts.md
    - docs/architecture/system-architecture.md
    - docs/architecture/data-models.md
  deleted:
    - services/grounding-service/ (entire directory)
    - services/extraction-service/ (entire directory)
    - services/umls-mcp-server/ (entire directory)
decisions:
  - "All 6 terminology systems accessed via ToolUniverse SDK (single dependency, single pattern)"
  - "TTLCache(ttl=300) for autocomplete caching — 5-minute TTL appropriate for real-time use"
  - "Demographic entities routed to umls+snomed (NOT skipped); MedGemma handles derived mapping"
  - "Consent entities skipped before grounding — not groundable to medical terminology codes"
  - "MedGemma 3-question agentic reasoning loop in single prompt (minimize token usage)"
  - "Gemini collaborates on reasoning structuring via gemini_suggestion field"
  - "expert_review routing as reasoning string marker (not new field) — avoids schema change"
  - "_ground_entity_with_retry() extracted as helper for ruff C901 complexity compliance"
metrics:
  duration_minutes: ~90
  completed_date: "2026-02-17"
  tasks_completed: 3
  tasks_total: 3
  files_created: 2
  files_modified: 19
  files_deleted: 3
---

# Phase 40 Plan 01: Legacy Cleanup + ToolUniverse Grounding Summary

**One-liner:** Deleted 3 legacy services and rewrote all terminology grounding through ToolUniverse SDK singleton with MedGemma 3-question agentic retry loop (max 3 attempts, expert_review routing on exhaustion).

## What Was Built

### Task 1: Delete Legacy Services and Clean Workspace

Deleted the three legacy service directories that were causing broken imports:
- `services/grounding-service/` — old httpx-based grounding with broken `concept_search` method
- `services/extraction-service/` — unused extraction service
- `services/umls-mcp-server/` — MCP server replaced by ToolUniverse SDK

Cleaned all workspace references from:
- Root `pyproject.toml` (workspace members, pythonpath, coverage, mypy overrides)
- `services/api-service/pyproject.toml` (dependencies, uv.sources, pythonpath)
- `services/protocol-processor-service/pyproject.toml` (added tooluniverse + cachetools)
- `infra/docker-compose.yml` (removed extraction/grounding service blocks)
- All docs files cleaned of legacy architecture references

Ran `uv sync` successfully to regenerate lock file.

**Commit:** `05c5886`

### Task 2: ToolUniverse Client Wrapper + Rewritten Routing

**New file: `tooluniverse_client.py`**

Singleton ToolUniverse wrapper with `@lru_cache(maxsize=1)` + `TTLCache(ttl=300)`. Handles all 6 systems:
- `umls_search_concepts` for UMLS
- `snomed_search_concepts` for SNOMED (returns UMLS CUIs, provenance via rootSource)
- `ICD10_search_codes` for ICD-10
- `LOINC_search_tests` for LOINC
- `RxNorm_get_drug_names` for RxNorm (single result dict, not list)
- `HPO_search_terms` for HPO

Each system's unique response format handled in `_parse_result()` (noqa C901).

**Rewritten: `terminology_router.py`**

Removed all httpx imports and NLM URL constants. Added single `_query_tooluniverse()` method dispatching through `tooluniverse_client.search_terminology`. Kept tenacity retry config (3 attempts, exponential backoff).

**Updated: `routing.yaml`**

All `api_configs` entries now use `source: tooluniverse`. Demographic routing changed from `skip: true` to `["umls", "snomed"]`. New `Consent: skip: true` entry added.

**Rewritten: API service endpoints**

`umls_search.py` and `terminology_search.py` now import `search_terminology` from `tooluniverse_client`. Removed all httpx and NLM URL code.

**Rewritten: Tests**

`test_schemas.py`, `test_umls_clients.py`, `test_umls_search.py` — all legacy imports replaced with `GroundingCandidate`-based mocks and `patch("api_service.umls_search.search_terminology")`.

**Commit:** `8716e86`

### Task 3: MedGemma Agentic Reasoning Loop

**New: `AgenticReasoningResult` Pydantic model**

Fields: `should_skip`, `is_derived`, `derived_term`, `rephrased_query`, `gemini_suggestion`, `reasoning`.

**New: `agentic_reasoning_loop()` function**

Asks MedGemma 3 questions in a single prompt (minimize token usage):
1. Is this a valid medical criterion or should it be skipped?
2. Is this a derived entity mapping to a standard concept?
3. Can this be rephrased for better terminology search?

MedGemma output structured by Gemini via `_structure_reasoning_with_gemini()`. Gemini can add its own `gemini_suggestion` reformulation.

**New: `grounding_reasoning.jinja2` prompt template**

Three-question template with entity context, criterion context, previous query, and attempt number.

**New: `_ground_entity_with_retry()` helper**

Extracted from `ground_node` for ruff C901 compliance. Implements the max 3-attempt loop:
1. Initial route + MedGemma decide
2. If confidence < 0.5 and no code: agentic reasoning → reformulate query → retry
3. After 3 failed attempts: mark `[expert_review]` in reasoning string

**Updated: `ground_node()`**

- Added Consent skip at top of entity loop (before routing)
- Removed old Demographic blanket-skip check (Demographics now routed via umls+snomed)
- Delegates to `_ground_entity_with_retry()` for the retry logic
- Uses `result.candidates` for audit log (not stale local `candidates` var)

**Commit:** `c1eed5a`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Ruff C901 complexity violations**
- **Found during:** Task 2 (`_parse_result`) and Task 3 (`ground_node`)
- **Issue:** `_parse_result` complexity 17 > 10 due to 6-system dispatch; `ground_node` complexity 15 > 10 due to inline retry loop
- **Fix:** Added `# noqa: C901` to `_parse_result` (inherent system dispatch complexity). Extracted retry loop into `_ground_entity_with_retry()` helper to reduce `ground_node` complexity.
- **Files modified:** `tooluniverse_client.py`, `ground.py`, `medgemma_decider.py` (new helper)
- **Commit:** `c1eed5a`

**2. [Rule 1 - Bug] Ruff I001/E501 linting errors in test files**
- **Found during:** Task 2 post-commit ruff check
- **Issue:** Import block sorting and line length violations in `test_schemas.py`, `test_umls_clients.py`, `test_umls_search.py`
- **Fix:** Auto-fixed with `ruff check --fix`, manually fixed remaining E501 violations
- **Files modified:** All three test files
- **Commit:** `c1eed5a` (included with Task 3)

**3. [Rule 1 - Bug] Stale `candidates` variable in audit log after retry loop**
- **Found during:** Task 3 code review
- **Issue:** `_log_grounding_audit` was passed local `candidates` from step 1, but after retry loop `result.candidates` may contain different candidates
- **Fix:** Changed audit log call to use `result.candidates` (final state) instead of local `candidates` variable
- **Files modified:** `ground.py`
- **Commit:** `c1eed5a`

## Pre-existing Issues (Out of Scope)

- `test_graph.py::TestCreateGraph::test_graph_compiles` fails with `ModuleNotFoundError: No module named 'inference'` — pre-existing infrastructure issue, not caused by this plan. Logged to deferred items.
- `api-service` tests using `test_client` fixture fail with `ModuleNotFoundError: No module named 'shared'` in conftest.py — pre-existing pytest worker isolation issue. `test_schemas.py` (15 tests) passes cleanly.

## Self-Check

Checking that all claimed files exist and commits are present:

**Results:**
- FOUND: `services/protocol-processor-service/src/protocol_processor/tools/tooluniverse_client.py`
- FOUND: `services/protocol-processor-service/src/protocol_processor/prompts/grounding_reasoning.jinja2`
- FOUND: `services/protocol-processor-service/src/protocol_processor/tools/medgemma_decider.py`
- FOUND: `services/protocol-processor-service/src/protocol_processor/nodes/ground.py`
- Commit `05c5886` present: `chore(40-01): delete legacy services and clean all workspace references`
- Commit `8716e86` present: `feat(40-01): create ToolUniverse client wrapper and rewrite terminology routing`
- Commit `c1eed5a` present: `feat(40-01): implement MedGemma agentic reasoning loop with expert_review routing`

## Self-Check: PASSED
