---
phase: 20-medgemma-agentic-grounding
plan: 01
subsystem: inference
tags: [vertex-ai, model-garden, medgemma, langchain, aiplatform, tenacity]

requires:
  - phase: 04-inference-grounding-libs
    provides: shared.lazy_cache lazy_singleton decorator, inference library structure
provides:
  - AgentConfig frozen dataclass with from_env() for Vertex AI configuration
  - ModelGardenChatModel LangChain BaseChatModel wrapper for Model Garden endpoints
  - create_model_loader factory returning lazy callable for vertex backend
  - _build_gemma_prompt Gemma chat template formatter
  - _predict_with_retry exponential-backoff retry for Vertex endpoint calls
affects: [20-02-PLAN, grounding-service, extraction-service]

tech-stack:
  added: [google-cloud-aiplatform, requests]
  patterns: [Gemma chat template formatting, Model Garden endpoint wrapping, tenacity retry with retryable error classification]

key-files:
  created:
    - libs/inference/src/inference/config.py
    - libs/inference/src/inference/model_garden.py
  modified:
    - libs/inference/src/inference/__init__.py
    - libs/inference/pyproject.toml
    - .env.example

key-decisions:
  - "ModelGardenChatModel as top-level class (not nested in factory function) for clean imports and type checking"
  - "Local MedGemma loading raises NotImplementedError — not needed for this phase, vertex-only"
  - "Retained exact Gemma chat template from reference: <start_of_turn>user/model delimiters with ### Instruction prefix"

patterns-established:
  - "AgentConfig.from_env() pattern: frozen dataclass with environment variable binding for model configuration"
  - "create_model_loader(config) pattern: factory returning lazy singleton callable that defers heavyweight SDK init"
  - "Retryable error classification: separate transient vs client errors for intelligent retry behavior"

duration: 3min
completed: 2026-02-12
---

# Phase 20 Plan 01: Port ModelGardenChatModel + AgentConfig Summary

**LangChain-compatible ModelGardenChatModel wrapping Vertex AI Model Garden MedGemma endpoint with Gemma chat template formatting, tenacity retry, and AgentConfig environment binding**

## Performance

- **Duration:** 3 min
- **Started:** 2026-02-12T22:32:13Z
- **Completed:** 2026-02-12T22:35:38Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Ported AgentConfig frozen dataclass with from_env() reading MODEL_BACKEND, GCP_PROJECT_ID, GCP_REGION, VERTEX_ENDPOINT_ID, VERTEX_MODEL_NAME from environment
- Ported ModelGardenChatModel as top-level BaseChatModel with Gemma prompt formatting, endpoint.predict calls, and echo-stripping
- Created create_model_loader factory with lazy_singleton caching, supporting both ChatGoogleGenerativeAI (model_name path) and ModelGardenChatModel (endpoint_id path)
- Added google-cloud-aiplatform and requests dependencies to libs/inference
- Documented Vertex AI Model Garden env vars in .env.example

## Task Commits

Each task was committed atomically:

1. **Task 1: Port AgentConfig dataclass** - `beed532` (feat)
2. **Task 2: Port ModelGardenChatModel and create_model_loader** - `2e8653f` (feat)

## Files Created/Modified
- `libs/inference/src/inference/config.py` - AgentConfig frozen dataclass with from_env() and supports_tools property
- `libs/inference/src/inference/model_garden.py` - ModelGardenChatModel, _build_gemma_prompt, _predict_with_retry, _is_retryable_error, _validate_vertex_config, create_model_loader
- `libs/inference/src/inference/__init__.py` - Public exports: AgentConfig, ModelGardenChatModel, create_model_loader
- `libs/inference/pyproject.toml` - Added google-cloud-aiplatform>=1.38.0 and requests>=2.28.0
- `.env.example` - Added MODEL_BACKEND, GCP_PROJECT_ID, GCP_REGION, VERTEX_ENDPOINT_ID variables

## Decisions Made
- ModelGardenChatModel defined as top-level class rather than nested inside a builder function (cleaner imports, better type checking)
- Local backend raises NotImplementedError since only vertex is needed for MedGemma agentic grounding
- Kept exact Gemma chat template format from reference implementation (proven to work with MedGemma)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
- inference workspace package was not installed in the root venv despite being a uv workspace member; resolved with explicit `uv pip install -e` to make imports work for verification

## User Setup Required

None - no external service configuration required. The .env.example documents the variables but they are configured as part of the existing GCP deployment workflow.

## Next Phase Readiness
- libs/inference now provides ModelGardenChatModel and AgentConfig, ready for import by grounding-service
- Plan 20-02 can build the MedGemma agentic grounding node using create_model_loader(config) to get a LangChain-compatible model
- supports_tools property enables Plan 20-02 to detect whether to use native tool calling or programmatic agentic loop

## Self-Check: PASSED

- All 4 created/modified source files verified to exist on disk
- Both task commits (beed532, 2e8653f) verified in git log
- All 6 verification imports confirmed passing
- ruff check passes clean on entire libs/inference/

---
*Phase: 20-medgemma-agentic-grounding*
*Completed: 2026-02-12*
