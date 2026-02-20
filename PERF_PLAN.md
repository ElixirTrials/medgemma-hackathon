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

### 1.5 Investigate MedGemma `ModelGardenChatModel` cold-start / keep-warm options

From the MLflow data: 63 calls to `ModelGardenChatModel` produced a min of 1.3s,
median of ~14s, and a **max of 308s** — a 230× variance that makes the pipeline
unpredictable. The 308s outlier is almost certainly a cold-start or a queued slot
on a shared Model Garden endpoint.

**Steps:**

1. Read `libs/inference/src/inference/model_garden.py` (and `config.py`,
   `factory.py`) to understand how `create_model_loader` and `AgentConfig`
   configure the Vertex AI endpoint. Specifically:
   - Is it a shared public endpoint or a dedicated endpoint ID?
   - Is there a `min_replica_count` > 0 keeping the model warm?
   - Is `AgentConfig.from_env()` reading an endpoint resource name, or using
     the default Model Garden serving path?

2. Check the Vertex AI console (or `gcloud ai endpoints list`) to verify
   whether the endpoint has `min_replica_count=0` (causes cold-starts).

3. Determine available remedies:
   - **Provisioned throughput**: Vertex AI allows reserving dedicated serving
     capacity with guaranteed warm replicas. Document the quota/cost.
   - **Dedicated endpoint with `min_replica_count=1`**: Keeps at least one
     replica warm. Cost: ~$0.05–0.15/hr depending on accelerator.
   - **Pre-flight warm-up call**: Send a single trivial inference call before
     dispatching the entity batch. Adds ~2s overhead but eliminates the 308s
     outlier for runs within the same process lifetime.
   - **Skip MedGemma in tests**: Mock `medgemma_decide` entirely in unit and
     integration tests; only call it in `@pytest.mark.slow` E2E tests. This
     sidesteps the cold-start problem entirely for the test suite.

**Output of 1.5:**
- Confirmed endpoint type (shared vs dedicated) and `min_replica_count`
- Ranked list of remedies with cost/complexity trade-offs
- Recommendation for Phase 5: keep-warm call, dedicated endpoint, or test-only
  mock — whichever is most appropriate given the deployment constraints

### 1.6 Measure agentic retry trigger rate

From MLflow trace data: Run 1 had 63 MedGemma calls and 158 Gemini structuring
calls. With a baseline of 2 Gemini calls per entity (structure decision + field
mapping), 158 calls for 63 entities implies ~32 extra Gemini calls — roughly
**50% of entities** triggered at least one agentic retry cycle. This is far above
the 30% threshold at which the `confidence < 0.5` cutoff should be reconsidered.

**Steps:**

1. Query the MLflow spans DB to count, per LangGraph trace, how many
   `ModelGardenChatModel` calls exceed 1 per entity (retries):

   ```python
   # In the spans table, each ground_node run has N MedGemma calls.
   # Baseline is 1 MedGemma call per entity (first evaluate attempt).
   # Retry calls add 1 MedGemma (agentic_reasoning_loop) + 1 MedGemma
   # (re-evaluate), so each retry cycle adds 2 MedGemma calls.
   # retry_count = (total_medgemma_calls - entity_count) / 2
   ```

   Using the known entity counts from `span.set_inputs(entity_count=...)`:

   | Trace | MedGemma calls | Entities | Est. retry cycles | Retry rate |
   |---|---|---|---|---|
   | Run 1 (1214s) | 63 | ~42 | ~10 | ~24% |
   | Run 2 (956s) | 56 | ? | ? | ? |
   | … | … | … | … | … |

   The entity count is available in the `ground_node` span's content
   (`inputs.entity_count`). Read it from the spans table and compute retry rate
   for all 6 grounding runs.

2. Cross-reference the AuditLog table (via the API DB, not MLflow) to see what
   `confidence` scores entities received on their first attempt. This gives the
   ground truth on how many fell below 0.5.

3. Sample 10–20 AuditLog entries where `confidence < 0.5` and examine
   `reasoning` to determine if they are:
   - **Genuinely ambiguous** entities that need retry (retries are justified)
   - **Ungroundable** entities (consent, demographics) that slip past the
     pre-filter and waste API calls
   - **Threshold too aggressive**: entities where MedGemma said confidence=0.4
     but the selected code was actually correct (false negatives)

**Output of 1.6:**
- Retry rate per trace (table)
- Breakdown of why entities fell below threshold (ambiguous / ungroundable /
  threshold too tight)
- Recommendation: keep `confidence < 0.5`, raise to `0.3`, or add entity-type
  pre-filters before the retry loop kicks in

### Phase 1 Completion Criteria

- [ ] Table of all sync `.invoke()` call sites in async paths
- [ ] Baseline test durations recorded (per-test wall-clock from pytest output)
- [ ] Env-var injection confirmed safe for conftest.py
- [ ] `ainvoke` compatibility confirmed for `ChatGoogleGenerativeAI.with_structured_output`
- [ ] MedGemma endpoint type confirmed (shared vs dedicated), cold-start root
  cause understood, and remediation options ranked
- [ ] Agentic retry rate computed for all 6 grounding traces
- [ ] Retry root-cause sampled from AuditLog (ambiguous vs ungroundable vs
  threshold too tight)
- [ ] Written summary: findings and recommended threshold / pre-filter changes
  (feeds Phase 5 scope decision)

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
