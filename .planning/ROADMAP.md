# Roadmap: Clinical Trial Criteria Extraction System

## Milestones

- ✅ **v1.0 Core Pipeline** - Phases 1-7 (shipped 2026-02-12)
- 🚧 **v1.1 Documentation Site** - Phases 8-12 (paused after Phase 10)
- 🚧 **v1.2 GCP Cloud Run Deployment** - Phases 13-15 (paused)
- ✅ **v1.3 Multimodal PDF Extraction** - Phase 16 (shipped 2026-02-12)

## Phases

<details>
<summary>✅ v1.0 Core Pipeline (Phases 1-7) - SHIPPED 2026-02-12</summary>

### Phase 1: Infrastructure & Data Models
**Goal**: All services share consistent data contracts, the database is migrations-ready, and local development runs with a single command
**Depends on**: Nothing (first phase)
**Requirements**: REQ-01.1, REQ-01.2, REQ-01.3
**Success Criteria** (what must be TRUE):
  1. SQLModel classes for Protocol, Criteria, CriteriaBatch, Entity, Review, AuditLog, and OutboxEvent exist in shared models with created_at/updated_at timestamps and JSONB fields
  2. Alembic migrations auto-generate from SQLModel metadata and apply cleanly to a fresh PostgreSQL database
  3. Event types (ProtocolUploaded, CriteriaExtracted, ReviewCompleted, EntitiesGrounded) are defined with outbox persistence pattern
  4. `docker compose up` starts PostgreSQL with persistent volume and all three services pass health checks
**Plans**: 2 plans

Plans:
- [x] 01-01: Domain SQLModel classes, event types, and Alembic migration
- [x] 01-02: Outbox processor, Dockerfiles, and Docker Compose infrastructure

### Phase 2: Protocol Upload & Storage
**Goal**: Clinical researchers can upload protocol PDFs through the UI and see them listed with status tracking and quality scores
**Depends on**: Phase 1
**Requirements**: REQ-02.1, REQ-02.2, REQ-02.3
**Success Criteria** (what must be TRUE):
  1. User can upload a PDF through the HITL UI, which uploads directly to GCS via signed URL (no server-side proxy), and sees the protocol appear in a list
  2. Protocol list displays paginated results with status badges (uploaded, extracting, extracted, reviewed) served from server-side pagination
  3. PDF quality score is computed on upload (text extractability, page count, encoding type), stored in GCS metadata, and visible in protocol detail view
  4. Upload rejects non-PDF files and files exceeding 50MB with clear error messages
**Plans**: 2 plans

Plans:
- [x] 02-01: Backend API: GCS signed URL upload, PDF quality analyzer, paginated list and detail endpoints
- [x] 02-02: Frontend UI: Upload dialog, paginated protocol list with status badges, detail view with quality scores

### Phase 3: Criteria Extraction Workflow
**Goal**: Uploaded protocols are automatically processed by extraction-service to extract structured inclusion/exclusion criteria with temporal constraints, assertion status, and confidence scores
**Depends on**: Phase 2
**Requirements**: REQ-03.1, REQ-03.2, REQ-03.3, REQ-03.4
**Success Criteria** (what must be TRUE):
  1. When a protocol is uploaded, extraction-service automatically extracts criteria and creates a CriteriaBatch with status=pending_review within 5 minutes
  2. Each extracted criterion has structured fields: text, type (inclusion/exclusion), category, temporal_constraint, conditions, numeric_thresholds, assertion status (PRESENT/ABSENT/HYPOTHETICAL/HISTORICAL/CONDITIONAL), and confidence score (0.0-1.0)
  3. PDF parsing via pymupdf4llm preserves tables and multi-column layouts, with parsed content cached to avoid re-parsing
  4. CriteriaExtracted event is published via outbox pattern and grounding-service can subscribe to it
**Plans**: 2 plans

Plans:
- [x] 03-01: Extraction foundation: ExtractionState, Pydantic schemas, PDF parser with caching, Jinja2 prompts, trigger handler
- [x] 03-02: Graph nodes and integration: 4 LangGraph nodes (ingest/extract/parse/queue), graph assembly, outbox handler registration, verification

### Phase 4: HITL Review UI
**Goal**: Clinical researchers can efficiently review AI-extracted criteria with side-by-side PDF comparison, edit individual criteria, and maintain a complete audit trail
**Depends on**: Phase 3
**Requirements**: REQ-04.1, REQ-04.2, REQ-04.3, REQ-04.4
**Success Criteria** (what must be TRUE):
  1. Reviewer sees a queue of pending CriteriaBatches and can approve, reject, or modify each criterion individually (not all-or-nothing), with partial progress saved across sessions
  2. Split-screen view shows original protocol PDF (left panel with page navigation, loaded via GCS signed URL) alongside extracted criteria cards (right panel)
  3. Each criterion displays a confidence badge (high/medium/low with configurable thresholds), criteria are sortable by confidence (lowest first), and low-confidence items are visually highlighted
  4. Every review action (approve/reject/modify) is logged with reviewer_id, timestamp, action type, and before/after values, queryable via API with 100% completeness
**Plans**: 2 plans

Plans:
- [x] 04-01: Review API endpoints (batch list, criteria, review actions, PDF URL, audit log) + frontend TanStack Query hooks
- [x] 04-02: Review UI: split-screen PDF viewer + criteria cards with confidence badges, review queue, route wiring

### Phase 5: Entity Grounding Workflow
**Goal**: Extracted criteria are automatically processed by grounding-service to identify medical entities via MedGemma and ground them to UMLS/SNOMED concepts via the MCP server, with tiered fallback for coverage gaps
**Depends on**: Phase 3 (needs CriteriaBatch data and CriteriaExtracted events)
**Requirements**: REQ-05.1, REQ-05.2, REQ-05.3
**Success Criteria** (what must be TRUE):
  1. grounding-service automatically processes criteria when CriteriaExtracted event fires, extracting medical entities (Condition, Medication, Procedure, Lab_Value, Demographic, Biomarker) with span positions and context windows
  2. Every extracted entity is grounded to UMLS CUI and SNOMED-CT code via the MCP server, with every generated code validated against the UMLS API before database storage
  3. Tiered grounding strategy works: exact match first, then semantic similarity, then routed to expert review queue -- failed grounding stores free-text plus nearest neighbor without blocking the pipeline
  4. EntitiesGrounded event is published on completion, and each grounding has a confidence score (0.0-1.0)
**Plans**: 3 plans

Plans:
- [x] 05-01: UMLS MCP server with FastMCP: concept_search, concept_linking, semantic_type_prediction tools + UMLS REST API client with mock fallback
- [x] 05-02: Agent-b foundation: GroundingState TypedDict, Pydantic entity schemas, Jinja2 extraction prompts, CriteriaExtracted trigger handler, UMLS validation client
- [x] 05-03: Grounding graph nodes and integration: 4 LangGraph nodes (extract_entities/ground_to_umls/map_to_snomed/validate_confidence), graph assembly, outbox handler registration

### Phase 5.1: Error Handling Hardening (INSERTED)
**Goal**: All services fail loudly when dependencies are missing — no mock fallbacks, no silent error swallowing, no graceful degradation that hides real failures
**Depends on**: Phase 5 (gap closure for Phases 1-5)
**Success Criteria** (what must be TRUE):
  1. GCS operations raise ValueError when GCS_BUCKET_NAME is not set instead of returning localhost mock URLs, and the /mock-upload endpoint is removed
  2. DATABASE_URL raises ValueError when not set instead of defaulting to SQLite
  3. UMLS API client methods (search, get_concept, get_snomed_code) propagate exceptions instead of returning empty values — callers can distinguish API failure from empty results
  4. ground_to_umls uses only the MCP server path — no silent fallback to direct client
  5. All 3 mypy errors in ground_to_umls.py are fixed and `uv run mypy .` passes clean
  6. `uv run ruff check .` passes clean
**Plans**: 1 plan

Plans:
- [x] 05.1-01: Remove GCS mock fallback, fix UMLS error swallowing, remove MCP fallback, fix mypy errors

### Phase 5.2: Test Coverage (INSERTED)
**Goal**: Every service and library has real functional tests — boilerplate/example tests removed, critical business logic covered
**Depends on**: Phase 5.1 (error handling fixed first, then test the correct behavior)
**Success Criteria** (what must be TRUE):
  1. All 86 boilerplate/example tests removed (test_example_unit.py, test_example_integration.py, test_example_mocking.py) and replaced with real tests
  2. api-service has integration tests for all 9 production endpoints (4 protocol + 5 review) using TestClient
  3. Unit tests exist for: Pydantic schemas (criteria + entity), quality scoring algorithm, shared SQLModel models, UMLS clients, outbox processor
  4. Agent graph tests with mocked LLMs verify: extraction-service extraction graph compiles and routes, grounding-service grounding graph compiles and routes
  5. `uv run pytest` passes with zero skipped tests (all stale skips removed or fixed)
  6. All tests test REAL project code, not dummy functions
  7. UMLS client rewritten with production patterns: exception hierarchy, disk caching, retry, SnomedCandidate dataclass
**Plans**: 3 plans

Plans:
- [x] 05.2-01: Remove boilerplate tests, add unit tests for schemas, models, quality scoring, UMLS clients, outbox processor
- [x] 05.2-02: Rewrite UMLS client with production patterns: exception hierarchy, disk caching, retry, SnomedCandidate dataclass
- [x] 05.2-03: Add API integration tests for protocol + review endpoints, agent graph compilation tests

### Phase 5.3: Rename Services and Docs to Implementation Names (INSERTED)
**Goal**: All services, libs, and apps use implementation-domain names and descriptions; no template placeholders (e.g. "agent-a", "agent-b", "guest interaction", "guardrailing") in code, config, or docs
**Depends on**: Phase 5.2
**Success Criteria** (what must be TRUE):
  1. Directory `services/agent-a-service` renamed to `services/extraction-service`; Python package `agent_a_service` renamed to `extraction_service`; all imports and references updated (api-service, pyproject, docker-compose, CI, mkdocs, READMEs)
  2. Directory `services/agent-b-service` renamed to `services/grounding-service`; Python package `agent_b_service` renamed to `grounding_service`; all imports and references updated
  3. Docs (components-overview.md, PROJECT_OVERVIEW.md, onboarding.md, testing-guide.md, copilot-instructions.md, ROADMAP.md, per-service READMEs) use "extraction-service" / "grounding-service" and correct descriptions (criteria extraction, UMLS grounding) — no "agent-a", "agent-b", "guest interaction", or "guardrailing"
  4. `uv run pytest` and CI pass after renames; no broken imports or paths
**Plans**: 3 plans

Plans:
- [x] 05.3-01: Rename agent-a-service to extraction-service (dir, package, all refs)
- [x] 05.3-02: Rename agent-b-service to grounding-service (dir, package, all refs)
- [x] 05.3-03: Update all documentation and config to implementation names and descriptions

### Phase 6: Entity Approval, Auth & Search
**Goal**: Clinical researchers can authenticate, validate grounded entities with SNOMED codes, and search across criteria -- completing the full end-to-end HITL workflow
**Depends on**: Phase 4 (HITL UI exists), Phase 5 (grounded entities exist)
**Requirements**: REQ-05.4, REQ-06.1, REQ-07.1
**Success Criteria** (what must be TRUE):
  1. Researcher logs in via Google OAuth, receives a JWT, and all API endpoints require valid authentication
  2. Entity list view displays SNOMED badge (code + preferred term) with human-readable labels, and researcher can approve, reject, or modify each entity mapping individually
  3. Full-text search via GET /criteria/search?q= returns relevance-ranked results with filters for protocol, criteria type, and approval status, backed by GIN index on criteria text
**Plans**: 2 plans

Plans:
- [x] 06-01: Backend: Google OAuth + JWT auth, entity approval endpoints, full-text search with GIN index
- [x] 06-02: Frontend: Auth flow + entity approval UI with SNOMED badges + search page with filters

### Phase 7: Production Hardening
**Goal**: The end-to-end pipeline achieves target reliability and performance metrics for the 50-protocol pilot
**Depends on**: Phase 6 (complete pipeline exists)
**Requirements**: REQ-08.1, REQ-08.2
**Success Criteria** (what must be TRUE):
  1. All external API calls (Gemini, Vertex AI, UMLS MCP, GCS) use tenacity retry with exponential backoff (max 3 retries) and circuit breaker for sustained failures, with structured logging for retry events
  2. Pipeline achieves >95% success rate from upload to criteria extraction, with failed extractions surfacing to the user with actionable error messages and dead-letter handling for unrecoverable failures
  3. Average processing time per protocol is <5 minutes end-to-end
**Plans**: 4 plans

Plans:
- [x] 07-01: Protocol status enum, dead-letter handling, retry endpoint
- [x] 07-02: Retry decorators and circuit breakers on all external services
- [x] 07-03: MLflow instrumentation: autolog, request middleware, circuit breaker events, HITL tracing
- [x] 07-04: Frontend error surfacing with failure badges, error reasons, and retry button

</details>

<details>
<summary>🚧 v1.1 Documentation Site (Phases 8-12) - PAUSED after Phase 10</summary>

**Milestone Goal:** Comprehensive MkDocs documentation that bridges high-level intent and low-level code, making the system accessible to engineers, PMs, and clinical researchers.

### Phase 8: Documentation Foundation
**Goal**: MkDocs configuration with native Mermaid.js, navigation structure, and CI quality gates
**Depends on**: Nothing (documentation-only milestone)
**Requirements**: INFRA-01, INFRA-02, INFRA-03
**Success Criteria** (what must be TRUE):
  1. MkDocs builds in strict mode with zero warnings
  2. Native Mermaid.js diagrams render correctly in light and dark mode via pymdownx.superfences
  3. Documentation site navigation includes all 6 sections (architecture, journeys, components, status, code-tour, diagrams) with correct hierarchy
  4. CI pipeline validates Markdown links and fails on broken references
  5. Documentation preview deploys on PRs touching docs/ directory
**Plans**: 2 plans

Plans:
- [x] 08-01: Modernize mkdocs.yml: replace mermaid2 with native superfences, enable strict mode + validation, fix template metadata
- [x] 08-02: Create 6-section navigation structure with placeholder pages, add CI documentation validation job

### Phase 9: System Architecture & Data Models
**Goal**: C4 diagrams showing system structure plus database schema and LangGraph state documentation
**Depends on**: Phase 8
**Requirements**: ARCH-01, ARCH-02, DATA-01, DATA-02
**Success Criteria** (what must be TRUE):
  1. Engineer can view C4 Container diagram showing React UI, FastAPI, PostgreSQL, LangGraph agents, and FastMCP interactions
  2. Engineer can reference wiring diagram explaining REST for frontend-backend and transactional outbox for event-driven agent triggers
  3. Engineer can reference DB schema ER diagram showing Protocol, Criteria, CriteriaBatch, Entity, Review, AuditLog tables with relationships
  4. Engineer can reference LangGraph state documentation showing ExtractionState and GroundingState TypedDict structures with field descriptions and data flow
  5. All diagrams include date_verified frontmatter metadata
**Plans**: 2 plans

Plans:
- [x] 09-01: System architecture: C4 Container diagram + service communication wiring section
- [x] 09-02: Data models: database schema ER diagram + LangGraph state documentation

### Phase 10: User Journey Narratives
**Goal**: Sequence diagrams showing upload-extraction and grounding-review workflows with narrative explanations
**Depends on**: Phase 9
**Requirements**: JOUR-01, JOUR-02
**Success Criteria** (what must be TRUE):
  1. PM can view "Upload & Extraction" sequence diagram showing Researcher to HITL UI to API to GCS to Outbox to Extraction Service to DB flow
  2. PM can view "Grounding & HITL Review" sequence diagram showing CriteriaExtracted to Grounding Service to DB to HITL UI to Approval to Audit Log flow
  3. Each journey narrative explains the user story and runtime behavior
  4. Diagrams explicitly note "happy path only" and link to error handling documentation
**Plans**: 2 plans

Plans:
- [x] 10-01: Upload & Extraction journey with sequence diagram, narrative, navigation updates, and grounding-review placeholder
- [x] 10-02: Grounding & HITL Review journey with sequence diagram and narrative

### Phase 11: Component Deep Dives
**Goal**: Per-service engineering manual documenting responsibilities, key abstractions, configuration, and environment variables
**Depends on**: Phase 10
**Requirements**: COMP-01, COMP-02, COMP-03, COMP-04
**Success Criteria** (what must be TRUE):
  1. Engineer can reference api-service.md showing responsibilities, key endpoints, configuration, and environment variables
  2. Engineer can reference extraction-service.md showing LangGraph graph nodes, PDF parsing, Gemini integration, and configuration
  3. Engineer can reference grounding-service.md showing MedGemma integration, UMLS MCP tools, grounding strategy, and configuration
  4. Engineer can reference hitl-ui.md showing React component structure, state management (TanStack Query + Zustand), key screens, and hooks
  5. All component docs cross-reference architecture diagrams and user journeys
**Plans**: TBD (paused)

Plans:
- [ ] 11-01: TBD

### Phase 12: Implementation Status & Code Tour
**Goal**: Feature status report with test coverage analysis plus narrative code walkthrough from upload to review
**Depends on**: Phase 11
**Requirements**: STAT-01, STAT-02, TOUR-01, TOUR-02
**Success Criteria** (what must be TRUE):
  1. Stakeholder can view feature status table marking each feature as Stable, Beta, or Stubbed
  2. Stakeholder can view test coverage analysis comparing src vs tests across all services
  3. New engineer can follow code tour walkthrough showing 5+ "slides" following protocol lifecycle from upload to review
  4. Each code tour slide includes: title, user story, code location (file path, no line numbers), relevant code snippet, and "why this matters" explanation
  5. Code tour uses reference strategy preventing drift (function names not line numbers, automated link checking)
**Plans**: TBD (paused)

Plans:
- [ ] 12-01: TBD

</details>

## 🚀 v1.2 GCP Cloud Run Deployment (Current)

**Milestone Goal:** Deploy the entire application to Google Cloud Run using Terraform, with all configuration consumed from .env file and documented .env.example for operators. This is a lean 50-protocol pilot deployment — prioritize simplicity over enterprise patterns.

### Phase 13: Terraform Foundation
**Goal**: Terraform backend, GCP APIs, Artifact Registry, and IAM service accounts are provisioned — establishing the foundation for all Cloud Run resources
**Depends on**: Nothing (first phase of v1.2)
**Requirements**: TF-01, TF-02, SEC-02, REG-01
**Success Criteria** (what must be TRUE):
  1. Operator can run `terraform init` from `infra/terraform/` and Terraform connects to GCS backend with automatic state locking enabled
  2. All required GCP APIs (Cloud Run, Cloud SQL, Secret Manager, VPC Access, Artifact Registry) are enabled via Terraform with explicit dependencies
  3. Artifact Registry repository for Docker images exists and accepts image pushes from authenticated clients
  4. Four IAM service accounts (api-service, extraction-service, grounding-service, hitl-ui) are created with predefined roles (cloudsql.client, secretmanager.secretAccessor) assigned
  5. Terraform uses region variable pattern (single source of truth for us-central1) preventing VPC connector region mismatches

**Plans**: TBD

Plans:
- [ ] 13-01: TBD

### Phase 14: Cloud SQL, Networking & Container Registry
**Goal**: Private Cloud SQL PostgreSQL instance, VPC networking with Serverless Connector, Secret Manager integration, and container images in Artifact Registry are deployed — enabling Cloud Run services to connect to database and secrets securely
**Depends on**: Phase 13
**Requirements**: DB-01, DB-02, SEC-01, REG-02
**Success Criteria** (what must be TRUE):
  1. Cloud SQL PostgreSQL 16 instance is provisioned with private IP only (no public IP) and VPC peering to the default network
  2. VPC Serverless Connector (10.8.0.0/28 subnet) enables Cloud Run services to access Cloud SQL via private IP with explicit Terraform dependencies preventing race conditions
  3. Secret Manager stores all sensitive configuration (DATABASE_URL, UMLS_API_KEY, Google OAuth client ID/secret) with service account IAM bindings for secretAccessor role
  4. Build script (`scripts/build-and-push.sh`) builds all 4 Docker images, pushes to Artifact Registry, and captures SHA256 digests for Terraform consumption
  5. Connection pool configuration is documented (pool_size=2, max_overflow=1) and max_connections on Cloud SQL set to 100

**Plans**: TBD

Plans:
- [ ] 14-01: TBD

### Phase 15: Cloud Run Deployment & Documentation
**Goal**: All four services deploy to Cloud Run with health checks, autoscaling limits, environment configuration, and complete deployment documentation — enabling end-to-end integration testing and operator handoff
**Depends on**: Phase 14
**Requirements**: TF-03, CR-01, CR-02, CR-03, CFG-01, CFG-02, CFG-03
**Success Criteria** (what must be TRUE):
  1. Reusable Terraform module `cloud-run-service` deploys all 4 services (api-service, extraction-service, grounding-service, hitl-ui) with VPC connector, secret references, and IAM bindings — DRY pattern eliminates duplication
  2. Cloud Run services have startup probes configured on `/health` endpoints with initial_delay_seconds=30 for LangGraph services to prevent premature traffic routing
  3. Autoscaling is configured with max_instances=10 per service to prevent connection pool exhaustion (40 instances total vs 100 Cloud SQL connections with pool_size=2+max_overflow=1=3 per instance)
  4. `.env.example` documents every required variable with descriptions and example values, and `terraform.tfvars.example` provides template for all Terraform input variables including image digests
  5. `infra/terraform/README.md` provides complete deployment guide with prerequisites, step-by-step instructions, troubleshooting section, and verification checklist

**Plans**: TBD

Plans:
- [ ] 15-01: TBD

<details>
<summary>✅ v1.3 Multimodal PDF Extraction (Phase 16) — SHIPPED 2026-02-12</summary>

- [x] Phase 16: Multimodal PDF Extraction (1/1 plans) — completed 2026-02-12

See `.planning/milestones/v1.3-ROADMAP.md` for full details.

</details>

## Requirement Coverage

### v1.0 Requirements (22 total - all shipped)

| Requirement | Phase | Description |
|-------------|-------|-------------|
| REQ-01.1 | Phase 1 | PostgreSQL Database with SQLModel ORM |
| REQ-01.2 | Phase 1 | Event System with Transactional Outbox |
| REQ-01.3 | Phase 1 | Docker Compose Local Development |
| REQ-02.1 | Phase 2 | Protocol PDF Upload via GCS |
| REQ-02.2 | Phase 2 | Protocol List & Detail Views |
| REQ-02.3 | Phase 2 | PDF Quality Detection |
| REQ-03.1 | Phase 3 | Gemini-Based Criteria Extraction |
| REQ-03.2 | Phase 3 | PDF Parsing with pymupdf4llm |
| REQ-03.3 | Phase 3 | Structured Criteria Schema |
| REQ-03.4 | Phase 3 | Extraction Event Publishing |
| REQ-04.1 | Phase 4 | Criteria Review UI |
| REQ-04.2 | Phase 4 | Side-by-Side PDF Viewer |
| REQ-04.3 | Phase 4 | Confidence Score Display |
| REQ-04.4 | Phase 4 | Audit Logging |
| REQ-05.1 | Phase 5 | MedGemma Entity Extraction |
| REQ-05.2 | Phase 5 | UMLS/SNOMED Grounding via MCP |
| REQ-05.3 | Phase 5 | Grounding Workflow as LangGraph |
| REQ-05.4 | Phase 6 | Entity Approval UI |
| REQ-06.1 | Phase 6 | Google OAuth Authentication |
| REQ-07.1 | Phase 6 | Full-Text Search Over Criteria |
| REQ-08.1 | Phase 7 | Retry Logic with Exponential Backoff |
| REQ-08.2 | Phase 7 | Pipeline Success Rate Target |

### v1.1 Requirements (17 total - 12 shipped, 5 paused)

| Requirement | Phase | Description | Status |
|-------------|-------|-------------|--------|
| INFRA-01 | Phase 8 | MkDocs native Mermaid.js via superfences | Shipped |
| INFRA-02 | Phase 8 | mkdocs.yml navigation with 6 sections | Shipped |
| INFRA-03 | Phase 8 | Strict mode build with zero warnings | Shipped |
| ARCH-01 | Phase 9 | C4 Container diagram | Shipped |
| ARCH-02 | Phase 9 | Service communication wiring diagram | Shipped |
| DATA-01 | Phase 9 | Database schema documentation | Shipped |
| DATA-02 | Phase 9 | LangGraph state documentation | Shipped |
| JOUR-01 | Phase 10 | Upload & Extraction narrative | Shipped |
| JOUR-02 | Phase 10 | Grounding & HITL Review narrative | Shipped |
| COMP-01 | Phase 11 | api-service component deep dive | Paused |
| COMP-02 | Phase 11 | extraction-service component deep dive | Paused |
| COMP-03 | Phase 11 | grounding-service component deep dive | Paused |
| COMP-04 | Phase 11 | hitl-ui component deep dive | Paused |
| STAT-01 | Phase 12 | Feature status table | Paused |
| STAT-02 | Phase 12 | Test coverage analysis | Paused |
| TOUR-01 | Phase 12 | Code tour with 5+ slides | Paused |
| TOUR-02 | Phase 12 | Code tour slide structure | Paused |

### v1.2 Requirements (15 total - all mapped)

| Requirement | Phase | Description |
|-------------|-------|-------------|
| TF-01 | Phase 13 | Terraform init and apply from infra/terraform/ |
| TF-02 | Phase 13 | GCS backend with state locking |
| TF-03 | Phase 15 | Reusable Cloud Run service modules |
| CR-01 | Phase 15 | Deploy 4 services to Cloud Run Gen 2 |
| CR-02 | Phase 15 | Health check startup probes on /health |
| CR-03 | Phase 15 | Autoscaling with max_instances limits |
| DB-01 | Phase 14 | Cloud SQL PostgreSQL 16 private IP |
| DB-02 | Phase 14 | VPC Serverless Connector for private access |
| SEC-01 | Phase 14 | Secret Manager for credentials |
| SEC-02 | Phase 13 | IAM service accounts with least privilege |
| REG-01 | Phase 13 | Artifact Registry repository |
| REG-02 | Phase 14 | Build and push script for container images |
| CFG-01 | Phase 15 | .env.example with all variables documented |
| CFG-02 | Phase 15 | terraform.tfvars.example template |
| CFG-03 | Phase 15 | infra/terraform/README.md deployment guide |

**Coverage: 15/15 v1.2 requirements mapped. No orphans.**

### v1.3 Requirements (6 total - all shipped)

| Requirement | Phase | Description | Status |
|-------------|-------|-------------|--------|
| EXT-01 | Phase 16 | Raw PDF bytes to Gemini as multimodal input | Shipped |
| EXT-02 | Phase 16 | ingest_node fetches bytes without markdown conversion | Shipped |
| EXT-03 | Phase 16 | extract_node sends PDF as multimodal content part | Shipped |
| EXT-04 | Phase 16 | Prompt references attached PDF | Shipped |
| EXT-05 | Phase 16 | ExtractionResult schema unchanged | Shipped |
| EXT-06 | Phase 16 | Upload, dead letter, error handling preserved | Shipped |

**Coverage: 6/6 v1.3 requirements shipped. No orphans.**

## Dependency Graph

### v1.0 (Shipped)
```
Phase 1 (Infrastructure)
    |
Phase 2 (Protocol Upload)
    |
Phase 3 (Extraction) --------+
    |                         |
Phase 4 (HITL Review)    Phase 5 (Grounding)*
    |                         |
    +-------+-----------------+
            |
    Phase 6 (Entity Approval + Auth + Search)
            |
    Phase 7 (Production Hardening)
```

### v1.1 (Documentation Site - Paused)
```
Phase 8 (Documentation Foundation)
    |
Phase 9 (Architecture & Data Models)
    |
Phase 10 (User Journey Narratives)
    |
Phase 11 (Component Deep Dives) [PAUSED]
    |
Phase 12 (Implementation Status & Code Tour) [PAUSED]
```

### v1.2 (GCP Cloud Run Deployment - Current)
```
Phase 13 (Terraform Foundation)
    |
Phase 14 (Cloud SQL, Networking & Container Registry)
    |
Phase 15 (Cloud Run Deployment & Documentation)
```

## Progress

**Execution Order:**
- v1.0: 1 → 2 → 3 → 4 → 5 → 5.1 → 5.2 → 5.3 → 6 → 7
- v1.1: 8 → 9 → 10 → [11-12 paused]
- v1.2: 13 → 14 → 15
- v1.3: 16

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Infrastructure & Data Models | v1.0 | 2/2 | Complete | 2026-02-11 |
| 2. Protocol Upload & Storage | v1.0 | 2/2 | Complete | 2026-02-11 |
| 3. Criteria Extraction Workflow | v1.0 | 2/2 | Complete | 2026-02-11 |
| 4. HITL Review UI | v1.0 | 2/2 | Complete | 2026-02-11 |
| 5. Entity Grounding Workflow | v1.0 | 3/3 | Complete | 2026-02-11 |
| 5.1. Error Handling Hardening | v1.0 | 1/1 | Complete | 2026-02-11 |
| 5.2. Test Coverage | v1.0 | 3/3 | Complete | 2026-02-11 |
| 5.3. Rename Services and Docs | v1.0 | 3/3 | Complete | 2026-02-11 |
| 6. Entity Approval, Auth & Search | v1.0 | 2/2 | Complete | 2026-02-11 |
| 7. Production Hardening | v1.0 | 4/4 | Complete | 2026-02-12 |
| 8. Documentation Foundation | v1.1 | 2/2 | Complete | 2026-02-12 |
| 9. Architecture & Data Models | v1.1 | 2/2 | Complete | 2026-02-12 |
| 10. User Journey Narratives | v1.1 | 2/2 | Complete | 2026-02-12 |
| 11. Component Deep Dives | v1.1 | 0/TBD | Paused | - |
| 12. Status & Code Tour | v1.1 | 0/TBD | Paused | - |
| 13. Terraform Foundation | v1.2 | 0/TBD | Not started | - |
| 14. Cloud SQL, Networking & Registry | v1.2 | 0/TBD | Not started | - |
| 15. Cloud Run Deployment & Docs | v1.2 | 0/TBD | Not started | - |
| 16. Multimodal PDF Extraction | v1.3 | 1/1 | Complete | 2026-02-12 |
