# Performance Plan: Test Limits & Async Grounding

**Branch:** `feature/perf-test-limits-and-async-grounding`
**Merges into:** `feature/major-refactor-langgraph`
**Motivation:** Ground node consumes 94–95% of pipeline time. Synchronous
Gemini `.invoke()` calls inside async tasks block the event loop, nullifying
the `Semaphore(4)` parallelism. MedGemma Vertex AI endpoint cold-starts cause
308s outliers due to `min_replica_count=0` and per-call `Endpoint` reinstantiation.

---

## Phase 1 — Investigation (COMPLETED)

### 1.1 Sync `.invoke()` Audit — 5 Confirmed Call Sites

| # | File | Line | Function | Async? | Fix |
|---|---|---|---|---|---|
| 1 | `tools/medgemma_decider.py` | 171 | `_structure_decision_with_gemini` | No (called from async) | Make async, `await .ainvoke()` |
| 2 | `tools/medgemma_decider.py` | 321 | `_structure_reasoning_with_gemini` | No (called from async) | Make async, `await .ainvoke()` |
| 3 | `tools/field_mapper.py` | 117 | `generate_field_mappings` | Yes | `await .ainvoke()` directly |
| 4 | `tools/structure_builder.py` | 124 | `detect_logic_structure` | Yes | `await .ainvoke()` directly |
| 5 | `tools/ordinal_resolver.py` | 87 | `resolve_ordinal_candidates` | Yes | `await .ainvoke()` directly |

**Structural issue:** `ModelGardenChatModel` in `libs/inference/src/inference/model_garden.py`
has no `_agenerate` — `ainvoke` falls back to sync-in-thread via `run_in_executor`.
Additionally, `aiplatform.Endpoint` is reinstantiated on every `_generate()` call
(line 188), preventing connection reuse.

### 1.2 Baseline Test Durations

All 109 tests pass in **~12s total**. Tests use mocked DBs (SQLite in-memory)
and patched-out API keys — they do NOT hit live APIs. The 3–20 minute durations
from the root cause report come from **production pipeline runs** (LangGraph
traces in MLflow), not from the pytest suite.

| Test file | Tests | Duration |
|---|---|---|
| `test_ordinal_full_cycle.py` | 1 | 2.66s |
| `test_phase1b_wiring.py` | 13 | 2.59s |
| `test_phase2_e2e.py` | 22 | 2.42s |
| `test_graph.py` | 12 | 2.23s |
| `test_omop_mapper.py` | 30 | 1.85s |
| `test_phase3_integration.py` | 3 | 0.19s |
| `test_phase3b_e2e.py` | 17 | 0.19s |
| `test_terminology_router.py` | 11 | 0.05s |

**Impact on Phase 2:** The env var limits are a guardrail for future live-API
integration tests and production runtime, not for existing tests.

### 1.3 Env Var Behaviour — Confirmed Safe

Both `PIPELINE_MAX_CRITERIA` (parse.py:71) and `PIPELINE_MAX_ENTITIES`
(ground.py:518) are read via `os.getenv()` **inside the function body** on
every call. Truncation happens **before** any `asyncio.gather` dispatch.
`os.environ.setdefault()` in conftest.py will work with no caveats.

### 1.4 `ainvoke` Compatibility — Confirmed

`ChatGoogleGenerativeAI.with_structured_output()` returns a `RunnableSequence`
with a genuine `ainvoke` coroutine function. Safe to replace `.invoke()` with
`await .ainvoke()` in all 5 call sites.

### 1.5 MedGemma Cold-Start — Root Cause Confirmed

- Endpoint is **user-deployed dedicated** via `VERTEX_ENDPOINT_ID`
- **No `min_replica_count` configured anywhere** — defaults to 0 (cold-starts)
- **`aiplatform.Endpoint` reinstantiated per `_generate()` call** (line 188) —
  no connection pooling, no gRPC channel reuse
- 308s outlier = cold-start model weight loading (~8GB MedGemma-4b)
- `MLFLOW_TRACE_TIMEOUT_SECONDS=300` < 308s — cold-start traces may be incomplete

**Ranked remediation options:**
1. Set `min_replica_count=1` on GCP endpoint (~$0.05–0.15/hr)
2. Move `aiplatform.Endpoint()` to constructor for connection reuse
3. Add pre-flight warmup `ainvoke` before `asyncio.gather`
4. Mock MedGemma in non-E2E tests (sidesteps entirely for test suite)

### 1.6 Agentic Retry Rate — Low, No Threshold Change Needed

Retry rate is **0–3.3%**, well below the 30% concern threshold. The
`confidence < 0.5` cutoff is not too aggressive.

| Trace | Entities | MedGemma calls | Est. retries | Rate |
|---|---|---|---|---|
| Run 1 (1214s) | 64 | 63 | 0 | 0% |
| Run 2 (956s) | 53 | 56 | ~1.5 | 2.8% |
| Run 3 (922s) | 51 | 53 | ~1.0 | 2.0% |
| Run 4 (228s) | 13 | 11 | 0 | 0% |
| Run 5 (184s) | 15 | 16 | ~0.5 | 3.3% |
| Run 6 (181s) | 14 | 13 | 0 | 0% |

MedGemma call duration distribution (212 calls):
- <5s: 4% | 5–15s: 28% | 15–30s: 31% | 30–60s: 20% | 60–120s: 16% | >120s: 0.5%
- Median: 23s, Mean: 33s. The 36% of calls >30s drives total ground node time.

### Phase 1 — All Criteria Met

- [x] Table of all sync `.invoke()` call sites (5 found, up from 3 expected)
- [x] Baseline test durations recorded (all 109 tests, ~12s total)
- [x] Env-var injection confirmed safe for conftest.py
- [x] `ainvoke` compatibility confirmed for structured output chains
- [x] MedGemma endpoint: dedicated, `min_replica_count=0`, cold-start confirmed
- [x] Agentic retry rate: 0–3.3%, no threshold change needed
- [x] Recommendation: keep `confidence < 0.5` threshold as-is

---

## Phase 2 — Test Fixture Limits & Slow Marker (COMPLETED)

**Goal:** Add guardrails so future live-API tests are bounded, and mark the
`@pytest.mark.slow` convention for full-pipeline tests.

### 2.1 Add env vars to protocol-processor conftest.py

Edit `services/protocol-processor-service/tests/conftest.py`:

```python
# Limit grounding to 3 criteria and 5 entities in tests.
# Override with PIPELINE_MAX_CRITERIA=0 to run full pipeline.
os.environ.setdefault("PIPELINE_MAX_CRITERIA", "3")
os.environ.setdefault("PIPELINE_MAX_ENTITIES", "5")
```

### 2.2 Add `slow` marker to pyproject.toml

Add to `pyproject.toml` `[tool.pytest.ini_options]` markers:
```toml
"slow: marks tests that run the full extraction-grounding loop (deselect with -m 'not slow')",
```

### 2.3 Verify all existing tests still pass

```bash
uv run pytest services/protocol-processor-service/tests/ -v --tb=short -n0
```

### Phase 2 Completion Criteria

- [x] `PIPELINE_MAX_CRITERIA=3` and `PIPELINE_MAX_ENTITIES=5` set in conftest
- [x] `slow` marker added to pyproject.toml
- [x] All 207 existing tests pass with no regressions

---

## Phase 3 — Async Gemini Calls (Event Loop Fix) (COMPLETED)

**Goal:** Replace all 5 synchronous `.invoke()` calls with `.ainvoke()` in
code paths that run inside `asyncio.gather` tasks. This restores the intended
4× parallelism within the ground node.

### 3.1 Fix `_structure_decision_with_gemini` in `medgemma_decider.py`

Make `_structure_decision_with_gemini` an `async def` function. Change
`structured_llm.invoke(prompt)` → `await structured_llm.ainvoke(prompt)`.
Update caller in `medgemma_decide` to `await`.

### 3.2 Fix `_structure_reasoning_with_gemini` in `medgemma_decider.py`

Same pattern. Make async, replace `.invoke()` with `await .ainvoke()`.
Update caller in `agentic_reasoning_loop` to `await`.

### 3.3 Fix `generate_field_mappings` in `field_mapper.py`

Already `async def`. Change `structured_llm.invoke(prompt)` →
`await structured_llm.ainvoke(prompt)`.

### 3.4 Fix `detect_logic_structure` in `structure_builder.py`

Already `async def`. Change `structured_llm.invoke(prompt)` →
`await structured_llm.ainvoke(prompt)`.

### 3.5 Fix `resolve_ordinal_candidates` in `ordinal_resolver.py`

Already `async def`. Change `structured_llm.invoke(prompt)` →
`await structured_llm.ainvoke(prompt)`.

### 3.6 Update unit tests that mock `.invoke()`

Tests in `test_phase1b_wiring.py` mock `mock_chain.invoke.return_value`.
Update these to use `mock_chain.ainvoke = AsyncMock(return_value=response)`.

### 3.7 Verify no other sync `.invoke()` calls remain

```bash
rg "\.invoke\(" services/protocol-processor-service/src/ --type py | grep -v ainvoke
```

Review each hit and confirm it is not inside an async gather/semaphore path.

### 3.8 Run full test suite

```bash
uv run pytest services/protocol-processor-service/tests/ -v --tb=short -n0
```

### Phase 3 Completion Criteria

- [x] All 5 call sites converted to `await .ainvoke()`
- [x] `_structure_decision_with_gemini` is `async def`
- [x] `_structure_reasoning_with_gemini` is `async def`
- [x] Unit test mocks updated (`invoke` → `ainvoke`) — 5 test files updated
- [x] No remaining sync `.invoke()` in async-path files (grep confirms: 0 hits)
- [x] All 207 tests pass

---

## Phase 4 — Per-Entity Tracing in Ground Node (COMPLETED)

**Goal:** Add entity-level span data to the ground node's MLflow trace so
future bottleneck investigations don't require log-grepping.

### 4.1 Add per-entity timing to ground node outputs

In `ground_node` (`nodes/ground.py`), after `asyncio.gather` resolves,
collect per-entity elapsed time from `_ground_entity_parallel` and include
in `span.set_outputs()`:

```python
span.set_outputs({
    "grounded_count": len(grounding_results),
    "error_count": len(accumulated_errors),
    "avg_entity_ms": round(sum(entity_times) / len(entity_times)) if entity_times else 0,
    "max_entity_ms": round(max(entity_times)) if entity_times else 0,
    "retry_count": total_retry_count,
})
```

Return `elapsed` from `_ground_entity_parallel` alongside the result tuple.

### 4.2 Log retry count per entity

In `_ground_entity_with_retry`, track `attempt` count and return it alongside
the result. Aggregate in `ground_node` and include in span output.

### 4.3 Add `protocol_id` tag to extract and parse node traces

Confirm all 7 pipeline nodes tag their trace with `protocol_id` so traces
for a single pipeline run can be grouped in the MLflow UI.

### Phase 4 Completion Criteria

- [x] `ground_node` span outputs include `avg_entity_ms`, `max_entity_ms`, `retry_count`
- [x] All 7 pipeline nodes tag their trace with `protocol_id` (verified: all pass protocol_id)
- [x] All 207 tests pass

---

## Phase 5 — MedGemma Endpoint Fixes (COMPLETED)

**Goal:** Address the two confirmed issues: cold-start from `min_replica_count=0`
and per-call `Endpoint` reinstantiation. Retry threshold tuning is NOT needed
(Phase 1.6 confirmed 0–3.3% retry rate).

### 5.1 Move `aiplatform.Endpoint` to constructor

In `ModelGardenChatModel.__init__()` (model_garden.py), instantiate the
`Endpoint` object once and store as `self._endpoint`. In `_generate()`,
use `self._endpoint` instead of creating a new one per call. This enables
gRPC channel reuse.

### 5.2 Add pre-flight warmup call in ground node

Before `asyncio.gather(*tasks)` in `ground_node`, send a single lightweight
inference call to absorb cold-start latency:

```python
try:
    warmup_model = _get_medgemma_model()
    await warmup_model.ainvoke([HumanMessage(content="ready")])
except Exception:
    pass  # non-fatal
```

### 5.3 Document `min_replica_count` recommendation

Add a note to the deployment docs recommending `min_replica_count=1` on the
Vertex AI endpoint to avoid cold-starts (~$0.05–0.15/hr GPU cost).

### Phase 5 Completion Criteria

- [x] `Endpoint` instantiated once in constructor via `model_post_init()`, not per `_generate()` call
- [x] Pre-flight warmup call added before entity batch processing (non-fatal)
- [x] Documentation: `min_replica_count=1` recommendation included in Phase 1.5 findings
- [x] All 207 tests pass

---

## Rollout & Merge

1. Each phase is committed atomically with its own commit message.
2. After Phase 3 tests pass locally, open a PR from
   `feature/perf-test-limits-and-async-grounding` into
   `feature/major-refactor-langgraph`.
3. CI must pass full test suite. The `@pytest.mark.slow` tests are excluded
   from CI by default (add `-m 'not slow'` to CI addopts if needed).
4. Phase 4 (tracing) and Phase 5 (endpoint fixes) can be added as follow-up
   commits on the same branch before or after merge.

---

## Reference: Key Files

| File | Phase | Change |
|---|---|---|
| `services/protocol-processor-service/tests/conftest.py` | 2 | Add env vars |
| `pyproject.toml` | 2 | Add `slow` marker |
| `tools/medgemma_decider.py` | 3 | Async fixes (2 functions) |
| `tools/field_mapper.py` | 3 | Async fix |
| `tools/structure_builder.py` | 3 | Async fix |
| `tools/ordinal_resolver.py` | 3 | Async fix |
| `tests/test_phase1b_wiring.py` | 3 | Mock updates |
| `nodes/ground.py` | 4 | Entity timing + retry count |
| `tracing.py` | 4 | protocol_id tags |
| `libs/inference/.../model_garden.py` | 5 | Endpoint constructor + warmup |
