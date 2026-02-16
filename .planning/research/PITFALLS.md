# Pitfalls Research

**Domain:** Clinical Trial Criteria Extraction -- Pipeline Consolidation, ToolUniverse Grounding, and E2E Quality Fixes
**Researched:** 2026-02-16
**Confidence:** HIGH (based on codebase analysis, E2E test report, official documentation, and multiple verified sources)

---

## Critical Pitfalls

### Pitfall 1: Outbox Removal Creates Silent Data Loss Window During Pipeline Consolidation

**What goes wrong:**
Removing the transactional outbox pattern between extraction and grounding (to eliminate 5-15s latency) without replacing its atomicity guarantee creates a window where criteria are persisted but grounding never runs. If the grounding step fails after extraction commits, the protocol lands in "extracted" status permanently -- no outbox event to retry, no mechanism to trigger grounding again.

**Why it happens:**
The outbox pattern exists to solve the dual-write problem: extraction writes criteria to the database AND publishes a `CriteriaExtracted` event atomically. Developers see the outbox as "unnecessary complexity for a sequential pipeline" and replace it with a direct function call (`ground_entities()` called after `persist_criteria()`). But if grounding fails after the extraction commit, there is no retry queue. The current outbox processor retries failed events up to 3 times and moves them to dead_letter, giving operators visibility. A direct call just throws an exception that gets caught in the outer handler, and the protocol status may or may not get updated correctly.

**How to avoid:**
- If consolidating to a single graph, wrap the entire pipeline (extract + ground + persist) in a single database transaction that only commits when ALL steps succeed. If grounding fails, the criteria rows roll back too.
- Alternatively, keep a lightweight event mechanism: after extraction persists and commits, insert a "grounding_needed" row that a background task picks up. This preserves retry semantics without the full outbox machinery.
- Add a "stuck protocol" detector: query for protocols in "extracted" status for >5 minutes with no corresponding grounding batch, and alert or auto-retry.
- Never commit extraction results in one transaction and call grounding in a separate transaction without a recovery mechanism between them.

**Warning signs:**
- Protocols stuck in "extracted" status indefinitely (never transition to "grounding" or "pending_review")
- Grounding errors logged but no retry occurs
- Manual intervention needed to "re-run grounding" on protocols that extracted successfully
- No dead_letter entries for failed grounding (because the retry mechanism was removed)

**Phase to address:**
Pipeline consolidation phase (first phase of v2.0). Must be resolved BEFORE removing outbox.

---

### Pitfall 2: ToolUniverse MCP Subprocess Lifecycle Management Causes Grounding Timeouts

**What goes wrong:**
ToolUniverse runs as an MCP server via `uvx tooluniverse` subprocess (similar to the current UMLS MCP pattern). Each grounding call spawns a new subprocess, which must bootstrap the entire ToolUniverse runtime (load tool configs, authenticate APIs). This adds 5-15s startup overhead per batch. Worse, if the subprocess crashes or hangs mid-batch, the parent process (LangGraph node) waits until timeout, then falls back to `expert_review` for ALL entities in the batch -- the exact failure mode currently producing 0% confidence.

**Why it happens:**
The current `medgemma_ground.py` already shows this pattern: `MultiServerMCPClient` creates a new `StdioConnection(command="uv", args=["run", "python", "-m", "umls_mcp_server.server"])` per invocation. Each invocation starts a fresh subprocess. ToolUniverse has even more initialization overhead because it loads 211+ tool configs. Developers assume MCP subprocess management is handled by the framework, but `langchain-mcp-adapters` does not pool or reuse subprocess connections.

**How to avoid:**
- Use ToolUniverse's Python SDK directly (`from tooluniverse import RxNormTool, ICD10Tool`) instead of spawning an MCP subprocess. The MCP layer adds subprocess overhead without benefit when running in the same process.
- If MCP is required (e.g., for isolation), keep the ToolUniverse MCP server as a long-running sidecar process (like a database), not a per-request subprocess. Configure it in `docker-compose.yml` as a separate service.
- Implement connection pooling: start the MCP subprocess once in the application lifespan, reuse the connection for all grounding calls.
- Add explicit timeout handling: if ToolUniverse doesn't respond within 30s, kill the subprocess and retry with a fresh one (max 2 retries before fallback).
- Never fall back to `expert_review` for the entire batch when only one tool call fails. Ground entities individually so partial success is possible.

**Warning signs:**
- All entities in a batch have 0% confidence and `expert_review` method (current state, inherited from subprocess failures)
- Grounding latency >30s per batch (subprocess startup dominating)
- Log messages: "Agentic grounding failed for batch" or "UMLS search failed for" appearing for ALL entities, not just individual failures
- ToolUniverse MCP subprocess appearing in `ps aux` as zombie/orphan processes

**Phase to address:**
ToolUniverse integration phase. Must be resolved as part of the grounding replacement, not as a follow-up.

---

### Pitfall 3: Entity Type Classification Mismatch Between Extraction and ToolUniverse Routing

**What goes wrong:**
ToolUniverse's scoped routing maps entity types to specific tools (MEDICATION->RxNorm, DISEASE->ICD-10, LAB_TEST->LOINC, PHENOTYPE->HPO). But the extraction pipeline currently classifies entities with a different taxonomy: `Condition`, `Medication`, `Procedure`, `Lab_Value`, `Demographic`, `Biomarker`. If the mapping between extraction entity types and ToolUniverse entity types is wrong or incomplete, entities get routed to the wrong tool or no tool at all. "Biomarker" has no ToolUniverse mapping. "Demographic" (age, sex) doesn't need grounding but might get routed to ICD-10 incorrectly.

**Why it happens:**
The extraction entity taxonomy was designed for the UMLS MCP approach (which uses a single concept_search for all entity types). ToolUniverse requires entity-type-aware routing to select the correct tool. Developers port the ToolUniverse integration without updating the extraction schema to match, creating a translation layer that silently drops unmapped types.

**How to avoid:**
- Define a canonical entity type mapping upfront and document it:
  - `Condition` -> `DISEASE` (ICD10Tool)
  - `Medication` -> `MEDICATION` (RxNormTool)
  - `Lab_Value` -> `LAB_TEST` (LOINCTool)
  - `Biomarker` -> `PHENOTYPE` (HPOTool) or `LAB_TEST` (LOINCTool) depending on context
  - `Procedure` -> not groundable via ToolUniverse (use SNOMED procedure codes via UMLS fallback or skip)
  - `Demographic` -> skip grounding (age, sex don't need terminology codes)
- Add explicit "unroutable" handling: log and tag entities that don't map to any ToolUniverse tool, with `grounding_method: "no_tool_available"` (not `expert_review`, which implies the entity needs human review)
- Update the extraction schema's `entity_type` enum to align with ToolUniverse categories or add a `tool_route` field
- Write unit tests: for each entity type in the extraction schema, assert that a ToolUniverse tool mapping exists or the entity is explicitly skipped

**Warning signs:**
- Entity types appearing in the database that have no grounding codes (not because grounding failed, but because no tool was called)
- High % of entities routed to fallback when they should have been groundable
- "Procedure" entities always showing `expert_review` even though they are valid medical concepts
- Logs showing "No mapping for entity type: Biomarker" or similar

**Phase to address:**
ToolUniverse integration phase. Entity type mapping must be defined BEFORE implementing tool routing.

---

### Pitfall 4: Dashboard Pending Count Semantic Confusion Causes Missed Reviews

**What goes wrong:**
The dashboard shows "0 Pending Reviews" when batches exist with unreviewed criteria. Users stop checking the review queue because the dashboard says there's nothing to review. In reality, 40+ criteria may be waiting. The current code queries for batches with `status === 'pending_review'`, but this status transitions to `in_progress` after the FIRST criterion is reviewed. A batch with 1/41 criteria reviewed shows as "in progress," not "pending."

**Why it happens:**
The batch status state machine has three states relevant to pending work:
- `pending_review`: no criteria reviewed yet
- `in_progress`: at least one criterion reviewed, but not all
- `approved`/`rejected`: all criteria reviewed

The dashboard only counts `pending_review`, so batches with partial reviews are invisible. The `_update_batch_status()` function in `reviews.py` transitions to `in_progress` on the first review, which is correct for batch tracking but wrong for "how many batches need attention."

**How to avoid:**
- Change dashboard semantics to count batches with ANY unreviewed criteria: query batches where at least one criterion has `review_status IS NULL`
- Add a dedicated API endpoint: `GET /reviews/pending-count` that returns `{ batches_needing_review: N, total_unreviewed_criteria: M }` using a subquery on criteria
- Keep the batch status state machine for detailed tracking, but use a separate derived metric for the dashboard
- Do NOT change batch status semantics (they are correct for their purpose) -- add a new query for the dashboard's purpose

**Warning signs:**
- Dashboard shows "0 Pending Reviews" when the Review Queue page shows batches with partial progress
- Users report: "I thought there was nothing to review" when criteria are waiting
- Batch status is `in_progress` but dashboard counts it as "done"

**Phase to address:**
E2E quality fixes phase. This is a query-only change, no schema migration needed.

---

### Pitfall 5: Audit Trail Entries Created But Not Visible Due to Query Scope Mismatch

**What goes wrong:**
The audit trail shows "No audit entries" after performing review actions. The entries exist in the database (confirmed by `Review` and `AuditLog` records being created in `submit_review_action()`), but the UI query returns empty results. The Review page calls `useAuditLog(1, 20, 'criteria')` which hits `GET /reviews/audit-log?page=1&page_size=20&target_type=criteria`. This query is correct syntactically but may return empty results if the entries are not committed before the query runs, or if there is a filtering mismatch.

**Why it happens:**
Two possible root causes identified from code analysis:

1. **No batch scope**: The audit trail shows ALL entries for `target_type=criteria`, not scoped to the current batch. If the total count is 0 or the entries for this specific batch are buried in pagination, they appear missing. The API has no `batch_id` filter.

2. **Race condition**: The `submit_review_action()` function calls `db.commit()` AFTER `_update_batch_status()` but the audit log query is triggered by the TanStack Query cache invalidation from `onSuccess`. If the invalidation fires before the commit completes, the subsequent GET returns stale data.

**How to avoid:**
- Add `batch_id` query parameter to the audit log API. When provided, filter to audit entries whose `target_id` is in the set of criteria IDs for that batch. The Review page should pass the current `batchId`.
- Ensure the `onSuccess` callback in `useReviewAction()` triggers cache invalidation after the mutation response is received (which means the server has committed). TanStack Query's `onSuccess` fires after the mutation promise resolves, so the commit should be done. Add a test to verify this.
- Add an integration test: submit an approve action, then immediately query the audit log for that `target_id`, and assert the entry exists.

**Warning signs:**
- "No audit entries yet" displayed on the Review page after performing actions
- Audit log API returns entries when queried without filters but returns empty when filtered by `target_type`
- The `total` count in `AuditLogListResponse` is 0 despite actions being taken

**Phase to address:**
E2E quality fixes phase (Tier 1 critical fix per OPERATIONAL_REVISION_PLAN.md).

---

### Pitfall 6: Gemini Extraction Non-Determinism Undermines Corpus Comparison

**What goes wrong:**
The same protocol PDF produces 35 criteria in one run and 41 in the next. This makes it impossible to compare before/after extraction quality, because the "before" and "after" sets have different cardinalities and different criteria boundaries. Re-extraction tooling (running the pipeline again on the same protocol) cannot produce meaningful diffs when the criteria count itself is unstable.

**Why it happens:**
Gemini's structured output is non-deterministic even at temperature=0. This is a [known issue](https://github.com/google-gemini/deprecated-generative-ai-python/issues/745) -- Gemini 2.5/3 models do not guarantee deterministic output even with fixed seed and temperature=0. The extraction prompt has ambiguous granularity instructions: the model decides whether to split "Participants must not be taking Warfarin, Sulphasalazine, or CYP 3A4 inducers" into 1 criterion or 3. Different runs make different splitting decisions.

**How to avoid:**
- Add explicit granularity instructions to the extraction prompt: "Each criterion should be one complete eligibility requirement as written in the protocol. Do not split compound criteria that appear as a single numbered item in the source document."
- Set temperature=0 AND add a seed parameter for reproducibility (acknowledging it is best-effort, not guaranteed)
- For corpus comparison, use text similarity matching (not strict equality) to pair criteria across runs: compute Levenshtein distance between criteria texts and match pairs above 80% similarity
- Add a "criteria hash" based on normalized text content to detect when criteria are semantically identical but have different IDs
- Accept that exact determinism is impossible with current Gemini models and design the corpus comparison workflow to be tolerant of minor variations

**Warning signs:**
- Criteria count varies between runs (>10% difference = prompt ambiguity problem)
- Corpus comparison script reports "12 unmatched criteria" between runs
- Re-extraction creates duplicate criteria that are slight rewordings of existing ones
- Reviewers report: "This criterion was different last time I reviewed it"

**Phase to address:**
Extraction determinism phase. Prompt tightening should happen BEFORE re-extraction tooling, because re-extraction tooling relies on stable output.

---

### Pitfall 7: Re-extraction Without Review Protection Destroys Gold-Standard Data

**What goes wrong:**
Running re-extraction on an existing protocol creates a new `CriteriaBatch` (the current `queue_node` always creates a new batch), but doesn't check whether the existing batch has human reviews. If the system later deduplicates batches or the UI only shows the latest batch, reviewed criteria from the previous batch become invisible. The human corrections are preserved in the database but are operationally lost.

**Why it happens:**
The `queue_node` in `extraction_service/nodes/queue.py` unconditionally creates a new `CriteriaBatch` linked to the same `protocol_id`. It does not check for existing batches. The UI shows batches for a protocol, but if users assume "the latest batch is the authoritative one" and stop looking at old batches, corrections are abandoned. There is no `is_locked` flag, no warning about existing reviews, and no "merge with existing batch" logic.

**How to avoid:**
- Before creating a new batch, query for existing batches with the same `protocol_id`. If any criteria in those batches have `review_status IS NOT NULL`, log a warning and set a `supersedes_batch_id` field on the new batch
- Add an `is_locked` flag to `CriteriaBatch`: batches with ANY reviewed criteria are locked. Re-extraction creates a new unlocked batch and links it to the locked one
- Implement a "diff view" in the UI: show side-by-side comparison of old (reviewed) criteria vs. new (re-extracted) criteria, with matched pairs highlighted
- Add a database constraint or application-level check: `DELETE` or `UPDATE` on criteria with `review_status IS NOT NULL` requires explicit override
- Export reviewed criteria to a separate `gold_corpus` table before allowing re-extraction, so the gold data is never at risk

**Warning signs:**
- Multiple batches for the same protocol with no indication which has reviews
- Corpus size decreases after re-extraction (old reviewed batch becomes invisible)
- Reviewers report: "I already corrected this but it's back to the AI version"
- Protocol detail shows different batch being reviewed than what was previously corrected

**Phase to address:**
Re-extraction tooling phase. Must be implemented BEFORE allowing re-extraction on protocols with existing reviews.

---

### Pitfall 8: JSONB Schema Evolution Breaks Old Criteria on UI Load

**What goes wrong:**
The `conditions` JSONB column now stores `{ "field_mappings": [...] }` (v1.5-multi schema) after structured editing, but criteria extracted before v1.5 store `conditions` as either `null`, a JSON array of strings `["if diabetic"]`, or a simple dict `{"conditions_list": [...]}`. The `_criterion_to_response()` helper in `reviews.py` handles some of these cases but the UI components (`CriterionCard`, `StructuredFieldEditor`) may not handle all permutations. Adding new fields to the JSONB schema (e.g., `entity_codes` from ToolUniverse grounding) creates another version that old code doesn't expect.

**Why it happens:**
JSONB's schemaless nature encourages incremental additions without migration. The `conditions` column has evolved through at least 3 shapes:
1. `null` or `["string condition"]` (v1.0 extraction)
2. `{"conditions_list": ["string condition"]}` (API wrapper for list input)
3. `{"field_mappings": [{entity, relation, value}]}` (v1.5 structured editor)

Each new shape is added without migrating old data. Code checks `isinstance(conditions, dict)` vs `isinstance(conditions, list)` but doesn't handle nested field presence checks robustly. The ToolUniverse integration will add a 4th shape: `{"field_mappings": [...], "entity_codes": {"rxnorm": "...", "icd10": "..."}}`.

**How to avoid:**
- Add a `schema_version` field to every JSONB document: `{ "schema_version": "v2.0-tooluni", "field_mappings": [...], "entity_codes": {...} }`
- Write a one-time migration script that normalizes all existing `conditions` data to the latest schema version
- Add a read-time adapter function that converts any schema version to the latest: `def normalize_conditions(raw: Any) -> ConditionsV2 | None`
- Use TypeScript type guards on the frontend: `function hasFieldMappings(c: unknown): c is { field_mappings: FieldMapping[] }`
- Never access nested fields without optional chaining: `conditions?.field_mappings ?? []`
- Document all JSONB schema versions with examples in a JSONB_SCHEMA_VERSIONS.md file

**Warning signs:**
- TypeError on criteria load: "Cannot read property 'field_mappings' of undefined"
- Some criteria render correctly, others show blank or crash (mixed schema versions in same batch)
- Edit-then-save drops fields that were present before edit (partial schema overwrite)
- ToolUniverse grounding codes are written but not displayed (UI doesn't know about new fields)

**Phase to address:**
JSONB schema evolution should be addressed in the FIRST phase that modifies the `conditions` column (either ToolUniverse integration or editor pre-loading phase). Migration script must run before new writes begin.

---

### Pitfall 9: ToolUniverse Rate Limits and API Key Management Across Multiple Tools

**What goes wrong:**
ToolUniverse wraps multiple external APIs (NLM RxNorm, WHO ICD-10, LOINC from Regenstrief, HPO from Monarch Initiative). Each has different rate limits, authentication requirements, and SLAs. A single batch of 41 criteria with 3 entities each = 123 tool calls across 5+ APIs. Without per-API rate limiting, the system hits rate limits on one API (e.g., NLM allows 20 req/s for RxNorm) and causes cascading timeouts for the entire batch.

**Why it happens:**
Developers treat ToolUniverse as a single black-box API and apply a single retry/circuit-breaker policy. But ToolUniverse is a wrapper -- each tool call hits a different external API with different quotas. NLM's UMLS/RxNorm API requires an API key and has rate limits. LOINC's API requires registration. HPO's API is open but slow. When one API is rate-limited, the grounding node retries aggressively, consuming the retry budget on a temporary condition, then falls back to `expert_review` for all remaining entities.

**How to avoid:**
- Implement per-tool rate limiting: configure separate rate limiters for each ToolUniverse tool (`RxNormTool`: 20 req/s, `ICD10Tool`: 10 req/s, etc.)
- Use adaptive backoff: when a tool returns 429 (rate limited), pause only that tool and continue grounding other entity types with other tools
- Verify API key requirements for each ToolUniverse tool BEFORE starting the integration. Some tools may require separate API keys beyond the ToolUniverse installation
- Batch tool calls by entity type: ground all MEDICATION entities first (one RxNorm batch), then all DISEASE entities (one ICD-10 batch), to minimize API connection overhead
- Add a tool health check at startup: verify each tool is accessible before accepting grounding requests. Fail fast rather than failing per-entity

**Warning signs:**
- Grounding succeeds for some entity types but fails for others (API-specific failure)
- 429 status codes in logs for specific tool calls
- Grounding latency highly variable (2s when APIs are available, 60s+ when rate-limited)
- Environment variables for tool-specific API keys are missing or expired

**Phase to address:**
ToolUniverse integration phase. Rate limiting and API key validation must be implemented alongside tool routing, not as a follow-up.

---

### Pitfall 10: Pipeline Consolidation State Schema Merge Causes Type Safety Regression

**What goes wrong:**
Merging `ExtractionState` (TypedDict with `protocol_id`, `file_uri`, `pdf_bytes`, `raw_criteria`, etc.) and `GroundingState` (TypedDict with `batch_id`, `criteria_ids`, `criteria_texts`, `grounded_entities`, etc.) into a single `ProcessorState` creates a large TypedDict where most fields are `None` at any given node. Nodes that only need extraction data can accidentally read grounding fields (and vice versa). Mypy catches some issues, but `state.get("field", default)` bypasses type checking entirely.

**Why it happens:**
LangGraph StateGraphs require a single state schema. When merging two services, developers create a union type that includes all fields from both graphs. Early nodes receive a state where grounding fields are None/empty. Late nodes have extraction fields that are stale or unused. The TypedDict contract becomes "every field is Optional" which provides no type safety. Additionally, `state.get()` on a TypedDict returns `Any` in many mypy configurations, hiding type errors.

**How to avoid:**
- Use LangGraph's reducer pattern to mark fields as "write-once": once `pdf_bytes` is set by the ingest node, no subsequent node should modify it
- Keep the state schema narrow: only include fields that are read by at least 2 nodes. Use node-local variables for intermediate data
- Proposed consolidated state should have explicit phases: `ProcessorPhase = Literal["ingesting", "extracting", "grounding", "persisting"]` and nodes assert the current phase before proceeding
- Run `mypy --strict` on the consolidated graph module and fix all `Any` type warnings
- Add runtime assertions in each node: `assert state["pdf_bytes"] is not None, "ingest must run before extract"`

**Warning signs:**
- Mypy reports many `Any` type warnings in the consolidated graph
- Nodes access fields that haven't been populated yet (returns `None` where a value was expected)
- Test coverage gaps: nodes pass when tested individually but fail when composed in the full graph
- State dict grows to 15+ fields, most of which are None at any given node

**Phase to address:**
Pipeline consolidation phase. State schema design must be done BEFORE implementing individual nodes.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Removing outbox without replacing retry mechanism | Eliminates 5-15s latency, simpler code | Protocols stuck in "extracted" forever when grounding fails, no retry | Never; must have retry/recovery mechanism |
| Using ToolUniverse MCP subprocess per grounding call | Simple integration, follows existing pattern | 5-15s startup per call, zombie processes, same 0% confidence failure mode | Never; use Python SDK or long-running sidecar |
| Hardcoding entity type to tool mapping | Fast to implement, works for known types | New entity types silently dropped, no validation | OK for MVP if all mappings documented and tested |
| Adding fields to JSONB without schema_version | Avoids migration, fast iteration | Old records crash on load, silent field drops on edit-save | Never after v1.5; migration is mandatory |
| Querying pending batches by status only | Simple query, reuses existing endpoint | Dashboard misleads users about review work remaining | Never; dashboard is primary entry point |
| Single fallback for entire batch on grounding failure | Simpler error handling, guaranteed completion | ALL entities get 0% confidence even when some could be grounded | Never; individual entity fallback is critical |
| Coupling extraction entity types to grounding tool routing | Fewer abstractions, direct mapping | Schema changes in extraction break grounding routing | OK for initial implementation if mapping is explicit and tested |
| Direct commit + separate grounding call (no atomicity) | Eliminates outbox code | Data inconsistency: criteria exist but grounding never ran | Never; use single transaction or event-driven retry |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| ToolUniverse MCP | Spawning new subprocess per grounding batch (same as current UMLS MCP pattern) | Use Python SDK directly (`from tooluniverse import RxNormTool`) or run MCP as long-lived sidecar in docker-compose |
| ToolUniverse RxNormTool | Sending drug class names ("NSAID", "anticoagulant") instead of specific drug names | Extract specific drug names from criteria text first, then call RxNorm. Drug classes don't resolve to RxNorm CUIs. |
| ToolUniverse ICD10Tool | Sending criterion text directly instead of extracted disease names | Extract disease entity text first (e.g., "Type 2 Diabetes Mellitus"), then call ICD10. Full criterion text returns noise. |
| ToolUniverse LOINCTool | Sending "HbA1c < 7%" instead of "Hemoglobin A1c" | Strip comparators and values; send only the test name. LOINC codes identify tests, not thresholds. |
| LangGraph state merge | Creating union TypedDict with all fields Optional | Use minimal shared state. Keep intermediate data as node-local variables, not state fields. |
| Outbox removal | Deleting outbox code without adding alternative recovery | Keep retry mechanism: either single-transaction or background recovery job |
| Audit log API | Querying without batch scope (returns all entries for target_type) | Add batch_id filter that resolves to criteria IDs and scopes audit entries |
| Batch status as pending metric | Using `status='pending_review'` to count work remaining | Use criteria-level query: count batches with ANY criteria where `review_status IS NULL` |
| JSONB field_mappings | Writing new schema shape without migrating old data | Add schema_version, run migration script, add read-time adapter |
| Gemini temperature for determinism | Setting temperature=0 and expecting identical output | Also set seed parameter; add prompt granularity instructions; design for approximate matching not exact equality |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| ToolUniverse subprocess spawn per batch | 5-15s grounding latency before any tool calls execute | Use Python SDK or long-running MCP sidecar | Immediately; every batch pays startup cost |
| Sequential tool calls for 100+ entities | 2-3s per entity x 100 entities = 200-300s grounding time | Batch entities by type, use asyncio.gather for parallel tool calls across types | >30 entities per batch (typical: 40-60) |
| N+1 queries in audit log batch scope | Audit log query joins criteria IDs per batch, then queries audit entries per criteria | Pre-compute criteria IDs for batch in single query, use IN clause | >50 criteria per batch with audit trail open |
| ToolUniverse API rate limiting cascade | One rate-limited API blocks all grounding (single retry budget) | Per-tool rate limiters, adaptive backoff, partial-success grounding | >20 entities per batch hitting same API |
| Large JSONB conditions column scan | Criteria list query slow when conditions JSONB has nested field_mappings with entity_codes | Add GIN index on conditions column if querying by entity codes; keep conditions small | >500 criteria in database with ToolUniverse codes |
| Dashboard pending count query on large batch table | Dashboard load time >2s when many batches exist | Cache pending count in application memory with 30s TTL, or add materialized view | >100 batches in database |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| ToolUniverse API keys in environment variables without rotation | Compromised API key allows unlimited medical data queries | Use Secret Manager (GCP), rotate keys quarterly, audit key usage |
| ToolUniverse tools accessing external APIs without HIPAA review | Patient-identifiable criteria text sent to third-party APIs | Verify each ToolUniverse tool's data processing terms. Strip PHI from entity text before sending to tools. Most eligibility criteria don't contain PHI (they describe population requirements, not individual patients), but confirm. |
| Re-extraction endpoint without authorization check | Any authenticated user can re-run extraction, potentially overwriting reviewed data | Add role-based check: only admin users can trigger re-extraction on protocols with existing reviews |
| Audit log entries without tamper protection | Audit entries can be modified or deleted via direct DB access | Add database trigger that prevents UPDATE/DELETE on audit_log table; or use append-only table with write permissions only |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Dashboard says "0 Pending" when work exists | Reviewers stop checking, criteria pile up unreviewed | Show count of batches with ANY unreviewed criteria, not just status='pending_review' |
| Audit trail empty despite actions taken | Reviewers lose trust in the system's record-keeping | Fix query scope, add batch_id filter, add test to verify |
| Re-extraction creates new batch without warning about existing reviews | Reviewer's 2 hours of corrections become invisible (old batch) | Show modal: "This protocol has X reviewed criteria. Re-extraction creates a new batch." with "View existing reviews" link |
| ToolUniverse codes displayed as raw codes without context | Reviewer sees "E11.9" without knowing what it means | Always display code WITH preferred term: "E11.9 (Type 2 diabetes mellitus, without complications)" |
| Extraction non-determinism between review sessions | Reviewer sees different criteria on re-extraction, thinks their previous work was lost | Pin extraction results: show the SPECIFIC batch being reviewed, not "latest extraction" |
| Entity grounding shows partial results without explanation | Some entities have ICD-10 codes, others have nothing. Reviewer doesn't know why. | Show grounding status per entity: "Grounded (ICD-10)", "Grounding failed (API timeout)", "Skipped (demographic entity)" |

---

## "Looks Done But Isn't" Checklist

- [ ] **Pipeline consolidation:** Often missing retry/recovery mechanism -- verify that grounding failure does NOT leave criteria orphaned in "extracted" status
- [ ] **ToolUniverse integration:** Often missing per-tool rate limiting -- verify that hitting rate limits on one API doesn't cascade to all entity types
- [ ] **ToolUniverse integration:** Often missing entity type mapping -- verify that ALL extraction entity types (Condition, Medication, Procedure, Lab_Value, Demographic, Biomarker) have explicit ToolUniverse routing or explicit skip logic
- [ ] **Dashboard pending count:** Often missing criteria-level query -- verify dashboard shows non-zero count when batch has partial reviews
- [ ] **Audit trail visibility:** Often missing batch scope -- verify audit entries appear on the Review page for the specific batch being reviewed
- [ ] **Extraction determinism:** Often missing prompt granularity rules -- verify same protocol produces same criteria count (within 10%) across 3 consecutive runs
- [ ] **Re-extraction protection:** Often missing review lock -- verify re-extraction on a protocol with reviewed criteria does NOT make old reviews inaccessible
- [ ] **JSONB schema evolution:** Often missing migration script -- verify criteria created before v2.0 load without errors after schema changes
- [ ] **Editor pre-loading:** Often missing JSONB shape handling -- verify editor loads correctly for criteria with conditions=null, conditions=["string"], and conditions={field_mappings: [...]}
- [ ] **ToolUniverse codes in Entity table:** Often missing Entity model extension -- verify Entity model has new columns for multi-system codes (rxnorm_code, icd10_code, loinc_code, hpo_id) or stores them in a JSONB codes column

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Protocols stuck in "extracted" (no grounding) | LOW | 1. Query protocols with status='extracted' and no associated CriteriaBatch with grounded entities. 2. Create re-grounding script that feeds existing criteria_ids to grounding graph. 3. Add "stuck protocol" detector to prevent recurrence. |
| 0% confidence for all entities (subprocess failure) | MEDIUM | 1. Identify affected batches (all entities have grounding_method='expert_review'). 2. Re-run grounding with Python SDK instead of MCP subprocess. 3. Update Entity records with new grounding results. 4. No data loss (entities exist, just ungrounded). |
| Entity type mismatch drops entities from grounding | LOW | 1. Query entities with no grounding codes. 2. Check entity_type distribution. 3. Add missing mappings to tool registry. 4. Re-run grounding for affected entity types. |
| Dashboard misleading users about pending work | LOW | 1. Update dashboard query (code change only). 2. No data migration needed. 3. Communicate to users that counts are now accurate. |
| Audit trail entries invisible | LOW | 1. Verify entries exist in DB (`SELECT * FROM auditlog WHERE event_type='review_action'`). 2. Fix API query filter (add batch_id). 3. No data loss (entries exist). |
| JSONB schema mismatch crashes old criteria | MEDIUM | 1. Write migration script to normalize all conditions to latest schema. 2. Deploy read-time adapter first (handles any schema version). 3. Run migration script. 4. Verify with load test against pre-migration backup. |
| Re-extraction overwrote review visibility | HIGH | 1. Query all batches for protocol. 2. Identify batches with reviewed criteria. 3. If old batch still exists, surface it in UI. 4. If criteria were deleted (not just new batch), restore from backup. 5. Implement lock mechanism to prevent recurrence. |
| ToolUniverse API rate limiting cascade | LOW | 1. Add per-tool rate limiters. 2. Re-run grounding for affected batches. 3. Monitor rate limit response codes per tool. |
| Pipeline consolidation state type regression | MEDIUM | 1. Run mypy --strict on consolidated graph. 2. Fix all Any type warnings. 3. Add runtime assertions in each node. 4. Add integration test running full graph end-to-end with real state. |
| Extraction non-determinism | LOW | 1. Tighten prompt granularity instructions. 2. Set temperature=0 + seed. 3. Re-run extraction on test protocols to verify consistency. 4. No data loss (old extractions preserved in their batches). |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Outbox removal creates data loss window | Pipeline Consolidation | E2E test: kill grounding mid-run, verify protocol doesn't stay in "extracted" forever. Recovery must trigger within 5 minutes. |
| ToolUniverse subprocess lifecycle | ToolUniverse Integration | Load test: ground 50 entities in one batch, verify no subprocess zombies, latency <30s total (not per entity). |
| Entity type mismatch with tool routing | ToolUniverse Integration | Unit test: for each entity type in extraction schema, assert tool mapping exists or entity is explicitly skipped. |
| Dashboard pending count misleading | E2E Quality Fixes | Manual test: approve 1 of 40 criteria, verify dashboard still shows batch as needing review. |
| Audit trail entries invisible | E2E Quality Fixes | Integration test: submit approve action, immediately query audit log for that batch_id, assert entry exists. |
| Extraction non-determinism | Extraction Determinism | Run same protocol through extraction 3 times, assert criteria count differs by <10% and all runs > 30 criteria. |
| Re-extraction overwrites reviews | Re-extraction Tooling | E2E test: review 3 criteria, re-run extraction, verify old batch with reviews is accessible and new batch is separate. |
| JSONB schema evolution | JSONB Schema Evolution | Migration test: load pre-v2.0 criteria with conditions=null, conditions=["list"], and conditions={field_mappings: [...]}, verify all render without errors. |
| ToolUniverse rate limiting | ToolUniverse Integration | Load test: ground 100 entities rapidly, verify no cascading failures and partial success is recorded. |
| Pipeline state schema merge | Pipeline Consolidation | mypy --strict passes on consolidated graph module. Integration test: run full graph end-to-end asserting state values at each node boundary. |

---

## Sources

### Codebase Analysis
- `services/api-service/src/api_service/main.py` -- OutboxProcessor initialization with handler registration (lines 77-86)
- `services/api-service/src/api_service/reviews.py` -- `_update_batch_status()` state machine (lines 510-546), `submit_review_action()` audit log creation (lines 313-343)
- `services/extraction-service/src/extraction_service/nodes/queue.py` -- CriteriaBatch creation without existing batch check (lines 51-101)
- `services/grounding-service/src/grounding_service/nodes/medgemma_ground.py` -- MCP subprocess lifecycle and fallback to expert_review (lines 186-245, 317-338)
- `libs/events-py/src/events_py/outbox.py` -- OutboxProcessor retry and dead_letter logic (lines 60-145)
- `apps/hitl-ui/src/screens/Dashboard.tsx` -- pending count query using `useBatchList(1, 1, 'pending_review')` (line 12)
- `apps/hitl-ui/src/screens/ReviewPage.tsx` -- audit log query without batch scope: `useAuditLog(1, 20, 'criteria')` (line 63)

### E2E Testing
- `instructions/Refactoring/E2E-REPORT.md` -- All 13 issues documented from 2026-02-13 testing including 0% grounding confidence, audit trail empty, dashboard 0 pending, extraction non-determinism

### Architecture Planning
- `instructions/Refactoring/OPERATIONAL_REVISION_PLAN.md` -- Tier 1/2/3/4 prioritization of fixes (2026-02-16)
- `instructions/Refactoring/refactoring_review.md` -- Pipeline consolidation proposal
- `instructions/Refactoring/better_tool_use.md` -- ToolUniverse integration plan with tool registry and scope limiting

### ToolUniverse
- [ToolUniverse - 211+ Tools for "AI Scientist" Agents - Zitnik Lab](https://zitniklab.hms.harvard.edu/2025/06/03/ToolUniverse/)
- [GitHub - mims-harvard/ToolUniverse](https://github.com/mims-harvard/ToolUniverse) -- MCP configuration, tool categories
- ToolUniverse tools config index -- Confirmed availability of RxNormTool, ICD10Tool, LOINCTool, HPOTool, EFOTool

### Gemini Non-Determinism
- [Critical Determinism Failure in Gemini API with Fixed seed and temperature](https://github.com/google-gemini/deprecated-generative-ai-python/issues/745)
- [Inconsistent Gemini Output with Identical Input -- Even at temperature=0](https://discuss.ai.google.dev/t/inconsistent-gemini-output-with-identical-input-even-at-temperature-0/98096)
- [Content generation parameters - Vertex AI](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/content-generation-parameters)

### Transactional Outbox Pattern
- [Microservices Pattern: Transactional outbox](https://microservices.io/patterns/data/transactional-outbox.html)
- [Transactional outbox pattern - AWS Prescriptive Guidance](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/transactional-outbox.html)

### JSONB Schema Evolution
- [Zero-Downtime PostgreSQL JSONB Migration](https://medium.com/@shinyjai2011/zero-downtime-postgresql-jsonb-migration-a-practical-guide-for-scalable-schema-evolution-9f74124ef4a1)
- [7 Postgres JSONB Patterns for Semi-Structured Speed](https://medium.com/@connect.hashblock/7-postgres-jsonb-patterns-for-semi-structured-speed-69f02f727ce5)

### LangGraph Architecture
- [LangGraph Multi-Agent Orchestration: Complete Framework Guide](https://latenode.com/blog/langgraph-multi-agent-orchestration-complete-framework-guide-architecture-analysis-2025)
- [LangGraph state management: merge state from parallel branches](https://forum.langchain.com/t/question-why-does-langgraph-merge-state-from-parallel-branches-instead-of-branch-isolation/602)

---

*Pitfalls research for: Clinical Trial Criteria Extraction -- Pipeline Consolidation, ToolUniverse Grounding, and E2E Quality Fixes*
*Researched: 2026-02-16*
*Confidence: HIGH -- Based on codebase analysis, E2E test report, official documentation, ToolUniverse repository inspection, and multiple verified sources*
