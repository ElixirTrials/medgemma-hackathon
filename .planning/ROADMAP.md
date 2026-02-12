# Roadmap: Clinical Trial Criteria Extraction System

## Milestones

- ✅ **v1.0 Core Pipeline** - Phases 1-7 (shipped 2026-02-12)
- 🚧 **v1.1 Documentation Site** - Phases 8-12 (in progress)

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

## 🚧 v1.1 Documentation Site (In Progress)

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
**Plans**: TBD

Plans:
- [ ] 10-01: TBD

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
**Plans**: TBD

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
**Plans**: TBD

Plans:
- [ ] 12-01: TBD

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

### v1.1 Requirements (17 total - all mapped)

| Requirement | Phase | Description |
|-------------|-------|-------------|
| INFRA-01 | Phase 8 | MkDocs native Mermaid.js via superfences |
| INFRA-02 | Phase 8 | mkdocs.yml navigation with 6 sections |
| INFRA-03 | Phase 8 | Strict mode build with zero warnings |
| ARCH-01 | Phase 9 | C4 Container diagram |
| ARCH-02 | Phase 9 | Service communication wiring diagram |
| DATA-01 | Phase 9 | Database schema documentation |
| DATA-02 | Phase 9 | LangGraph state documentation |
| JOUR-01 | Phase 10 | Upload & Extraction narrative |
| JOUR-02 | Phase 10 | Grounding & HITL Review narrative |
| COMP-01 | Phase 11 | api-service component deep dive |
| COMP-02 | Phase 11 | extraction-service component deep dive |
| COMP-03 | Phase 11 | grounding-service component deep dive |
| COMP-04 | Phase 11 | hitl-ui component deep dive |
| STAT-01 | Phase 12 | Feature status table |
| STAT-02 | Phase 12 | Test coverage analysis |
| TOUR-01 | Phase 12 | Code tour with 5+ slides |
| TOUR-02 | Phase 12 | Code tour slide structure |

**Coverage: 17/17 v1.1 requirements mapped. No orphans.**

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

### v1.1 (Documentation Site)
```
Phase 8 (Documentation Foundation)
    |
Phase 9 (Architecture & Data Models)
    |
Phase 10 (User Journey Narratives)
    |
Phase 11 (Component Deep Dives)
    |
Phase 12 (Implementation Status & Code Tour)
```

## Progress

**Execution Order:**
v1.0: 1 → 2 → 3 → 4 → 5 → 5.1 → 5.2 → 5.3 → 6 → 7
v1.1: 8 → 9 → 10 → 11 → 12

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
| 10. User Journey Narratives | v1.1 | 0/TBD | Not started | - |
| 11. Component Deep Dives | v1.1 | 0/TBD | Not started | - |
| 12. Status & Code Tour | v1.1 | 0/TBD | Not started | - |
