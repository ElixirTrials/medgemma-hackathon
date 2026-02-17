---
phase: 32-entity-model-ground-node-multi-code-display
plan: 01
subsystem: terminology-routing
tags: [terminology, nlm-api, rxnorm, icd10, loinc, hpo, snomed, umls, fastapi, httpx]
dependency_graph:
  requires:
    - protocol-processor-service/tools/terminology_router.py
    - api-service/umls_search.py
    - umls-mcp-server (get_umls_client, search_snomed)
  provides:
    - Real NLM API terminology lookups for RxNorm, ICD-10, LOINC, HPO
    - Frontend search proxy endpoints at /api/terminology/{system}/search
    - SNOMED search endpoint at /api/terminology/snomed/search
  affects:
    - TerminologyRouter.route_entity() now returns real candidates
    - Frontend TerminologyCombobox can search all 6 systems
tech_stack:
  added:
    - httpx>=0.27.0 (async HTTP calls to NLM APIs)
    - diskcache>=5.6.0 (7-day TTL result caching)
    - platformdirs>=4.0.0 (user cache directory)
  patterns:
    - NLM REST APIs: RxNav, Clinical Tables (ICD-10/LOINC), JAX HPO ontology
    - diskcache for API response memoization
    - tenacity retry on TransientAPIError (429, 5xx)
    - FastAPI path parameter dispatch ({system} → per-system handler)
key_files:
  created:
    - services/api-service/src/api_service/terminology_search.py
  modified:
    - services/protocol-processor-service/src/protocol_processor/tools/terminology_router.py
    - services/protocol-processor-service/src/protocol_processor/config/routing.yaml
    - services/protocol-processor-service/pyproject.toml
    - services/api-service/src/api_service/main.py
    - services/api-service/pyproject.toml
decisions:
  - "NLM direct API over ToolUniverse: ToolUniverse medical tool availability unconfirmed; NLM REST APIs are free, no-auth, well-documented"
  - "source: direct_api in routing.yaml replaces source: tooluniverse for rxnorm/icd10/loinc/hpo"
  - "diskcache optional: if not installed, caching silently disabled (graceful degradation)"
  - "SNOMED endpoint delegates to get_umls_client().search_snomed() (existing working path)"
  - "Complexity fix: _dispatch_search extracted from search_terminology to satisfy C901 < 10"
metrics:
  duration: "4 min"
  completed_date: "2026-02-17"
  tasks_completed: 2
  files_modified: 5
  files_created: 1
---

# Phase 32 Plan 01: Real Terminology API Integration Summary

Replace ToolUniverse stubs with direct NLM API calls (RxNorm, ICD-10, LOINC, HPO) and add unified /api/terminology/{system}/search proxy for frontend autocomplete across all 6 systems.

## What Was Built

### Task 1: TerminologyRouter — Real NLM API Lookups

Replaced the `_query_tooluniverse` stub in `TerminologyRouter` with `_query_direct_api`, which dispatches to:

- **RxNorm**: `https://rxnav.nlm.nih.gov/REST/approximateTerm.json?term={term}` — returns RxCUI codes
- **ICD-10**: `https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search` — NLM Clinical Tables
- **LOINC**: `https://clinicaltables.nlm.nih.gov/api/loincs/v3/search` — NLM Clinical Tables
- **HPO**: `https://ontology.jax.org/api/hp/search?q={term}` — JAX HPO ontology

All four use httpx.AsyncClient with 10s timeout, tenacity retry on 429/5xx (3 attempts, exponential backoff), and diskcache with 7-day TTL.

Updated `routing.yaml`: `source: tooluniverse` → `source: direct_api` for rxnorm, icd10, loinc, hpo.

UMLS and SNOMED `direct_python` paths unchanged.

**Commit:** `fd9f42a`

### Task 2: Terminology Search Proxy Endpoints

Created `services/api-service/src/api_service/terminology_search.py` with:

```
GET /api/terminology/{system}/search?q={term}&max_results=5
```

Supports all 6 systems:
| System | Backend |
|--------|---------|
| rxnorm | NLM RxNav approximateTerm API |
| icd10 | NLM Clinical Tables ICD-10 API |
| loinc | NLM Clinical Tables LOINC API |
| hpo | JAX HPO ontology API |
| umls | get_umls_client().search_snomed() → CUI codes |
| snomed | get_umls_client().search_snomed() → SNOMED codes |

Returns `TerminologySearchResult` with `code`, `display`, `system`, `semantic_type`, `confidence`.

Invalid system → 400. API errors → 502. UMLS not configured → 503.

Mounted in `main.py` alongside existing `umls_search_router`.

**Commit:** `000e81a`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed ruff C901 complexity in search_terminology**
- **Found during:** Task 2 (ruff check)
- **Issue:** `search_terminology` cyclomatic complexity 13 > 10 threshold
- **Fix:** Extracted `_dispatch_search()` helper function to separate dispatch logic from error handling
- **Files modified:** services/api-service/src/api_service/terminology_search.py
- **Commit:** 000e81a (included in task commit)

**2. [Rule 1 - Bug] Fixed ruff E501 line-too-long in terminology_router.py**
- **Found during:** Task 1 (ruff check)
- **Issue:** cache.set() call exceeded 88 char limit
- **Fix:** Wrapped arguments across multiple lines
- **Commit:** fd9f42a (included in task commit)

**3. [Rule 1 - Bug] Fixed ruff I001 import sort in main.py**
- **Found during:** Task 2 (ruff check)
- **Issue:** terminology_search import not sorted alphabetically
- **Fix:** Applied ruff --fix, then resolved resulting E402 by moving noqa to from line
- **Commit:** 000e81a (included in task commit)

## Self-Check: PASSED

- FOUND: services/api-service/src/api_service/terminology_search.py
- FOUND: services/protocol-processor-service/src/protocol_processor/tools/terminology_router.py
- FOUND: commit fd9f42a (feat(32-01): real NLM API terminology lookups)
- FOUND: commit 000e81a (feat(32-01): terminology search proxy endpoints)
