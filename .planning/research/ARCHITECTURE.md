# Architecture Patterns: Pipeline Consolidation & ToolUniverse Grounding Integration

**Domain:** Clinical trial criteria extraction pipeline refactoring
**Researched:** 2026-02-16
**Confidence:** HIGH (based on verified codebase analysis, official API docs, ToolUniverse documentation)

## Executive Summary

This document analyzes the current two-service pipeline architecture (extraction-service + grounding-service) and proposes a consolidation strategy plus ToolUniverse integration for entity-type-aware grounding. After thorough codebase analysis, the recommendation is **Option A: Single protocol-processor-service with a 5-node LangGraph** (ingest, extract, parse, ground, persist) that replaces the outbox-mediated handoff between services with a single graph invocation. ToolUniverse tools (RxNorm, ICD-10, LOINC, HPO, EFO) complement the existing UMLS MCP server via an entity-type-aware routing layer, rather than replacing it.

The key architectural insight is that the current two-service split provides zero operational benefit: both services run in the same process, share the same database engine import, and the outbox event between them adds latency and failure modes with no decoupling gain. Consolidation removes the `criteria_extracted` outbox event, the grounding trigger handler, and the state duplication between `ExtractionState` and `GroundingState`.

---

## Current Architecture Analysis

### System Topology (As-Is)

```
Protocol Upload (UI)
    |
    v
api-service (FastAPI) ---> OutboxEvent("protocol_uploaded")
    |
    v (outbox poll, run_in_executor)
extraction-service LangGraph:
    ingest -> extract -> parse -> queue
    |                              |
    | (queue_node creates)         |
    v                              v
OutboxEvent("criteria_extracted")  CriteriaBatch + Criteria records
    |
    v (outbox poll, run_in_executor)
grounding-service LangGraph:
    medgemma_ground -> validate_confidence
    |                       |
    v                       v
UMLS MCP (concept_search)  Entity records + OutboxEvent("entities_grounded")
```

### Current File Structure (With Exact References)

**Extraction Service (4-node graph):**
- `services/extraction-service/src/extraction_service/graph.py` -- StateGraph: START -> ingest -> extract -> parse -> queue -> END
- `services/extraction-service/src/extraction_service/state.py` -- `ExtractionState` TypedDict (protocol_id, file_uri, title, pdf_bytes, raw_criteria, criteria_batch_id, error)
- `services/extraction-service/src/extraction_service/trigger.py` -- `handle_protocol_uploaded()` bridges outbox to graph.ainvoke()
- `services/extraction-service/src/extraction_service/nodes/ingest.py` -- fetches PDF bytes, updates protocol status to "extracting"
- `services/extraction-service/src/extraction_service/nodes/extract.py` -- Gemini File API extraction with structured output (ExtractionResult)
- `services/extraction-service/src/extraction_service/nodes/parse.py` -- Python post-processing (assertion refinement, confidence calibration, dedup)
- `services/extraction-service/src/extraction_service/nodes/queue.py` -- persists CriteriaBatch + Criteria, publishes `criteria_extracted` outbox event

**Grounding Service (2-node graph):**
- `services/grounding-service/src/grounding_service/graph.py` -- StateGraph: START -> medgemma_ground -> validate_confidence -> END
- `services/grounding-service/src/grounding_service/state.py` -- `GroundingState` TypedDict (batch_id, protocol_id, criteria_ids, criteria_texts, raw_entities, grounded_entities, entity_ids, error, iteration_history)
- `services/grounding-service/src/grounding_service/trigger.py` -- `handle_criteria_extracted()` bridges outbox to graph.ainvoke()
- `services/grounding-service/src/grounding_service/nodes/medgemma_ground.py` -- agentic loop: MedGemma extract -> UMLS MCP concept_search -> MedGemma evaluate -> refine (max 3 iterations)
- `services/grounding-service/src/grounding_service/nodes/validate_confidence.py` -- CUI validation, Entity record persistence, batch status update, outbox event publishing

**Shared Infrastructure:**
- `libs/events-py/src/events_py/outbox.py` -- `OutboxProcessor` with poll-and-process loop, `persist_with_outbox()` helper
- `libs/events-py/src/events_py/models.py` -- `DomainEventKind` enum (PROTOCOL_UPLOADED, CRITERIA_EXTRACTED, ENTITIES_GROUNDED)
- `libs/shared/src/shared/models.py` -- Protocol, CriteriaBatch, Criteria, Entity, Review, AuditLog, OutboxEvent SQLModels
- `libs/shared/src/shared/resilience.py` -- circuit breakers: gemini_breaker, umls_breaker, vertex_ai_breaker, gcs_breaker
- `libs/inference/src/inference/model_garden.py` -- `ModelGardenChatModel` for MedGemma on Vertex AI
- `libs/inference/src/inference/config.py` -- `AgentConfig` for model backend selection

**UMLS MCP Server:**
- `services/umls-mcp-server/src/umls_mcp_server/server.py` -- FastMCP with concept_search, concept_linking, semantic_type_prediction tools
- `services/umls-mcp-server/src/umls_mcp_server/umls_api.py` -- `UmlsClient` with disk cache, retry, exception hierarchy; searches SNOMEDCT_US only

**API Service Integration:**
- `services/api-service/src/api_service/main.py` -- OutboxProcessor registered with handlers for both `protocol_uploaded` and `criteria_extracted`
- `services/api-service/src/api_service/umls_search.py` -- REST proxy (GET /api/umls/search) wrapping UmlsClient.search_snomed()

### Critical Observation: False Microservice Boundary

Both services import `from api_service.storage import engine` (same DB engine). Both services run in the same FastAPI process (registered as outbox handlers in `main.py` lifespan). The outbox event between extraction and grounding is an intra-process message that:

1. Writes an OutboxEvent row to PostgreSQL
2. Waits for the next poll cycle (1 second default)
3. Reads the event back from PostgreSQL
4. Deserializes the payload
5. Constructs a new GroundingState from scratch
6. Re-loads criteria_texts from the database (data it just wrote)

This adds approximately 1-3 seconds of pure overhead and introduces failure modes (dead-letter on grounding trigger failure) for what should be a direct function call.

### Current Grounding Limitations

The UMLS MCP server searches only **SNOMEDCT_US** vocabulary. Entity types in the system include Condition, Medication, Procedure, Lab_Value, Demographic, and Biomarker, but all are grounded through the same SNOMED-only search. This means:

- **Medications** (e.g., "acetaminophen") get SNOMED codes but not RxNorm CUIs
- **Lab values** (e.g., "HbA1c") get SNOMED codes but not LOINC codes
- **Phenotypes** (e.g., "hearing loss") lack HPO codes that clinical trials use
- **Demographics** and some conditions lack ICD-10-CM codes used in EHR matching

---

## Recommended Architecture: Consolidated Pipeline

### Decision: Option A -- Single Service with 5-Node Graph

**Rationale:** The services already share a process, database engine, and Python environment. The outbox event between them adds latency and failure modes without decoupling benefit. A single graph is simpler to reason about, test, deploy, and debug.

Option B (keep 2 services but simplify) retains the false microservice boundary and the outbox overhead for no benefit. The only argument for it would be independent deployment, but since both services run in the same container, this argument does not apply.

### Consolidated Graph Structure

```
START -> ingest -> extract -> parse -> ground -> persist -> END
```

**Five nodes, one graph, one state:**

| Node | Source | Responsibility | Invokes |
|------|--------|---------------|---------|
| `ingest` | Existing `ingest_node` (unchanged) | Fetch PDF bytes, update protocol status to "extracting" | GCS/local file fetch |
| `extract` | Existing `extract_node` (unchanged) | Gemini File API structured extraction | Gemini API |
| `parse` | Existing `parse_node` (unchanged) | Assertion refinement, confidence calibration, dedup | Pure Python |
| `ground` | **NEW** -- merges queue persistence + grounding | Persist criteria, extract entities, route to terminology APIs, ground | MedGemma + UMLS/RxNorm/LOINC/HPO/ICD-10/EFO |
| `persist` | Adapted from `validate_confidence_node` | Validate CUIs, persist Entity records, update batch status, update protocol status | UMLS REST API |

### Consolidated State Definition

```python
class PipelineState(TypedDict):
    """Unified state for the extraction-grounding pipeline."""
    # Input
    protocol_id: str
    file_uri: str
    title: str

    # Extraction phase
    pdf_bytes: bytes
    raw_criteria: list[dict[str, Any]]

    # Persistence phase (replaces separate criteria_batch_id)
    batch_id: str
    criteria_ids: list[str]

    # Grounding phase
    criteria_texts: list[dict[str, Any]]
    grounded_entities: list[dict[str, Any]]
    entity_ids: list[str]

    # Agentic loop tracking
    iteration_history: list[dict[str, Any]]

    # Error handling
    error: str | None
```

### Consolidated Graph Definition

```python
def create_graph() -> Any:
    workflow = StateGraph(PipelineState)

    workflow.add_node("ingest", ingest_node)
    workflow.add_node("extract", extract_node)
    workflow.add_node("parse", parse_node)
    workflow.add_node("ground", ground_node)       # NEW
    workflow.add_node("persist", persist_node)      # Adapted

    workflow.add_edge(START, "ingest")
    workflow.add_conditional_edges("ingest", should_continue,
        {"continue": "extract", "error": END})
    workflow.add_conditional_edges("extract", should_continue,
        {"continue": "parse", "error": END})
    workflow.add_edge("parse", "ground")
    workflow.add_conditional_edges("ground", should_continue,
        {"continue": "persist", "error": END})
    workflow.add_edge("persist", END)

    return workflow.compile()
```

### What the `ground` Node Does

The `ground` node is the most complex. It combines what `queue_node` and `medgemma_ground_node` currently do:

1. **Persist criteria** (from current `queue_node`): Create CriteriaBatch + Criteria records, flush to get IDs
2. **Load criteria texts** for grounding (currently done redundantly in grounding-service)
3. **MedGemma entity extraction**: Call MedGemma to extract entities with search terms
4. **Entity-type-aware routing**: Route entities to appropriate terminology APIs based on type
5. **MedGemma evaluation**: Feed search results back to MedGemma for selection
6. **Return grounded entities** for persistence by next node

The key insight is that step 1 (persist criteria) must happen before step 2 (load criteria texts for grounding) because criteria IDs are needed for entity-criteria linkage. In the current architecture, this is handled by the outbox -- queue_node persists, outbox fires, grounding loads. In the consolidated architecture, this happens within a single graph node.

### Outbox Pattern Fate

**Keep the `protocol_uploaded` outbox event.** This event bridges the API upload endpoint to the pipeline. The upload is a user-facing HTTP request that should return immediately. The outbox provides the async handoff.

**Remove the `criteria_extracted` outbox event.** This event was only used to trigger grounding-service. With consolidation, grounding happens in the same graph. The `persist_with_outbox` call in `queue_node` is replaced with a direct session.commit() followed by the grounding step.

**Keep the `entities_grounded` outbox event** (but it becomes optional). Currently published by `validate_confidence_node`. In the consolidated pipeline, the `persist` node can still publish this event if downstream consumers need it (e.g., future notification system), but it is no longer required for pipeline flow.

**Updated OutboxProcessor handler registration:**

```python
# Before (main.py lifespan)
processor = OutboxProcessor(
    engine=engine,
    handlers={
        "protocol_uploaded": [handle_protocol_uploaded],
        "criteria_extracted": [handle_criteria_extracted],    # REMOVE
    },
)

# After
processor = OutboxProcessor(
    engine=engine,
    handlers={
        "protocol_uploaded": [handle_protocol_uploaded],
        # criteria_extracted handler removed -- grounding is in-graph
    },
)
```

---

## ToolUniverse Integration Architecture

### What ToolUniverse Provides

[ToolUniverse](https://zitniklab.hms.harvard.edu/2025/06/03/ToolUniverse/) (Zitnik Lab, Harvard) is a unified ecosystem of 211+ biomedical tools integrated with Model Context Protocol (MCP). Relevant tools for this system:

| Tool | Tools Count | Purpose | API Backend |
|------|------------|---------|-------------|
| `RxNormTool` | 1 | Drug name normalization to RXCUI | NLM RxNorm REST API (rxnav.nlm.nih.gov) |
| `ICD10Tool` | 2 | ICD-10-CM code lookup | NLM/WHO ICD-10 APIs |
| `ICDTool` | 3 | General ICD coding | NLM APIs |
| `LOINCTool` | 4 | Lab test LOINC code lookup | NLM Clinical Tables API |
| `HPOTool` | 3 | Human Phenotype Ontology lookup | HPO/Monarch API |
| `EFOTool` | 1 | Experimental Factor Ontology lookup | EMBL-EBI OLS API |

**Confidence: MEDIUM** -- ToolUniverse documentation confirms these tools exist with MCP integration, but detailed API specs per tool were not fully verified beyond RxNorm.

### Integration Strategy: Complement, Not Replace

**Do NOT replace the UMLS MCP server with ToolUniverse.** Instead, build an entity-type-aware routing layer that dispatches to the most appropriate terminology API based on entity type.

**Rationale:**
1. The UMLS MCP server already works and provides SNOMED codes (the primary ontology for conditions and procedures)
2. ToolUniverse adds coverage for medication-specific (RxNorm), lab-specific (LOINC), and phenotype-specific (HPO) terminologies
3. The UMLS Metathesaurus already integrates SNOMED, LOINC, and RxNorm -- but searching SNOMEDCT_US-only misses the specialized terminologies
4. ToolUniverse tools call the same underlying NLM APIs that the UMLS client uses, but with domain-specific search strategies

### Entity-Type-Aware Routing Pattern

```
Entity extracted by MedGemma
    |
    v
TerminologyRouter (pure Python, no LLM)
    |
    +-- entity_type == "Medication"     --> RxNorm API (primary) + UMLS SNOMED (secondary)
    +-- entity_type == "Condition"      --> UMLS SNOMED (primary) + ICD-10 (secondary)
    +-- entity_type == "Procedure"      --> UMLS SNOMED (primary only)
    +-- entity_type == "Lab_Value"      --> LOINC API (primary) + UMLS SNOMED (secondary)
    +-- entity_type == "Demographic"    --> ICD-10 (primary, for age/gender codes)
    +-- entity_type == "Biomarker"      --> UMLS SNOMED (primary) + HPO (secondary)
    |
    v
Results aggregated, best match selected by MedGemma evaluation
```

### Routing Implementation

```python
@dataclass
class TerminologyResult:
    """Result from a terminology lookup."""
    code: str
    display: str
    system: str              # "SNOMEDCT_US", "RxNorm", "LOINC", "ICD-10-CM", "HPO", "EFO"
    confidence: float
    method: str              # "exact_match", "semantic_similarity", "expert_review"

class TerminologyRouter:
    """Routes entities to appropriate terminology APIs based on entity type."""

    ROUTING_TABLE: dict[str, list[str]] = {
        "Condition":   ["umls_snomed", "icd10"],
        "Medication":  ["rxnorm", "umls_snomed"],
        "Procedure":   ["umls_snomed"],
        "Lab_Value":   ["loinc", "umls_snomed"],
        "Demographic": ["icd10"],
        "Biomarker":   ["umls_snomed", "hpo"],
    }

    async def search(
        self, entity_text: str, entity_type: str, context: str = ""
    ) -> list[TerminologyResult]:
        """Search all relevant terminologies for an entity."""
        systems = self.ROUTING_TABLE.get(entity_type, ["umls_snomed"])
        results: list[TerminologyResult] = []
        for system in systems:
            try:
                system_results = await self._search_system(system, entity_text, context)
                results.extend(system_results)
            except Exception as e:
                logger.warning("Terminology search failed for %s/%s: %s", system, entity_text, e)
        return results

    async def _search_system(
        self, system: str, term: str, context: str
    ) -> list[TerminologyResult]:
        """Dispatch to specific terminology API."""
        if system == "umls_snomed":
            return await self._search_umls(term)
        elif system == "rxnorm":
            return await self._search_rxnorm(term)
        elif system == "loinc":
            return await self._search_loinc(term)
        elif system == "icd10":
            return await self._search_icd10(term)
        elif system == "hpo":
            return await self._search_hpo(term)
        return []
```

### Where ToolUniverse Fits vs Direct API Calls

**Two implementation paths for the terminology router:**

**Path 1: Direct API clients (RECOMMENDED for v1.6)**
Build thin HTTP clients for each API (RxNorm, LOINC, ICD-10, HPO), following the same patterns as the existing `UmlsClient`:
- `RxNormClient` -- calls `https://rxnav.nlm.nih.gov/REST/` (no API key needed)
- `LoincClient` -- calls `https://clinicaltables.nlm.nih.gov/api/loinc/v3/` (no API key needed)
- `Icd10Client` -- calls NLM ICD-10-CM API (no API key needed)
- `HpoClient` -- calls HPO/Monarch API (no API key needed)

**Rationale for direct clients:**
- No additional dependencies (just httpx, already in project)
- Same patterns as existing UmlsClient (disk cache, retry, circuit breaker)
- Full control over error handling and response parsing
- ToolUniverse is a research tool ecosystem, not a production-hardened API client

**Path 2: ToolUniverse as MCP server (FUTURE consideration)**
ToolUniverse provides MCP integration, so in theory it could replace multiple direct clients with a single MCP server exposing all tools. However:
- ToolUniverse is a research project (Harvard Zitnik Lab), not a production dependency
- It installs 211+ tools when only 5-6 are needed
- Adds a large dependency surface (pip install tooluniverse)
- The underlying APIs are the same -- ToolUniverse just wraps them

**Verdict:** Build direct clients now. Evaluate ToolUniverse if the direct client approach proves too maintenance-heavy.

---

## Data Flow Changes

### Current Data Flow (2-Service)

```
1. Upload
   UI -> POST /protocols/upload -> Protocol(status="uploaded")
   + OutboxEvent("protocol_uploaded", {protocol_id, file_uri, title})

2. Outbox poll -> handle_protocol_uploaded()
   -> asyncio.run(extraction_graph.ainvoke(initial_state))

3. Extraction graph runs:
   ingest: fetch PDF bytes -> {pdf_bytes}
   extract: Gemini File API -> {raw_criteria}
   parse: Python post-process -> {raw_criteria refined}
   queue: persist CriteriaBatch + Criteria -> {criteria_batch_id}
   + OutboxEvent("criteria_extracted", {batch_id, criteria_ids})
   + Protocol(status="extracted")

4. Outbox poll -> handle_criteria_extracted()
   -> asyncio.run(grounding_graph.ainvoke(initial_state))

5. Grounding graph runs:
   medgemma_ground: [RE-LOADS criteria from DB], MedGemma extract,
     UMLS search, MedGemma evaluate -> {grounded_entities}
   validate_confidence: validate CUIs, persist Entity records,
     update batch status -> {entity_ids}
   + OutboxEvent("entities_grounded")
   + Protocol(status="pending_review")
```

**Total outbox events in pipeline: 3** (protocol_uploaded, criteria_extracted, entities_grounded)
**Redundant DB reads: 1** (grounding re-loads criteria from DB)
**Latency overhead: ~2-3 seconds** (two outbox poll cycles)

### Proposed Data Flow (Consolidated)

```
1. Upload (UNCHANGED)
   UI -> POST /protocols/upload -> Protocol(status="uploaded")
   + OutboxEvent("protocol_uploaded", {protocol_id, file_uri, title})

2. Outbox poll -> handle_protocol_uploaded()
   -> asyncio.run(pipeline_graph.ainvoke(initial_state))

3. Pipeline graph runs (single invocation):
   ingest: fetch PDF bytes -> {pdf_bytes}
   extract: Gemini File API -> {raw_criteria}
   parse: Python post-process -> {raw_criteria refined}
   ground: persist criteria, extract entities with MedGemma,
     route to terminology APIs, MedGemma evaluate
     -> {batch_id, criteria_ids, grounded_entities}
   persist: validate CUIs, persist Entity records,
     update batch + protocol status
     -> {entity_ids}
   + Protocol(status="pending_review")

4. (Optional) OutboxEvent("entities_grounded") for downstream consumers
```

**Total outbox events in pipeline: 1** (protocol_uploaded only) + 1 optional (entities_grounded)
**Redundant DB reads: 0** (criteria data flows through state)
**Latency overhead: ~0 seconds** (no inter-service outbox poll)

### Data Flow Within `ground` Node (Detailed)

```
ground_node(state: PipelineState) -> dict:
    # Step 1: Persist criteria (from old queue_node)
    batch = CriteriaBatch(protocol_id=state["protocol_id"])
    session.add(batch) -> flush -> batch.id

    for criterion in state["raw_criteria"]:
        criteria = Criteria(batch_id=batch.id, ...)
        session.add(criteria) -> flush -> criteria.id
        criteria_ids.append(criteria.id)

    session.commit()

    # Step 2: Build criteria_texts for grounding (no DB re-read needed)
    criteria_texts = [
        {"id": cid, "text": raw["text"], "criteria_type": raw["criteria_type"], ...}
        for cid, raw in zip(criteria_ids, state["raw_criteria"])
    ]

    # Step 3: MedGemma entity extraction
    entities = await medgemma_extract(criteria_texts)

    # Step 4: Entity-type-aware routing
    for entity in entities:
        results = await terminology_router.search(
            entity.text, entity.entity_type, entity.context_window
        )
        entity.candidates = results

    # Step 5: MedGemma evaluation (select best matches)
    grounded = await medgemma_evaluate(entities)

    return {
        "batch_id": batch.id,
        "criteria_ids": criteria_ids,
        "criteria_texts": criteria_texts,
        "grounded_entities": grounded,
    }
```

### field_mappings Pre-Loading

The milestone context mentions "field_mappings pre-loading." In the current system, field_mappings are stored in `Criteria.conditions` JSONB field as `{"field_mappings": [...]}` (set via ReviewActionRequest.modified_structured_fields). For the consolidated pipeline, field_mappings would be pre-loaded as follows:

**Use case:** Re-extraction of a protocol that already has human-reviewed field_mappings. The system should preserve human edits.

**Architecture:**
```python
# In ground_node, before MedGemma extraction:
existing_batch = session.query(CriteriaBatch).filter_by(
    protocol_id=state["protocol_id"],
    status="approved"
).first()

if existing_batch:
    # Load existing criteria with field_mappings
    existing_criteria = session.query(Criteria).filter_by(
        batch_id=existing_batch.id
    ).all()
    field_mappings_by_text = {
        c.text: c.conditions.get("field_mappings", [])
        for c in existing_criteria
        if c.conditions and "field_mappings" in c.conditions
    }
    # Pass to grounding as context
    state["existing_field_mappings"] = field_mappings_by_text
```

This is a separate feature from consolidation and should be built in a subsequent phase.

### Re-Extraction Architecture

Re-extraction (reprocessing a protocol with updated prompts/models) requires:

1. **New API endpoint:** POST /protocols/{id}/reextract
2. **New outbox event:** `protocol_reextract_requested` (payload includes protocol_id + previous batch_id)
3. **Pipeline behavior:** The consolidated graph handles re-extraction identically to initial extraction, but the `ground` node can optionally load previous batch data for comparison
4. **Previous batch preservation:** The old CriteriaBatch is NOT deleted -- it gets status "superseded"

This is orthogonal to consolidation and should be a separate phase.

---

## Component Change Inventory

### Files to CREATE

| File | Purpose |
|------|---------|
| `services/protocol-processor/src/protocol_processor/graph.py` | Consolidated 5-node StateGraph |
| `services/protocol-processor/src/protocol_processor/state.py` | `PipelineState` TypedDict |
| `services/protocol-processor/src/protocol_processor/trigger.py` | `handle_protocol_uploaded()` handler |
| `services/protocol-processor/src/protocol_processor/nodes/__init__.py` | Node re-exports |
| `services/protocol-processor/src/protocol_processor/nodes/ground.py` | Combined criteria persistence + grounding |
| `services/protocol-processor/src/protocol_processor/nodes/persist.py` | Entity validation + persistence |
| `services/protocol-processor/src/protocol_processor/routing/router.py` | `TerminologyRouter` with entity-type dispatch |
| `services/protocol-processor/src/protocol_processor/routing/rxnorm.py` | `RxNormClient` thin HTTP client |
| `services/protocol-processor/src/protocol_processor/routing/loinc.py` | `LoincClient` thin HTTP client |
| `services/protocol-processor/src/protocol_processor/routing/icd10.py` | `Icd10Client` thin HTTP client |
| `services/protocol-processor/src/protocol_processor/routing/hpo.py` | `HpoClient` thin HTTP client |
| `libs/shared/src/shared/resilience.py` | Add new circuit breakers: rxnorm_breaker, loinc_breaker, hpo_breaker |

### Files to MOVE (unchanged logic)

| From | To | Notes |
|------|----|-------|
| `extraction_service/nodes/ingest.py` | `protocol_processor/nodes/ingest.py` | State type annotation changes only |
| `extraction_service/nodes/extract.py` | `protocol_processor/nodes/extract.py` | State type annotation changes only |
| `extraction_service/nodes/parse.py` | `protocol_processor/nodes/parse.py` | State type annotation changes only |
| `extraction_service/prompts/` | `protocol_processor/prompts/extraction/` | Directory restructure |
| `grounding_service/prompts/` | `protocol_processor/prompts/grounding/` | Directory restructure |
| `extraction_service/schemas/criteria.py` | `protocol_processor/schemas/criteria.py` | Unchanged |
| `grounding_service/schemas/agentic_actions.py` | `protocol_processor/schemas/agentic_actions.py` | Unchanged |
| `grounding_service/schemas/entities.py` | `protocol_processor/schemas/entities.py` | Unchanged |

### Files to MODIFY

| File | Change |
|------|--------|
| `services/api-service/src/api_service/main.py` | Remove `handle_criteria_extracted` import and handler registration; import from `protocol_processor.trigger` instead of `extraction_service.trigger` |
| `libs/events-py/src/events_py/models.py` | `CRITERIA_EXTRACTED` can be deprecated (keep for backward compat but unused in pipeline) |
| `libs/shared/src/shared/resilience.py` | Add circuit breakers for new terminology APIs |
| `pyproject.toml` | Add `protocol-processor` service, remove `extraction-service` and `grounding-service` |
| `infra/docker-compose.yml` | Update service name references |
| `Makefile` | Update service name references |

### Files to DELETE (after migration)

| File | Reason |
|------|--------|
| `services/extraction-service/` (entire directory) | Consolidated into protocol-processor |
| `services/grounding-service/` (entire directory) | Consolidated into protocol-processor |
| `extraction_service/nodes/queue.py` | Logic moved into ground_node |
| `grounding_service/trigger.py` | No longer needed (no outbox handoff) |
| `grounding_service/nodes/ground_to_umls.py` | Legacy node (replaced by agentic grounding in Phase 20) |
| `grounding_service/nodes/map_to_snomed.py` | Legacy node (replaced by agentic grounding in Phase 20) |
| `grounding_service/nodes/extract_entities.py` | Legacy node (replaced by agentic grounding in Phase 20) |

### Files UNCHANGED

| File | Why |
|------|-----|
| `services/umls-mcp-server/` | Retained as-is; TerminologyRouter uses it for SNOMED lookups |
| `services/api-service/src/api_service/reviews.py` | No changes needed |
| `services/api-service/src/api_service/umls_search.py` | Retained for frontend autocomplete |
| `libs/shared/src/shared/models.py` | Entity model already has fields for multi-system codes |
| `apps/hitl-ui/` | No changes needed (consumes same API) |

---

## New Component Architecture: TerminologyRouter

### Component Boundaries

```
protocol_processor/
    routing/
        __init__.py          # Re-exports TerminologyRouter
        router.py            # TerminologyRouter class
        base.py              # BaseTerminologyClient ABC
        umls_snomed.py       # Existing UmlsClient adapter
        rxnorm.py            # RxNormClient (new)
        loinc.py             # LoincClient (new)
        icd10.py             # Icd10Client (new)
        hpo.py               # HpoClient (new)
```

### Client Interface Contract

```python
class BaseTerminologyClient(ABC):
    """Abstract base for terminology API clients."""

    @abstractmethod
    async def search(self, term: str, max_results: int = 5) -> list[TerminologyResult]:
        """Search for concepts matching a term."""
        ...

    @abstractmethod
    async def validate_code(self, code: str) -> bool:
        """Validate that a code exists in this terminology."""
        ...

    @property
    @abstractmethod
    def system_name(self) -> str:
        """Terminology system identifier (e.g., 'RxNorm', 'LOINC')."""
        ...
```

### RxNorm Client (New)

```python
class RxNormClient(BaseTerminologyClient):
    """Client for NLM RxNorm REST API.

    No API key required. Free public API.
    Base URL: https://rxnav.nlm.nih.gov/REST/
    """
    BASE_URL = "https://rxnav.nlm.nih.gov/REST"

    async def search(self, term: str, max_results: int = 5) -> list[TerminologyResult]:
        # GET /drugs.json?name={term}
        # Falls back to /approximateTerm.json?term={term} for fuzzy matching
        ...

    async def validate_code(self, rxcui: str) -> bool:
        # GET /rxcui/{rxcui}/properties.json
        ...

    @property
    def system_name(self) -> str:
        return "RxNorm"
```

### LOINC Client (New)

```python
class LoincClient(BaseTerminologyClient):
    """Client for NLM Clinical Tables LOINC API.

    No API key required. Free public API.
    Base URL: https://clinicaltables.nlm.nih.gov/api/loinc/v3/
    """
    BASE_URL = "https://clinicaltables.nlm.nih.gov/api/loinc/v3"

    async def search(self, term: str, max_results: int = 5) -> list[TerminologyResult]:
        # GET /search?terms={term}&maxList={max_results}
        ...

    @property
    def system_name(self) -> str:
        return "LOINC"
```

### Entity Model Extension

The existing `Entity` SQLModel already has `umls_cui` and `snomed_code` fields. For multi-system grounding, the Entity model needs additional code fields:

```python
# In libs/shared/src/shared/models.py -- Entity class
class Entity(SQLModel, table=True):
    # ... existing fields ...
    umls_cui: str | None = Field(default=None)
    snomed_code: str | None = Field(default=None)
    # NEW fields for multi-system grounding
    rxnorm_code: str | None = Field(default=None)
    loinc_code: str | None = Field(default=None)
    icd10_code: str | None = Field(default=None)
    hpo_code: str | None = Field(default=None)
    # Track which system provided the grounding
    grounding_system: str | None = Field(default=None)  # "SNOMEDCT_US", "RxNorm", "LOINC", etc.
```

This requires an Alembic migration to add 4 nullable columns. Since they are nullable with defaults, this is a non-destructive migration.

---

## Integration Points Summary

### API Service <-> Pipeline

| Integration Point | Current | Proposed |
|-------------------|---------|----------|
| Pipeline trigger | OutboxProcessor calls `handle_protocol_uploaded` (extraction-service) | OutboxProcessor calls `handle_protocol_uploaded` (protocol-processor) |
| Grounding trigger | OutboxProcessor calls `handle_criteria_extracted` (grounding-service) | **REMOVED** -- grounding is in-graph |
| Protocol status updates | Both triggers update Protocol.status independently | Single trigger, ground_node and persist_node update status |
| Entity persistence | validate_confidence_node writes Entity records | persist_node writes Entity records |

### Pipeline <-> External APIs

| API | Current | Proposed |
|-----|---------|----------|
| Gemini File API | extract_node calls google.genai.Client | **UNCHANGED** |
| MedGemma (Vertex) | medgemma_ground_node calls ModelGardenChatModel | ground_node calls ModelGardenChatModel |
| UMLS MCP | medgemma_ground_node calls concept_search via MCP stdio | TerminologyRouter calls UmlsClient directly (MCP optional) |
| UMLS REST API | validate_confidence_node calls validate_cui() | persist_node calls validate_cui() |
| RxNorm API | (none) | **NEW** -- TerminologyRouter calls RxNormClient |
| LOINC API | (none) | **NEW** -- TerminologyRouter calls LoincClient |
| ICD-10 API | (none) | **NEW** -- TerminologyRouter calls Icd10Client |
| HPO API | (none) | **NEW** -- TerminologyRouter calls HpoClient |

### Pipeline <-> Database

| Operation | Current | Proposed |
|-----------|---------|----------|
| CriteriaBatch + Criteria creation | queue_node (extraction-service) | ground_node (protocol-processor) |
| Entity creation | validate_confidence_node (grounding-service) | persist_node (protocol-processor) |
| CriteriaBatch status update | validate_confidence_node | persist_node |
| Protocol status update | Both triggers + both graphs | Single trigger + persist_node |

### UMLS MCP Server: Direct Client vs MCP

The current grounding-service uses the UMLS MCP server via `langchain-mcp-adapters` with stdio transport. This involves:
1. Spawning a subprocess (uv run python -m umls_mcp_server.server)
2. JSON-RPC communication over stdio
3. MCP protocol overhead

For the consolidated pipeline, the TerminologyRouter should call the `UmlsClient` directly (it is already a Python library in the same virtualenv). The MCP server remains available for external tools (Claude, Cursor) and the frontend autocomplete proxy.

**Rationale:** The MCP server adds subprocess management overhead and stdio serialization cost. Since we control both the client and server, and they run in the same process, direct library import is simpler and faster.

---

## Build Order (Dependency-Aware)

### Phase 1: Create protocol-processor skeleton (LOW RISK)

**What:** Create the new service directory structure, move unchanged nodes (ingest, extract, parse), create PipelineState, wire up basic graph without grounding.

**Dependencies:** None
**Risk:** Low -- only moving files and changing import paths
**Deliverable:** 4-node graph (ingest -> extract -> parse -> persist_criteria) that does what extraction-service does today, without grounding

**Files created:**
- `services/protocol-processor/` directory structure
- `protocol_processor/state.py` (PipelineState)
- `protocol_processor/graph.py` (4-node initially)
- `protocol_processor/trigger.py`
- Move `nodes/ingest.py`, `nodes/extract.py`, `nodes/parse.py`
- `nodes/persist_criteria.py` (simplified queue_node without outbox event)

### Phase 2: Terminology router foundation (MEDIUM RISK)

**What:** Build BaseTerminologyClient, RxNormClient, LoincClient, Icd10Client, HpoClient, and TerminologyRouter. Unit test each client against real APIs.

**Dependencies:** None (independent of Phase 1)
**Risk:** Medium -- new external API integrations, need to verify response formats
**Deliverable:** TerminologyRouter that can search multiple terminology systems by entity type

**Files created:**
- `protocol_processor/routing/` package
- Individual client modules
- Unit tests for each client
- Circuit breakers in `shared/resilience.py`

### Phase 3: Ground node implementation (HIGH RISK)

**What:** Build the ground_node that combines criteria persistence, MedGemma extraction, entity-type-aware routing, and MedGemma evaluation. Adapt the agentic loop from `medgemma_ground_node` to use TerminologyRouter instead of UMLS-only MCP.

**Dependencies:** Phase 1 (skeleton exists), Phase 2 (TerminologyRouter exists)
**Risk:** High -- this is the most complex node, combining logic from queue_node and medgemma_ground_node
**Deliverable:** 5-node graph with full extraction-through-grounding pipeline

**Files created/modified:**
- `protocol_processor/nodes/ground.py` (new, most complex)
- `protocol_processor/prompts/grounding/` (adapted from grounding-service prompts)
- Updated `graph.py` to 5 nodes

### Phase 4: Persist node + Entity model migration (MEDIUM RISK)

**What:** Adapt validate_confidence_node to new state shape, add multi-system code fields to Entity model, create Alembic migration.

**Dependencies:** Phase 3 (ground_node provides grounded_entities)
**Risk:** Medium -- database migration, but all new columns are nullable
**Deliverable:** Entities persisted with multi-system codes

**Files created/modified:**
- `protocol_processor/nodes/persist.py` (adapted from validate_confidence_node)
- `libs/shared/src/shared/models.py` (add rxnorm_code, loinc_code, icd10_code, hpo_code)
- Alembic migration for new columns

### Phase 5: Integration switchover (LOW RISK)

**What:** Update api-service main.py to import from protocol-processor, remove extraction-service and grounding-service handlers, run end-to-end test.

**Dependencies:** Phase 4 (all nodes working)
**Risk:** Low -- simple import changes, but important to verify end-to-end
**Deliverable:** Consolidated pipeline running in production

**Files modified:**
- `services/api-service/src/api_service/main.py`
- `pyproject.toml`
- `infra/docker-compose.yml`
- `Makefile`

### Phase 6: Cleanup (LOW RISK)

**What:** Remove old extraction-service and grounding-service directories, update documentation.

**Dependencies:** Phase 5 (switchover verified)
**Risk:** Low -- only deleting dead code
**Deliverable:** Clean codebase with single pipeline service

### Dependency Graph

```
Phase 1 (Skeleton)     Phase 2 (Terminology Router)
       |                        |
       +------------------------+
                |
        Phase 3 (Ground Node) [HIGHEST RISK]
                |
        Phase 4 (Persist + Migration)
                |
        Phase 5 (Integration Switchover)
                |
        Phase 6 (Cleanup)
```

---

## Scalability Considerations

| Concern | At 50 protocols | At 500 protocols | At 5000 protocols |
|---------|-----------------|-------------------|---------------------|
| Pipeline concurrency | Single outbox processor, 1 at a time | Needs concurrent processing (multiple outbox workers) | Need task queue (Celery/Cloud Tasks) |
| Terminology API rate limits | No issue (NLM APIs are generous) | May need request batching | Need API key + rate limiter |
| Entity volume | ~50 entities per protocol | ~500 per batch | Need bulk insert, async batching |
| MedGemma latency | 3-5 sec per batch (Vertex AI) | Acceptable (sequential per protocol) | Need parallel MedGemma calls per protocol |
| Database connections | Single session per pipeline run | Fine with connection pool | Need pgBouncer |

### Performance Impact of Consolidation

- **Reduced latency:** ~2-3 seconds saved per protocol (no outbox poll between extraction and grounding)
- **Reduced DB operations:** ~3 fewer round-trips per protocol (no outbox write/read, no criteria re-load)
- **Reduced process overhead:** No subprocess spawn for UMLS MCP (using direct client)
- **Memory:** Slightly higher peak memory per pipeline run (single graph holds all state), but negligible at current scale

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Keeping Outbox Between Extraction and Grounding

**What people do:** Consolidate the graph but keep the outbox event between a "persist criteria" node and a "ground" node for "future decoupling."

**Why it is wrong:** YAGNI. The decoupling provides zero value today and adds latency, failure modes, and complexity. If future requirements demand separate services, the outbox can be re-introduced then.

**Do this instead:** A single graph with sequential nodes. If you need to observe the criteria-persisted event for auditing, log it -- do not route pipeline flow through the outbox.

### Anti-Pattern 2: Making ToolUniverse a Runtime Dependency

**What people do:** pip install tooluniverse and use its MCP server as the primary grounding backend.

**Why it is wrong:** ToolUniverse is a research toolkit with 211+ tools, massive dependency footprint, and no production SLA. The underlying APIs (RxNorm, LOINC, etc.) are stable NLM services.

**Do this instead:** Build thin HTTP clients for each API. The clients are 50-100 lines each and depend only on httpx.

### Anti-Pattern 3: Using MedGemma for Entity-Type Routing

**What people do:** Ask MedGemma "which terminology system should I search?" for each entity.

**Why it is wrong:** Entity type to terminology system mapping is a deterministic lookup table, not an LLM reasoning task. LLM calls are expensive and slow.

**Do this instead:** A Python dictionary mapping entity_type to list[system_name]. MedGemma's role is medical reasoning (entity extraction, candidate evaluation), not routing logic.

### Anti-Pattern 4: Replacing SNOMED with RxNorm for Medications

**What people do:** Route medications only to RxNorm and skip SNOMED lookup.

**Why it is wrong:** Clinical trials use both coding systems. SNOMED provides the clinical concept (the substance), while RxNorm provides the drug product (brand, dose form). A medication entity should have both codes.

**Do this instead:** Query both SNOMED (via UMLS) and RxNorm for medication entities. Store both codes in the Entity model.

---

## Communication Pattern: Direct Invoke vs Outbox

### Decision Matrix

| Scenario | Pattern | Rationale |
|----------|---------|-----------|
| UI upload -> pipeline | **Outbox** | User HTTP request should return immediately; pipeline is long-running |
| Extraction -> Grounding (same graph) | **Direct** (sequential nodes) | Same process, same graph, no benefit from async decoupling |
| Pipeline complete -> notification | **Outbox** (optional) | Downstream consumers may need to react (future: email, webhook) |
| Re-extraction request | **Outbox** | User HTTP request should return immediately |
| Frontend UMLS search | **Direct** (REST API) | Synchronous user interaction, needs immediate response |

---

## Sources

### Codebase (HIGH confidence)
- All file references verified against actual codebase at `/Users/noahdolevelixir/Code/medgemma-hackathon/`

### ToolUniverse (MEDIUM confidence)
- [ToolUniverse Documentation](https://zitniklab.hms.harvard.edu/ToolUniverse/)
- [ToolUniverse Available Tools](https://zitniklab.hms.harvard.edu/ToolUniverse/tools/tools_config_index.html)
- [ToolUniverse RxNorm Tool](https://zitniklab.hms.harvard.edu/ToolUniverse/en/_modules/tooluniverse/rxnorm_tool.html)
- [ToolUniverse Announcement](https://zitniklab.hms.harvard.edu/2025/06/03/ToolUniverse/)
- [ToolUniverse GitHub](https://github.com/mims-harvard/ToolUniverse)

### NLM APIs (HIGH confidence)
- [RxNorm API Documentation](https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html)
- [LOINC API Documentation](https://clinicaltables.nlm.nih.gov/apidoc/loinc/v3/doc.html)
- [UMLS REST API Documentation](https://documentation.uts.nlm.nih.gov/)

### Architecture Patterns (MEDIUM confidence)
- [LangGraph Subgraphs Documentation](https://docs.langchain.com/oss/python/langgraph/use-subgraphs)
- [Transactional Outbox Pattern](https://microservices.io/patterns/data/transactional-outbox.html)
- [langchain-mcp-adapters](https://github.com/langchain-ai/langchain-mcp-adapters)

### Clinical Terminologies (HIGH confidence)
- [SNOMED CT, LOINC, and RxNorm Integration](https://pmc.ncbi.nlm.nih.gov/articles/PMC6115234/)
- [Medical Coding Systems Explained](https://www.imohealth.com/resources/medical-coding-systems-explained-icd-10-cm-cpt-snomed-and-others/)

### MedGemma (MEDIUM confidence)
- [MedGemma Model Card](https://developers.google.com/health-ai-developer-foundations/medgemma/model-card)
- [Integrating MedGemma into Clinical Workflows](https://cloud.google.com/blog/topics/developers-practitioners/integrating-medgemma-into-clinical-workflows-just-got-easier)

---

*Architecture research for: Pipeline Consolidation & ToolUniverse Grounding Integration*
*Researched: 2026-02-16*
*Confidence: HIGH -- based on verified codebase analysis with exact file references, official NLM API documentation, and ToolUniverse documentation*
