# Architecture Research

**Domain:** Clinical Trial Protocol Criteria Extraction System
**Researched:** 2026-02-10
**Confidence:** HIGH

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                  Presentation Layer (HITL UI)                │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐          │
│  │  Protocol   │  │  Criteria   │  │  Review &   │          │
│  │   Upload    │  │   Review    │  │  Approval   │          │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘          │
│         │                │                │                  │
├─────────┴────────────────┴────────────────┴──────────────────┤
│              Application Layer (FastAPI Gateway)             │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────────────────┐    ┌──────────────────────┐       │
│  │  Extraction Agent    │    │   Grounding Agent    │       │
│  │  (LangGraph Workflow)│    │  (LangGraph Workflow)│       │
│  │                      │    │                      │       │
│  │  • Protocol Ingest   │    │  • Entity Extract    │       │
│  │  • Gemini Criteria   │    │  • MedGemma NER      │       │
│  │  • Structure Parse   │    │  • UMLS via MCP      │       │
│  │  • HITL Queue        │    │  • SNOMED Mapping    │       │
│  └──────────┬───────────┘    └──────────┬───────────┘       │
│             │                           │                    │
├─────────────┴───────────────────────────┴────────────────────┤
│                    Data & Storage Layer                      │
├─────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │PostgreSQL│  │   GCS    │  │  Events  │  │  UMLS    │    │
│  │  Store   │  │  Bucket  │  │  Queue   │  │   MCP    │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| **api-service** | REST gateway, orchestration, persistence | FastAPI with SQLModel, Google OAuth, event publishing |
| **agent-a-service** | Extraction workflow orchestrator | LangGraph StateGraph with Gemini for criteria extraction, PDF processing via Document AI |
| **agent-b-service** | Grounding workflow orchestrator | LangGraph StateGraph with MedGemma for entity recognition, UMLS MCP server for concept grounding |
| **hitl-ui** | Human review and approval interface | React/Vite SPA with real-time updates, approval workflows, entity validation UI |
| **shared libs** | Common models, events, utilities | SQLModel schemas for protocols/criteria/entities, event definitions, inference loaders |
| **GCS Bucket** | PDF protocol storage | Cloud Storage with versioning, access controls, signed URLs for upload/download |
| **PostgreSQL** | Structured data and audit trail | Relational store with JSON columns for flexibility, event sourcing via outbox pattern |
| **UMLS MCP Server** | Medical concept grounding service | Model Context Protocol server providing SNOMED-CT, RxNorm, LOINC mappings |

## Recommended Project Structure

```
medgemma-hackathon/
├── services/
│   ├── api-service/              # FastAPI REST gateway
│   │   ├── src/api_service/
│   │   │   ├── routers/
│   │   │   │   ├── protocols.py        # Protocol upload, list, retrieve
│   │   │   │   ├── criteria.py         # Extracted criteria CRUD
│   │   │   │   ├── entities.py         # Medical entity endpoints
│   │   │   │   └── reviews.py          # HITL review/approval
│   │   │   ├── services/
│   │   │   │   ├── gcs.py              # GCS signed URLs, upload/download
│   │   │   │   ├── agent_proxy.py      # Invoke LangGraph agents
│   │   │   │   └── events.py           # Event publishing to agents
│   │   │   ├── main.py
│   │   │   ├── dependencies.py         # DB sessions, auth
│   │   │   └── storage.py              # SQLModel setup
│   │   └── alembic/                    # DB migrations
│   ├── agent-a-service/          # Extraction workflow
│   │   ├── src/agent_a_service/
│   │   │   ├── graph.py                # LangGraph workflow definition
│   │   │   ├── nodes.py                # Node implementations:
│   │   │   │                           # - ingest_protocol (GCS fetch)
│   │   │   │                           # - extract_criteria (Gemini)
│   │   │   │                           # - parse_structure (criteria parsing)
│   │   │   │                           # - queue_for_review (persist + event)
│   │   │   └── state.py                # AgentState with protocol, criteria
│   │   └── tests/
│   └── agent-b-service/          # Grounding workflow
│       ├── src/agent_b_service/
│       │   ├── graph.py                # LangGraph workflow definition
│       │   ├── nodes.py                # Node implementations:
│       │   │                           # - extract_entities (MedGemma NER)
│       │   │                           # - ground_to_umls (MCP call)
│       │   │                           # - map_to_snomed (concept mapping)
│       │   │                           # - validate_confidence (threshold check)
│       │   └── state.py                # AgentState with entities, mappings
│       └── tests/
├── apps/
│   └── hitl-ui/                  # React frontend
│       ├── src/
│       │   ├── pages/
│       │   │   ├── ProtocolUpload.tsx   # PDF upload with GCS integration
│       │   │   ├── CriteriaReview.tsx   # Extraction review/edit
│       │   │   └── EntityApproval.tsx   # Grounded entity approval
│       │   ├── components/
│       │   │   ├── CriteriaCard.tsx     # Criteria display/edit
│       │   │   ├── EntityTag.tsx        # Entity with SNOMED badge
│       │   │   └── ApprovalWorkflow.tsx # Approve/reject buttons
│       │   ├── api/
│       │   │   └── client.ts            # OpenAPI-generated client
│       │   └── App.tsx
│       └── package.json
├── libs/
│   ├── shared/                   # Common models
│   │   ├── src/shared/
│   │   │   └── models.py               # Protocol, Criteria, Entity, Review
│   │   └── tests/
│   ├── events-py/                # Event definitions
│   │   ├── src/events_py/
│   │   │   └── models.py               # ProtocolUploaded, CriteriaExtracted,
│   │   │                               # EntityGrounded, ReviewCompleted
│   │   └── tests/
│   ├── inference/                # Model loaders
│   │   ├── src/inference/
│   │   │   ├── loaders.py              # Gemini, MedGemma initialization
│   │   │   └── factory.py              # Agent factory pattern
│   │   └── tests/
│   └── data-pipeline/            # Data ingestion
│       └── src/data_pipeline/
│           └── pdf_processor.py        # Document AI integration
└── infra/
    ├── docker-compose.yml              # Local dev: PostgreSQL, MCP server
    └── terraform/                      # GCP: GCS, Cloud Run, CloudSQL
```

### Structure Rationale

- **services/api-service/routers/**: Organized by domain entity (protocols, criteria, entities, reviews) for clear REST API boundaries. Each router handles CRUD operations and triggers agent workflows via event publishing.
- **services/agent-*-service/nodes.py**: Each node is a single-responsibility function in the LangGraph workflow. Nodes are testable in isolation and compose into complex extraction/grounding pipelines.
- **apps/hitl-ui/pages/**: Page-based routing mirrors the user journey: upload protocol → review extracted criteria → approve grounded entities. Components are reusable across pages.
- **libs/shared/models.py**: Single source of truth for SQLModel schemas. Used by both api-service (persistence) and agent services (data validation). Prevents schema drift.
- **libs/events-py/**: Decouples services via event-driven communication. api-service publishes events; agent services subscribe. Enables async processing and scales horizontally.

## Architectural Patterns

### Pattern 1: LangGraph Agent Orchestration

**What:** LangGraph treats agent workflows as directed acyclic graphs (DAGs) where nodes represent processing steps (agents, functions, decision points) and edges define data flow with conditional logic. A centralized StateGraph maintains context, storing intermediate results and metadata, allowing for parallel execution and conditional branching.

**When to use:** When you need complex, stateful AI workflows with explicit control flow, cycles, branching, and human-in-the-loop checkpoints. Ideal for multi-step extraction pipelines where each step depends on previous results and requires different AI capabilities (document parsing → entity extraction → concept grounding).

**Trade-offs:**
- **Pro:** Maximum control and flexibility; pass only necessary state deltas between nodes (minimal token usage); supports cycles for iterative refinement; built-in persistence and checkpointing.
- **Con:** Steeper learning curve than simple chain-based frameworks; requires explicit state management; more boilerplate for simple linear workflows.

**Example:**
```python
# agent-a-service/graph.py - Extraction workflow
from langgraph.graph import END, START, StateGraph

def create_extraction_graph():
    workflow = StateGraph(ExtractionState)

    # Nodes for each step
    workflow.add_node("ingest_protocol", ingest_protocol_node)
    workflow.add_node("extract_criteria", extract_criteria_node)
    workflow.add_node("parse_structure", parse_structure_node)
    workflow.add_node("queue_for_review", queue_for_review_node)

    # Linear flow with conditional branching
    workflow.add_edge(START, "ingest_protocol")
    workflow.add_edge("ingest_protocol", "extract_criteria")
    workflow.add_conditional_edges(
        "extract_criteria",
        should_parse_further,  # Conditional function
        {
            "parse": "parse_structure",
            "review": "queue_for_review"
        }
    )
    workflow.add_edge("parse_structure", "queue_for_review")
    workflow.add_edge("queue_for_review", END)

    return workflow.compile()
```

### Pattern 2: Event-Driven Microservices with Transactional Outbox

**What:** Services persist state changes and events in the same database transaction (outbox pattern), then a separate process publishes events to a message broker. This ensures event publication never fails independently of state changes, maintaining consistency. PostgreSQL doesn't support native change data capture subscriptions, so the outbox table bridges the gap.

**When to use:** When you need guaranteed event delivery between microservices, eventual consistency, and fault tolerance. Essential for medical data systems where audit trails and data integrity are critical. Enables async processing of heavy AI workloads without blocking API responses.

**Trade-offs:**
- **Pro:** Strong consistency guarantees; events never lost; enables async processing; scales horizontally; clear audit trail.
- **Con:** Increased complexity (outbox processor); eventual consistency (not immediate); requires event schema versioning; potential message duplication (idempotency needed).

**Example:**
```python
# api-service/services/events.py
from sqlmodel import Session, select
from shared.models import OutboxEvent, Protocol

async def publish_protocol_uploaded_event(
    protocol: Protocol,
    db: Session
):
    # Atomic: persist protocol + outbox event in same transaction
    event = OutboxEvent(
        event_type="protocol_uploaded",
        aggregate_id=protocol.id,
        payload={
            "protocol_id": protocol.id,
            "gcs_path": protocol.gcs_path,
            "user_id": protocol.uploaded_by
        },
        status="pending"
    )
    db.add(event)
    db.commit()

    # Separate process polls outbox and publishes to message broker
    # (e.g., Cloud Pub/Sub, RabbitMQ, Kafka)
```

### Pattern 3: Human-in-the-Loop (HITL) Review Workflow

**What:** AI agents automate parts of the workflow, but humans remain involved at key decision points for validation and approval. The system pre-screens and structures data (extraction, entity recognition, concept grounding), then queues results for clinical researcher review. Humans can accept, modify, or reject AI outputs, creating a feedback loop for model improvement.

**When to use:** High-stakes domains like healthcare where AI outputs require expert validation before use. Regulatory requirements (explainability, accountability) mandate human oversight. Enables AI to handle repetitive work while experts focus on edge cases and quality assurance.

**Trade-offs:**
- **Pro:** Builds trust and regulatory compliance; improves accuracy over pure automation; creates labeled training data from corrections; domain experts control final decisions.
- **Con:** Bottleneck if review queue grows; requires clear UX for efficient review; risk of "automation bias" if reviewers rubber-stamp AI outputs; needs performance tracking to detect drift.

**Example:**
```python
# agent-a-service/nodes.py
def queue_for_review_node(state: ExtractionState) -> ExtractionState:
    """Final node: persist extracted criteria and notify HITL UI."""
    criteria_batch = CriteriaBatch(
        protocol_id=state["protocol_id"],
        criteria=state["extracted_criteria"],
        extraction_confidence=state["confidence_scores"],
        status="pending_review",  # HITL status
        review_assigned_to=None,  # Assigned when clinician claims
        review_deadline=datetime.now() + timedelta(days=2)
    )

    # Persist and publish event for HITL UI
    db.add(criteria_batch)
    db.commit()

    publish_event("criteria_ready_for_review", {
        "batch_id": criteria_batch.id,
        "num_criteria": len(state["extracted_criteria"]),
        "protocol_title": state["protocol_title"]
    })

    return state
```

### Pattern 4: Model Context Protocol (MCP) for External Knowledge

**What:** MCP provides a standardized semantic transport for sharing rich context and tools across AI agents. An MCP server exposes medical ontologies (UMLS, SNOMED-CT) as callable tools that agents can invoke for concept grounding, semantic type prediction, and entity linking. This decouples medical knowledge from agent code.

**When to use:** When agents need access to large, version-controlled external knowledge bases (medical ontologies, drug databases) that update independently. MCP servers handle complex lookups (semantic similarity, concept hierarchies) and return structured results, abstracting implementation details from agents.

**Trade-offs:**
- **Pro:** Clean separation of concerns; ontology updates don't require agent redeployment; reusable across multiple agents; supports caching and performance optimization.
- **Con:** Network latency for remote calls; requires MCP server infrastructure; potential single point of failure; versioning complexity for ontology updates.

**Example:**
```python
# agent-b-service/nodes.py
async def ground_to_umls_node(state: GroundingState) -> GroundingState:
    """Use UMLS MCP server to ground extracted entities to concepts."""
    entities = state["extracted_entities"]
    grounded_entities = []

    # MCP client initialized with server connection
    mcp_client = get_mcp_client("umls-server")

    for entity in entities:
        # Call MCP tool: semantic_type_prediction
        semantic_type = await mcp_client.call_tool(
            "predict_semantic_type",
            {
                "mention_text": entity.text,
                "context": entity.context_window
            }
        )

        # Call MCP tool: concept_linking
        concepts = await mcp_client.call_tool(
            "link_to_umls",
            {
                "mention": entity.text,
                "semantic_types": [semantic_type],
                "top_k": 5
            }
        )

        grounded_entities.append({
            "original": entity,
            "semantic_type": semantic_type,
            "candidate_concepts": concepts,
            "confidence": concepts[0]["score"]
        })

    state["grounded_entities"] = grounded_entities
    return state
```

### Pattern 5: Separation of Extraction and Grounding Workflows

**What:** Split the pipeline into two independent LangGraph workflows: (1) Extraction workflow (agent-a) handles protocol ingestion and criteria extraction using Gemini's document understanding; (2) Grounding workflow (agent-b) processes extracted criteria to identify medical entities with MedGemma and ground them to UMLS concepts. Workflows communicate via events and shared data models.

**When to use:** When different steps require different AI models, have different performance characteristics, or need independent scaling. Extraction is I/O-bound (PDF processing, Gemini API calls); grounding is compute-bound (MedGemma inference, UMLS lookups). Decoupling allows each to scale independently and retry on failure without reprocessing the entire pipeline.

**Trade-offs:**
- **Pro:** Independent scaling and deployment; failure isolation (extraction succeeds even if grounding fails); clear responsibility boundaries; easier testing and debugging; supports parallel processing.
- **Con:** Increased operational complexity (two services); eventual consistency between workflows; requires event-based coordination; data must be persisted between stages.

**Example:**
```python
# Data flow between agents via events and shared database

# agent-a-service: Extraction completes
def queue_for_review_node(state: ExtractionState):
    # Save extracted criteria to DB
    criteria_batch = save_criteria(state["extracted_criteria"])

    # Publish event to trigger grounding workflow
    publish_event("criteria_extracted", {
        "batch_id": criteria_batch.id,
        "criteria_ids": [c.id for c in criteria_batch.criteria]
    })

    return state

# agent-b-service: Listens for criteria_extracted events
async def handle_criteria_extracted_event(event):
    # Load criteria from shared database
    criteria = load_criteria(event["criteria_ids"])

    # Start grounding workflow
    state = GroundingState(criteria=criteria)
    result = await grounding_graph.ainvoke(state)

    # Publish completion event for HITL UI
    publish_event("entities_grounded", {
        "batch_id": event["batch_id"],
        "entity_count": len(result["grounded_entities"])
    })
```

## Data Flow

### Request Flow: Protocol Upload to Extraction

```
[User uploads PDF in HITL UI]
    ↓
[React component calls api-service POST /protocols/upload]
    ↓
[api-service generates GCS signed URL]
    ↓
[Browser uploads PDF directly to GCS]
    ↓
[api-service creates Protocol record with gcs_path]
    ↓
[api-service publishes ProtocolUploaded event to outbox]
    ↓
[Outbox processor publishes to message broker]
    ↓
[agent-a-service receives event, starts extraction graph]
    ↓
[Ingest node: fetch PDF from GCS]
    ↓
[Extract node: Gemini API extracts criteria text]
    ↓
[Parse node: structure criteria into inclusion/exclusion]
    ↓
[Queue node: save CriteriaBatch with status=pending_review]
    ↓
[agent-a-service publishes CriteriaExtracted event]
    ↓
[HITL UI receives event via WebSocket, updates review queue]
```

### Request Flow: Criteria to Entity Grounding

```
[agent-b-service receives CriteriaExtracted event]
    ↓
[Load criteria batch from PostgreSQL]
    ↓
[Extract entities node: MedGemma NER on criteria text]
    ↓
[Ground to UMLS node: MCP server call for concept linking]
    ↓
[Map to SNOMED node: filter UMLS concepts to SNOMED-CT only]
    ↓
[Validate confidence node: flag low-confidence entities]
    ↓
[Persist entities with grounding metadata to DB]
    ↓
[Publish EntitiesGrounded event]
    ↓
[HITL UI displays entities with SNOMED codes for review]
```

### State Management: LangGraph Agent State

```
[LangGraph StateGraph manages workflow state]
    ↓
[State persisted to checkpoints after each node]
    ↓
[On failure: workflow resumes from last checkpoint]
    ↓
[State contains: protocol_id, extracted_criteria, entities, confidence_scores]
    ↓
[State flows through nodes, accumulating results]
    ↓
[Final state saved to PostgreSQL as structured records]
```

### Key Data Flows

1. **PDF Protocol Ingestion:** User uploads PDF → GCS storage → api-service creates Protocol record → event triggers agent-a extraction workflow → PDF fetched from GCS and processed by Gemini via Document AI → structured criteria saved to PostgreSQL.

2. **Criteria Extraction to Grounding:** agent-a completes extraction → publishes CriteriaExtracted event → agent-b loads criteria from DB → MedGemma extracts medical entities → UMLS MCP server grounds entities to SNOMED concepts → entities saved to DB with confidence scores.

3. **HITL Review and Approval:** Clinical researcher opens HITL UI → views CriteriaBatch with status=pending_review → edits criteria text, approves grounded entities → api-service updates status to approved → publishes ReviewCompleted event → downstream systems can use approved data.

4. **Event-Driven Coordination:** All inter-service communication is event-driven via outbox pattern → api-service persists entity changes and events atomically → outbox processor publishes to message broker → agent services subscribe to relevant events → enables async processing, retry logic, and horizontal scaling.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 0-100 protocols/month | Single Cloud Run instance per service; Cloud SQL PostgreSQL (small instance); GCS standard storage; synchronous MCP calls; single HITL reviewer. |
| 100-1000 protocols/month | Auto-scaling Cloud Run (min 1, max 5 per service); Cloud SQL HA with read replicas; GCS with signed URL caching; MCP server connection pooling; multiple HITL reviewers with assignment queue; implement Redis for event deduplication. |
| 1000+ protocols/month | Horizontal scaling for agent services (Cloud Run max instances 20+); Cloud SQL largest instance or Cloud Spanner; batch processing for grounding workflow (process multiple criteria in parallel); MCP server cluster with load balancer; dedicated review queue service; implement Cloud Pub/Sub for event bus; consider caching extracted criteria embeddings for similarity search. |

### Scaling Priorities

1. **First bottleneck:** Gemini API rate limits and Document AI processing time. **Fix:** Implement request queuing with exponential backoff; batch multiple criteria extractions per protocol; cache extracted criteria for similar protocols; use Gemini 2.0 Flash for lower latency.

2. **Second bottleneck:** MedGemma inference latency for large criteria sets. **Fix:** Deploy MedGemma on GPU-enabled Cloud Run or Vertex AI with auto-scaling; batch entity extraction across multiple criteria; implement entity extraction caching (criteria text hash → entities); pre-warm model instances during low traffic.

3. **Third bottleneck:** UMLS MCP server lookup latency for high-frequency entities. **Fix:** Implement concept grounding cache (entity text + context → UMLS concepts); deploy MCP server replicas with consistent hashing; consider pre-computing grounding for common medical terms; use UMLS semantic type prediction to reduce candidate space.

4. **Fourth bottleneck:** PostgreSQL write contention from concurrent agent workflows. **Fix:** Use connection pooling with PgBouncer; partition outbox table by event_type; implement write-through caching for frequently accessed entities; consider read replicas for HITL UI queries; use PostgreSQL's JSONB indexing for criteria search.

## Anti-Patterns

### Anti-Pattern 1: Synchronous Agent Invocation from API Endpoints

**What people do:** api-service directly calls LangGraph agent workflows synchronously in the request handler, waiting for completion before returning response to client.

**Why it's wrong:** Extraction and grounding workflows can take 10-60 seconds. This blocks the API worker, exhausts connection pool, and causes HTTP timeouts. Users see loading spinners for minutes. Services can't scale independently.

**Do this instead:** Use event-driven async architecture. api-service accepts upload, returns 202 Accepted with task ID immediately. Publishes event to message broker. Agent services process asynchronously. Client polls status endpoint or receives WebSocket updates. HITL UI shows "Processing..." state with progress updates.

### Anti-Pattern 2: Storing PDFs in PostgreSQL

**What people do:** Save PDF binary data in PostgreSQL BYTEA column alongside Protocol metadata.

**Why it's wrong:** PostgreSQL is optimized for structured queries, not blob storage. Large PDFs bloat database size, slow backups, increase replication lag, and exhaust memory during queries. No support for streaming, partial reads, or CDN distribution.

**Do this instead:** Store PDFs in GCS (designed for blob storage). Save only GCS object path in PostgreSQL. Use signed URLs for time-limited access. Benefits: cheap storage, fast uploads, CDN support, no database impact, automatic versioning, and lifecycle management.

### Anti-Pattern 3: Monolithic LangGraph Workflow

**What people do:** Create single giant LangGraph workflow: ingest → extract → ground → validate → queue for review, all in one StateGraph across both agent services.

**Why it's wrong:** Tight coupling makes testing hard. One failure (e.g., UMLS server down) fails entire pipeline. Can't scale extraction and grounding independently. Reprocessing a grounding failure requires re-running expensive extraction. State management becomes complex.

**Do this instead:** Split into two LangGraph workflows: extraction (agent-a) and grounding (agent-b). Communicate via events and shared database. Each workflow has clear inputs/outputs. Test independently. Scale independently. Retry grounding without re-extracting. Enables parallel processing of multiple protocols.

### Anti-Pattern 4: Embedding UMLS Lookups in Agent Code

**What people do:** Hardcode UMLS database queries or API calls directly in agent node functions. Load UMLS dictionaries into memory. Implement custom concept matching logic.

**Why it's wrong:** UMLS updates quarterly (new concepts, deprecated codes). Agent redeployment required for each update. Concept matching logic duplicated across agents. No centralized caching. Difficult to test without full UMLS database.

**Do this instead:** Use MCP server to abstract UMLS access. Server handles ontology updates, caching, and semantic search. Agents call standardized MCP tools. Benefits: versioning, performance tuning, reusability, testability (mock MCP responses).

### Anti-Pattern 5: Missing Confidence Thresholds and Fallback Paths

**What people do:** Trust all AI outputs equally. Directly save extracted criteria and grounded entities to database without confidence scoring. Assume Gemini/MedGemma/UMLS never make mistakes.

**Why it's wrong:** AI models are probabilistic. Low-confidence extractions are often errors (OCR mistakes, ambiguous criteria). Blindly trusting outputs leads to incorrect medical concept mappings. Clinical researchers waste time reviewing obvious mistakes. No automated quality filtering.

**Do this instead:** Every extraction and grounding step produces confidence scores. Set thresholds: high confidence (auto-approve), medium (standard HITL review), low (flag for expert review or automatic rejection). Implement validation nodes in LangGraph workflows. Example: if extraction confidence < 0.7, trigger human-assisted extraction instead of auto-queuing.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| **Gemini API** | Direct HTTP calls via Vertex AI SDK | Use Gemini 2.0 Flash for document understanding; structured output for criteria extraction; handle rate limits with exponential backoff; cache results by protocol hash |
| **MedGemma (Hugging Face)** | Local inference via transformers library | Load MedGemma-1.5-4b-it model; GPU required for reasonable latency; batch entity extraction for efficiency; consider Vertex AI Prediction for managed deployment |
| **UMLS MCP Server** | MCP client SDK | Custom-deployed MCP server exposing UMLS Metathesaurus; tools: concept_search, semantic_type_prediction, concept_relationship; requires UMLS license |
| **Google Cloud Storage** | GCS client SDK | Signed URLs for browser uploads; service account for agent access; versioning enabled; lifecycle rules for old protocols; CORS configured for hitl-ui |
| **Document AI** | Vertex AI Document AI API | OCR processing for PDF protocols; layout analysis for table extraction; form parser for structured sections; integrates with Gemini for downstream analysis |
| **Google OAuth** | OAuth 2.0 PKCE flow | Authentication for clinical researchers; Google Workspace integration; role-based access control (RBAC) for review permissions; session management in api-service |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| **hitl-ui ↔ api-service** | REST API + WebSockets | OpenAPI-generated TypeScript client; WebSocket for real-time updates (review queue notifications); JWT auth on all endpoints; CORS configured |
| **api-service ↔ agent-a-service** | Event bus (Cloud Pub/Sub) | api-service publishes ProtocolUploaded; agent-a subscribes; acknowledges after processing; retries on transient failures; dead-letter queue for errors |
| **api-service ↔ agent-b-service** | Event bus (Cloud Pub/Sub) | api-service publishes CriteriaExtracted; agent-b subscribes; acknowledges after grounding; retries on transient failures |
| **agent-a ↔ agent-b** | Shared PostgreSQL + events | agent-a writes CriteriaBatch; publishes event; agent-b reads from DB; writes Entity records; publishes completion event; eventual consistency |
| **agent-b-service ↔ UMLS MCP Server** | MCP protocol over HTTP | agent-b as MCP client; server as separate deployment; connection pooling; timeout handling; fallback to cached results on failure |
| **All services ↔ PostgreSQL** | SQLModel ORM | Connection pooling via SQLAlchemy; read replicas for queries; write to primary; transactional outbox for events; Alembic for migrations |

## Build Order and Dependencies

### Phase 1: Core Infrastructure and Data Models (Week 1)

**Dependencies:** None
**Build:**
1. `libs/shared/models.py`: SQLModel schemas (Protocol, Criteria, Entity, Review, OutboxEvent)
2. `libs/events-py/models.py`: Event definitions (ProtocolUploaded, CriteriaExtracted, etc.)
3. `services/api-service`: FastAPI skeleton with health endpoints, PostgreSQL setup, Alembic migrations
4. `infra/docker-compose.yml`: Local PostgreSQL, basic networking

**Rationale:** Establish data contracts first. All services depend on shared models. Database migrations must run before any service starts. This phase is the foundation.

**Testing:** Unit tests for model validation; integration test for database connection.

---

### Phase 2: Protocol Upload and Storage (Week 1-2)

**Dependencies:** Phase 1 (api-service, shared models)
**Build:**
1. `services/api-service/routers/protocols.py`: POST /protocols/upload (signed URL generation), GET /protocols
2. `services/api-service/services/gcs.py`: GCS client, signed URL generation, bucket creation
3. `apps/hitl-ui`: Basic React scaffold with upload form, GCS direct upload

**Rationale:** User entry point into the system. Can't extract criteria without protocols. GCS integration is isolated (no AI dependencies), making it a good early milestone.

**Testing:** E2E test: upload PDF → verify in GCS → Protocol record in DB.

---

### Phase 3: Extraction Workflow (agent-a) (Week 2-3)

**Dependencies:** Phase 2 (protocols exist), Phase 1 (events, models)
**Build:**
1. `libs/inference/loaders.py`: Gemini client initialization, Document AI setup
2. `services/agent-a-service/graph.py`: LangGraph workflow (ingest, extract, queue)
3. `services/agent-a-service/nodes.py`: Node implementations (GCS fetch, Gemini extraction)
4. `services/agent-a-service/state.py`: ExtractionState with protocol, criteria
5. `services/api-service`: Event publishing for ProtocolUploaded
6. `services/agent-a-service`: Event subscription, workflow invocation

**Rationale:** Core value proposition. Extraction workflow is independent of grounding. Can deliver value (structured criteria) before entity grounding is built.

**Testing:** Integration test: publish event → agent-a extracts → CriteriaBatch saved. Mock Gemini responses.

---

### Phase 4: HITL Review UI (Week 3-4)

**Dependencies:** Phase 3 (extraction produces CriteriaBatch)
**Build:**
1. `services/api-service/routers/criteria.py`: GET /criteria (list batches), PATCH /criteria/:id (edit)
2. `services/api-service/routers/reviews.py`: POST /reviews/:batch_id/approve
3. `apps/hitl-ui/pages/CriteriaReview.tsx`: Review queue, editable criteria cards
4. `apps/hitl-ui/components/CriteriaCard.tsx`: Display/edit component
5. WebSocket integration for real-time updates

**Rationale:** Enables human validation of extracted criteria before grounding. Provides immediate user value (review and correct AI extractions). Critical for HITL workflow.

**Testing:** E2E test: upload protocol → extraction completes → review appears in UI → edit and approve.

---

### Phase 5: Grounding Workflow (agent-b) and UMLS MCP (Week 4-5)

**Dependencies:** Phase 3 (CriteriaBatch exists), Phase 1 (Entity model)
**Build:**
1. UMLS MCP Server: Deploy custom MCP server with UMLS Metathesaurus access
2. `libs/inference/loaders.py`: MedGemma model loader, MCP client initialization
3. `services/agent-b-service/graph.py`: LangGraph workflow (extract entities, ground, map)
4. `services/agent-b-service/nodes.py`: MedGemma NER, UMLS grounding, SNOMED mapping
5. `services/agent-b-service/state.py`: GroundingState with entities, mappings
6. `services/api-service`: Event publishing for CriteriaExtracted
7. `services/agent-b-service`: Event subscription, workflow invocation

**Rationale:** Grounding workflow is separate from extraction. Requires MedGemma deployment (compute-intensive) and UMLS MCP server (external dependency). Can start after extraction proves valuable.

**Testing:** Integration test: publish CriteriaExtracted → agent-b grounds → Entity records saved. Mock MCP responses.

---

### Phase 6: Entity Approval UI (Week 5-6)

**Dependencies:** Phase 5 (grounding produces Entity), Phase 4 (HITL UI exists)
**Build:**
1. `services/api-service/routers/entities.py`: GET /entities, PATCH /entities/:id
2. `apps/hitl-ui/pages/EntityApproval.tsx`: Entity list, SNOMED badge display
3. `apps/hitl-ui/components/EntityTag.tsx`: Entity with concept info, confidence badge
4. `apps/hitl-ui/components/ApprovalWorkflow.tsx`: Bulk approve/reject

**Rationale:** Closes the loop on HITL workflow. Clinical researchers validate SNOMED mappings. Feedback enables model improvement.

**Testing:** E2E test: grounding completes → entities appear in UI → approve entities → status updated.

---

### Phase 7: Production Hardening (Week 6-7)

**Dependencies:** All previous phases
**Build:**
1. Implement retry logic with exponential backoff
2. Dead-letter queues for failed events
3. Observability: structured logging, Cloud Trace, error tracking
4. Performance optimization: caching (criteria, entities, MCP results), connection pooling
5. Security: input validation, rate limiting, API key rotation
6. Terraform: GCP infrastructure as code (Cloud Run, Cloud SQL, GCS, Pub/sub)

**Rationale:** System works end-to-end, now make it production-ready. Observability is critical for debugging distributed workflows. Caching reduces costs and latency.

**Testing:** Load testing (100 concurrent uploads), chaos testing (kill agent services mid-workflow), security scan.

---

## Dependency Graph

```
Phase 1 (Infrastructure)
    ↓
Phase 2 (Protocol Upload) ───┬──→ Phase 3 (Extraction)
    │                         │          ↓
    └─────────────────────────┼──→ Phase 4 (Review UI)
                              │          ↓
                              └──→ Phase 5 (Grounding)
                                         ↓
                                    Phase 6 (Entity Approval)
                                         ↓
                                    Phase 7 (Hardening)
```

**Critical Path:** 1 → 2 → 3 → 4 → 5 → 6 → 7 (linear dependencies)
**Parallel Work:** Phase 2 and 3 can partially overlap (GCS integration independent of Gemini integration)

---

## Sources

**LangGraph Architecture:**
- [LangGraph: Agent Orchestration Framework for Reliable AI Agents](https://www.langchain.com/langgraph)
- [LangGraph Multi-Agent Orchestration: Complete Framework Guide](https://latenode.com/blog/ai-frameworks-technical-infrastructure/langgraph-multi-agent-orchestration/langgraph-multi-agent-orchestration-complete-framework-guide-architecture-analysis-2025)
- [Multi-agent system using Elasticsearch and LangGraph](https://www.elastic.co/search-labs/blog/multi-agent-system-llm-agents-elasticsearch-langgraph)
- [Agent Orchestration 2026: LangGraph, CrewAI & AutoGen Guide](https://iterathon.tech/blog/ai-agent-orchestration-frameworks-2026)

**Clinical Trial Protocol Extraction:**
- [Streamline protocol design with AI in clinical trials](https://www.pwc.com/us/en/technology/alliances/amazon-web-services/healthcare-intelligent-automation-platform/intelligent-clinical-trial.html)
- [Augmenting the clinical trial design process with information extraction](https://snorkel.ai/blog/augmenting-the-clinical-trial-design-information-extraction/)
- [Accelerating clinical evidence synthesis with large language models](https://www.nature.com/articles/s41746-025-01840-7)

**HITL Workflows:**
- [Rethinking 'human in the loop' as AI scales across healthcare](https://www.mobihealthnews.com/news/rethinking-human-loop-ai-scales-across-healthcare)
- [Human-in-the-Loop AI (HITL) - Complete Guide 2026](https://parseur.com/blog/human-in-the-loop-ai)
- [Human-in-the-Loop (HitL) Agentic AI for High-Stakes Oversight 2026](https://onereach.ai/blog/human-in-the-loop-agentic-ai-systems/)

**Medical Entity Grounding:**
- [Snomed to UMLS Code Mapping](https://nlp.johnsnowlabs.com/2021/07/01/snomed_umls_mapping_en.html)
- [MedCAT: Medical Concept Annotation Tool](https://github.com/CogStack/MedCAT)
- [Improving broad-coverage medical entity linking with semantic type prediction](https://pmc.ncbi.nlm.nih.gov/articles/PMC8952339/)

**Microservices and Event-Driven Architecture:**
- [Event-Driven Architecture and Microservices Best Practices](https://developer.ibm.com/articles/eda-and-microservices-architecture-best-practices/)
- [Architectural Showdown: Microservices vs. Event-Driven Architecture in Healthcare](https://avisari.medium.com/architectural-showdown-microservices-vs-event-driven-architecture-in-healthcare-data-management-d654c9e9e0df)
- [Event Sourcing with PostgreSQL](https://microservices.io/patterns/data/event-sourcing.html)

**Gemini and MedGemma:**
- [Gemini Document Understanding](https://ai.google.dev/gemini-api/docs/document-processing)
- [Extracting structured data from PDFs using Gemini 2.0](https://peterfriese.dev/blog/2025/gemini-genkit-pdf-structured-data/)
- [MedGemma Technical Documentation](https://developers.google.com/health-ai-developer-foundations/medgemma)
- [MedGemma 1.5 Model Card](https://developers.google.com/health-ai-developer-foundations/medgemma/model-card)

**Google Cloud Platform:**
- [Build a document processing pipeline with Workflows](https://cloud.google.com/document-ai/docs/workflows)
- [Medical Text Processing with Healthcare Natural Language API](https://cloud.google.com/blog/topics/healthcare-life-sciences/medical-text-processing-on-google-cloud/)

---

*Architecture research for: Clinical Trial Protocol Criteria Extraction System*
*Researched: 2026-02-10*
