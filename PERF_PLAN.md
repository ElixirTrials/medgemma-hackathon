# Performance Plan: Test Limits & Async Grounding

**Branch:** `feature/perf-test-limits-and-async-grounding`
**Merges into:** `feature/major-refactor-langgraph`
**Motivation:** Ground node consumes 94–95% of pipeline time. Tests run full
extraction-grounding loops (50–80 entities) against live APIs with no limiting,
causing 3–20 minute test durations. Synchronous Gemini `.invoke()` calls inside
async tasks block the event loop, nullifying the `Semaphore(4)` parallelism.

---

## Phase 1 — Investigation

**Goal:** Produce precise measurements and a confirmed list of every offending
call site before touching production code.

### 1.1 Audit all sync LLM calls inside async paths

Search the codebase for `.invoke(` calls made inside async functions or tasks.
Every `structured_llm.invoke(...)` and `ChatGoogleGenerativeAI(...).invoke(...)`
that runs within `asyncio.gather` or `async with semaphore` is a confirmed
event-loop blocker.

**Files to audit:**
- `services/protocol-processor-service/src/protocol_processor/tools/medgemma_decider.py`
  — `_structure_decision_with_gemini()` (line ~171)
  — `_structure_reasoning_with_gemini()` (line ~321)
- `services/protocol-processor-service/src/protocol_processor/tools/field_mapper.py`
  — `generate_field_mappings()` (line ~117)
- `services/protocol-processor-service/src/protocol_processor/nodes/ground.py`
  — confirm no other sync calls are hidden inside `_ground_entity_parallel`
- `libs/inference/src/inference/` — confirm `ModelGardenChatModel` exposes
  `ainvoke` and that it is truly non-blocking

**Output of 1.1:** A table listing each call site with:
- file + line number
- current form (`invoke` vs `ainvoke`)
- whether LangChain's `ChatGoogleGenerativeAI` supports `ainvoke` for this
  use case (structured output)

### 1.2 Measure baseline test durations

Run the slowest test files individually and capture wall-clock time:

```bash
uv run pytest services/protocol-processor-service/tests/test_phase2_e2e.py -v --tb=short 2>&1 | tee /tmp/baseline_phase2.txt
uv run pytest services/protocol-processor-service/tests/test_phase3_integration.py -v --tb=short 2>&1 | tee /tmp/baseline_phase3.txt
uv run pytest services/protocol-processor-service/tests/test_phase1b_wiring.py -v --tb=short 2>&1 | tee /tmp/baseline_phase1b.txt
```

Record per-test duration from pytest output. These are the before numbers for
the regression check after Phase 2 and Phase 3.

### 1.3 Confirm `PIPELINE_MAX_CRITERIA` / `PIPELINE_MAX_ENTITIES` behaviour

Read `services/protocol-processor-service/src/protocol_processor/nodes/parse.py`
(around line 71) and `nodes/ground.py` (around line 518) to confirm:
- The env vars are read at node entry time (not at import time).
- Setting them in `conftest.py` via `os.environ` will take effect without
  process restart.
- The truncation happens before any API calls, not after.

**Output of 1.3:** Confirmed yes/no + any caveats (e.g. env var is read once
at module level, requiring a different injection point).

### 1.4 Verify `ChatGoogleGenerativeAI.with_structured_output` supports `ainvoke`

LangChain's `with_structured_output` wraps the model in a `RunnableSequence`.
Confirm whether calling `.ainvoke()` on that sequence is safe and returns the
same Pydantic model as `.invoke()`.

```bash
uv run python -c "
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel
class T(BaseModel):
    x: int
import inspect
chain = ChatGoogleGenerativeAI(model='gemini-2.5-flash', google_api_key='dummy').with_structured_output(T)
print('has ainvoke:', hasattr(chain, 'ainvoke'))
print('ainvoke is coroutine function:', inspect.iscoroutinefunction(chain.ainvoke))
"
```

**Output of 1.4:** Confirmed that `ainvoke` exists and is async. If not,
document the alternative (e.g. `asyncio.get_event_loop().run_in_executor`).

### 1.5 Check MedGemma `ModelGardenChatModel` cold-start / keep-warm options

Read `libs/inference/src/inference/model_garden.py` (or equivalent) to
understand how `create_model_loader` configures the Vertex AI endpoint.
Determine if there is:
- A provisioned throughput / dedicated endpoint option
- A keep-alive or ping strategy
- An environment variable controlling endpoint ID

**Output of 1.5:** A description of current Vertex AI config and whether a
keep-warm call before the test suite would eliminate the 308s outlier.

### Phase 1 Completion Criteria

- [ ] Table of all sync `.invoke()` call sites in async paths
- [ ] Baseline test durations recorded
- [ ] Env-var injection confirmed safe for conftest.py
- [ ] `ainvoke` compatibility confirmed for `ChatGoogleGenerativeAI.with_structured_output`
- [ ] MedGemma endpoint cold-start root cause understood

---

## Phase 2 — Test Fixture Limits

**Goal:** Cut test time by 80–90% by limiting the number of entities processed
per test run. Zero production code changes. No mock additions — tests still
exercise real API paths, just with fewer entities.

### 2.1 Add env vars to root conftest.py

Edit `services/protocol-processor-service/tests/conftest.py`:

```python
# Limit grounding to 3 criteria and 5 entities in all tests.
# Override with PIPELINE_MAX_CRITERIA=0 to run full pipeline.
os.environ.setdefault("PIPELINE_MAX_CRITERIA", "3")
os.environ.setdefault("PIPELINE_MAX_ENTITIES", "5")
```

Use `setdefault` so individual tests or CI overrides can increase the limit
(e.g. `PIPELINE_MAX_CRITERIA=0 pytest -m e2e`).

### 2.2 Add an `@pytest.mark.slow` mark and guard for full-pipeline tests

Any test that intentionally exercises the full extraction+grounding loop (e.g.
true E2E protocol upload tests in `tests/e2e/`) should be marked:

```python
@pytest.mark.slow
def test_full_pipeline_real_protocol():
    ...
```

Add to `pyproject.toml` `[tool.pytest.ini_options]` markers:
```toml
"slow: marks tests that run the full extraction-grounding loop (deselect with -m 'not slow')",
```

CI runs the default suite (fast). A separate `make test-slow` or nightly job
runs `pytest -m slow`.

### 2.3 Re-run baseline tests and confirm speedup

```bash
uv run pytest services/protocol-processor-service/tests/ -v --tb=short 2>&1 | tee /tmp/after_phase2.txt
```

**Expected:** Tests that previously took 3–20 minutes now complete in under
90 seconds.

### Phase 2 Completion Criteria

- [ ] `PIPELINE_MAX_CRITERIA=3` and `PIPELINE_MAX_ENTITIES=5` set in conftest
- [ ] `@pytest.mark.slow` applied to full-pipeline E2E tests
- [ ] All existing tests still pass (no regressions)
- [ ] Wall-clock reduction of ≥80% confirmed vs Phase 1 baseline

---

## Phase 3 — Async Gemini Calls (Event Loop Fix)

**Goal:** Replace every synchronous `.invoke()` with `.ainvoke()` in code paths
that run inside `asyncio.gather` tasks. This restores the intended 4× parallelism
within the ground node and eliminates event loop starvation.

### 3.1 Fix `_structure_decision_with_gemini` in `medgemma_decider.py`

Change:
```python
result = structured_llm.invoke(prompt)
```
To:
```python
result = await structured_llm.ainvoke(prompt)
```

Make `_structure_decision_with_gemini` an async function and update its callers
(`medgemma_decide` and `agentic_reasoning_loop`) which are already `async`.

### 3.2 Fix `_structure_reasoning_with_gemini` in `medgemma_decider.py`

Same pattern — make async, replace `.invoke()` with `await .ainvoke()`. Update
`agentic_reasoning_loop` call site.

### 3.3 Fix `generate_field_mappings` in `field_mapper.py`

`generate_field_mappings` is already `async def`. Change:
```python
result = structured_llm.invoke(prompt)
```
To:
```python
result = await structured_llm.ainvoke(prompt)
```

No caller changes needed (callers already `await` it).

### 3.4 Verify no other sync `.invoke()` calls remain in async paths

```bash
uv run grep -rn "\.invoke(" services/protocol-processor-service/src/ \
  --include="*.py" | grep -v "ainvoke" | grep -v "model.invoke\|run\.invoke"
```

Review each remaining hit and confirm it is either:
- Not inside an async function, or
- Not inside a `asyncio.gather` / semaphore path

### 3.5 Update unit tests that mock `.invoke()`

Tests in `test_phase1b_wiring.py` mock `mock_chain.invoke.return_value`. Update
these mocks to also set `mock_chain.ainvoke = AsyncMock(return_value=response)`
so the updated async paths are covered.

### 3.6 Verify parallelism improvement

With `PIPELINE_MAX_ENTITIES=20` (temporarily override for this measurement),
run the ground node against a real protocol and compare wall-clock to cumulative
API time. Expected: wall-clock ≈ cumulative_api_time / 4 (Semaphore slots).

### Phase 3 Completion Criteria

- [ ] `_structure_decision_with_gemini` is `async def` using `await .ainvoke()`
- [ ] `_structure_reasoning_with_gemini` is `async def` using `await .ainvoke()`
- [ ] `generate_field_mappings` uses `await .ainvoke()`
- [ ] No remaining sync `.invoke()` calls inside async-path files (confirmed by grep)
- [ ] All unit tests updated and passing
- [ ] Observed ground node wall-clock is ≤ 30% of the pre-Phase-3 time for the same entity count

---

## Phase 4 — Per-Entity Tracing in Ground Node

**Goal:** Add entity-level span data to the ground node's MLflow trace so
future bottleneck investigations don't require log-grepping. This directly
addresses the blind spot identified in Section 4 of the root cause report.

### 4.1 Add per-entity timing to ground node outputs

In `ground_node` (`nodes/ground.py`), after the `asyncio.gather` resolves,
collect per-entity timing from `_ground_entity_parallel`'s existing `elapsed`
measurement and include a summary in `span.set_outputs()`:

```python
span.set_outputs({
    "grounded_count": len(grounding_results),
    "error_count": len(accumulated_errors),
    "avg_entity_ms": round(sum(entity_times) / len(entity_times)) if entity_times else 0,
    "max_entity_ms": round(max(entity_times)) if entity_times else 0,
    "retry_count": retry_count,
})
```

Return the `elapsed` from `_ground_entity_parallel` alongside the result tuple
so the ground node can accumulate it.

### 4.2 Log retry count per entity

In `_ground_entity_with_retry`, pass back how many attempts were made in the
return value (add `attempt_count` to `EntityGroundingResult` or return it
alongside). Aggregate in `ground_node` and include in the span output.

### 4.3 Add `protocol_id` tag to extract and parse node traces

Currently only `ground_node` and `ordinal_resolve_node` tag traces with
`protocol_id`. Confirm `extract_node` and `parse_node` also call
`mlflow.update_current_trace(tags={"protocol_id": ...})` so all node traces
for a single run can be grouped in the MLflow UI.

### Phase 4 Completion Criteria

- [ ] `ground_node` span outputs include `avg_entity_ms`, `max_entity_ms`, `retry_count`
- [ ] All 7 pipeline nodes tag their trace with `protocol_id`
- [ ] A test protocol run produces MLflow traces that identify which entities
  were slow without needing to grep logs

---

## Phase 5 — MedGemma Keep-Warm (If Warranted by Phase 1.5)

**Goal:** Eliminate the 308s cold-start outlier on Vertex AI Model Garden by
sending a lightweight keep-warm call before the ground node processes entities.

**Proceed only if Phase 1.5 confirms that cold-start is the cause of the
max-308s outlier.** If the root cause is rate limiting, skip this phase.

### 5.1 Add warm-up call before `asyncio.gather` in ground node

Before dispatching the entity tasks, send a single trivial inference call to
ModelGardenChatModel to wake the endpoint:

```python
# Warm the Model Garden endpoint before parallel entity processing
try:
    warmup_model = _get_medgemma_model()
    await warmup_model.ainvoke([HumanMessage(content="ready")])
except Exception:
    pass  # non-fatal
```

### 5.2 Alternatively: dedicated keep-warm background task

If the inference lib supports it, configure a background asyncio task that
pings the endpoint every 5 minutes to keep it warm across pipeline runs.

### Phase 5 Completion Criteria

- [ ] Warmup call added (if cold-start confirmed)
- [ ] Max entity time drops below 60s in subsequent MLflow traces
- [ ] No measurable impact on entities that were already fast

---

## Rollout & Merge

1. Each phase is committed atomically with its own commit message.
2. After Phase 3 tests pass locally, open a PR from
   `feature/perf-test-limits-and-async-grounding` into
   `feature/major-refactor-langgraph`.
3. CI must pass full test suite. The `@pytest.mark.slow` tests are excluded
   from CI by default (add `-m 'not slow'` to CI addopts if needed).
4. Phase 4 (tracing) and Phase 5 (keep-warm) can be added as follow-up
   commits on the same branch before or after merge.

---

## Reference: Key Files

| File | Relevance |
|---|---|
| `services/protocol-processor-service/tests/conftest.py` | Phase 2: add env vars |
| `pyproject.toml` | Phase 2: add `slow` marker |
| `services/protocol-processor-service/src/protocol_processor/tools/medgemma_decider.py` | Phase 3: async fixes |
| `services/protocol-processor-service/src/protocol_processor/tools/field_mapper.py` | Phase 3: async fix |
| `services/protocol-processor-service/src/protocol_processor/nodes/ground.py` | Phase 4: entity timing |
| `services/protocol-processor-service/src/protocol_processor/tracing.py` | Phase 4: protocol_id tags |
| `services/protocol-processor-service/tests/test_phase1b_wiring.py` | Phase 3: mock updates |
