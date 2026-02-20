# Implementation Status

Current state of ElixirTrials components as of the `feature/major-refactor-langgraph` branch.

## Maturity Matrix

| Component | Status | Notes |
|-----------|--------|-------|
| PDF upload + quality scoring | Production-ready | Signed URL flow, client-side validation, quality analysis |
| Gemini criteria extraction | Production-ready | Structured output with Gemini 2.5 Flash |
| Entity decomposition (parse) | Production-ready | Concurrent async decomposition |
| UMLS grounding (TerminologyRouter) | Production-ready | Multi-vocab routing with caching |
| OMOP concept mapping | Production-ready | Dual grounding with reconciliation |
| Agentic retry loop | Experimental | MedGemma reasoning for low-confidence entities |
| Expression tree structuring | Production-ready | Gemini logic detection, atomic/composite model |
| Ordinal scale resolution | Experimental | Gemini-based detection, proposals for review |
| HITL review UI | Production-ready | Split-pane PDF + criteria, filtering, audit trail |
| Re-extraction with review inheritance | Production-ready | Fuzzy matching (>90% threshold) |
| CIRCE export | Production-ready | Full expression tree walking |
| FHIR R4 Group export | Production-ready | Full expression tree walking |
| OMOP evaluation SQL export | Production-ready (limited) | Flat AND/OR model only (see known limitations) |
| LangGraph checkpointing | Production-ready | AsyncPostgresSaver with retry support |
| Outbox event processing | Production-ready | At-least-once delivery, dead letter handling |
| Google OAuth | Production-ready | JWT session with protected routes |
| MLflow observability | Production-ready | Per-node traces, orphan cleanup |
| Circuit breaker (Gemini) | Production-ready | pybreaker-based with UI warning |

## Known Limitations

### Evaluation SQL Builder (flat model)

The OMOP CDM evaluation SQL builder uses a flat AND/OR model: all inclusion atomics are combined with AND, all exclusion atomics use NOT EXISTS. The expression tree's nested AND/OR/NOT structure is **not** respected by the SQL builder.

For example, "HbA1c >= 7% OR fasting glucose >= 126" is evaluated as requiring **both** rather than **either**.

The CIRCE and FHIR Group builders correctly walk the expression tree.

**File**: `services/api-service/src/api_service/exporters/evaluation_sql_builder.py:1-13`

### CompositeCriterion.parent_criterion_id

The `parent_criterion_id` column on `CompositeCriterion` is intentionally unused by the automated pipeline. Tree parent-child relationships are stored in `CriterionRelationship`. This field is reserved for future HITL use (manual tree restructuring).

### No UI Tests

The `apps/hitl-ui` directory has no test files. The React components are untested.

### Stale Workspace Members

Several workspace members in `pyproject.toml` exist as directories but have minimal functionality:

- `libs/data-pipeline` — data loading helpers (limited)
- `libs/evaluation` — quality evaluation framework (limited)
- `libs/inference` — model inference utilities (limited)
- `libs/model-training` — fine-tuning scripts (limited)

These are scaffolded for future use but not actively consumed by the pipeline.

## Test Coverage

| Area | Test files | Count | Runner |
|------|-----------|-------|--------|
| API endpoints | `services/api-service/tests/test_protocol_api.py` | ~15 tests | pytest |
| Review workflow | `services/api-service/tests/test_review_api.py` | ~10 tests | pytest |
| Auth | `services/api-service/tests/test_auth_required.py` | ~5 tests | pytest |
| Exports | `services/api-service/tests/test_exports.py` | 36 tests | pytest |
| Data integrity | `services/api-service/tests/test_integrity.py` | ~5 tests | pytest |
| Quality scoring | `services/api-service/tests/test_quality.py` | ~5 tests | pytest |
| Models/schemas | `services/api-service/tests/test_models.py`, `test_schemas.py` | ~10 tests | pytest |
| UMLS clients | `services/api-service/tests/test_umls_clients.py` | ~5 tests | pytest |
| Event contracts | `libs/events-py/tests/` | ~5 tests | pytest |
| Pipeline nodes | None | 0 | — |
| UI components | None | 0 | — |

**Run all tests**: `make test`

## Top 5 Risks for Maintainers

### 1. Cross-Service Import Coupling

Pipeline nodes (`protocol-processor-service`) directly import from `api-service` for database access (`from api_service.storage import engine`). This creates a tight runtime coupling — the processor cannot run without the api-service package on the Python path.

**Mitigation**: The `pyproject.toml` pythonpath config handles this for dev. For production, both packages must be installed together.

### 2. No Pipeline Node Tests

The 7 LangGraph nodes have zero test coverage. All testing is through the API layer. A change to a node could break the pipeline without any test failure.

**Mitigation**: Add integration tests that invoke individual nodes with mock LLM responses.

### 3. Outbox Polling Latency

The outbox processor polls every 2 seconds. Under load, this could create a backlog. There's no back-pressure mechanism.

**Mitigation**: Monitor outbox table depth; consider reducing poll interval or switching to PostgreSQL LISTEN/NOTIFY.

### 4. Gemini API Rate Limits

Multiple pipeline nodes call Gemini concurrently (semaphore=4 per node). A burst of protocol uploads could hit API rate limits.

**Mitigation**: The circuit breaker (`pybreaker`) handles transient failures. Consider adding global rate limiting.

### 5. Expression Tree vs Flat SQL Mismatch

The CIRCE and FHIR exporters walk the expression tree correctly, but the SQL exporter uses a flat model. Users may get inconsistent results across export formats.

**Mitigation**: Document the limitation clearly (done). Future: implement tree-aware SQL generation using recursive CTE grouping.
