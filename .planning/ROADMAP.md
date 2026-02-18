# Roadmap: Clinical Trial Criteria Extraction System

## Milestones

- ✅ **v1.0 Core Pipeline** - Phases 1-7 (shipped 2026-02-12)
- 🚧 **v1.1 Documentation Site** - Phases 8-12 (paused after Phase 10)
- 🚧 **v1.2 GCP Cloud Run Deployment** - Phases 13-15 (paused)
- ✅ **v1.3 Multimodal PDF Extraction** - Phase 16 (shipped 2026-02-12)
- ✅ **v1.4 Structured Entity Display & Grounding Fixes** — Phases 17-21 (shipped 2026-02-13)
- ✅ **v1.5 Structured Criteria Editor** — Phases 22-28 (shipped 2026-02-13)
- 🚧 **v2.0 Pipeline Consolidation & E2E Quality** — Phases 29-35 (in progress)

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
**Plans**: 1 plan

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
**Plans**: 1 plan

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
**Plans**: 1 plan

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
**Plans**: 1 plan

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
**Plans**: 1 plan

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
**Plans**: 1 plan

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
**Plans**: 1 plan

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
**Plans**: 1 plan

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

<details>
<summary>✅ v1.3 Multimodal PDF Extraction (Phase 16) — SHIPPED 2026-02-12</summary>

### Phase 16: Multimodal PDF Extraction
**Goal**: Replace lossy PDF → markdown → Gemini text pipeline with direct PDF → Gemini multimodal input for better extraction quality
**Depends on**: Nothing (independent optimization)
**Requirements**: EXT-01, EXT-02, EXT-03, EXT-04, EXT-05, EXT-06
**Success Criteria** (what must be TRUE):
  1. Raw PDF bytes sent directly to Gemini as multimodal input (base64 data URI)
  2. pymupdf4llm markdown conversion removed from extraction pipeline
  3. Extraction prompt references attached PDF document (no embedded markdown)
  4. ExtractionResult schema unchanged, downstream components unmodified
**Plans**: 1 plan

Plans:
- [x] 16-01: Replace pymupdf4llm with native Gemini multimodal PDF input

</details>

<details>
<summary>✅ v1.4 Structured Entity Display & Grounding Fixes (Phases 17-21) — SHIPPED 2026-02-13</summary>

### Phase 17: Frontend Structured Data Display
**Goal**: Display temporal constraints, numeric thresholds, and SNOMED/UMLS data that already exists (or will exist after backend fixes) in the HITL review UI
**Depends on**: Nothing (frontend-only, can display what data exists)
**Requirements**: FE-01, FE-02, FE-03
**Success Criteria** (what must be TRUE):
  1. CriterionCard shows temporal_constraint when present, rendered as human-readable text (e.g., "Within 6 months of screening")
  2. CriterionCard shows numeric_thresholds when present, rendered as badges (e.g., ">=18 years", "<1.5 WOMAC")
  3. EntityCard shows SNOMED badge and UMLS CUI link when data is populated (existing code in EntityCard.tsx verified working)
**Plans**: 1 plan

Plans:
- [x] 17-01: Temporal constraint display, numeric threshold badges, EntityCard SNOMED/UMLS verification

### Phase 18: Grounding Pipeline Debug & Fix
**Goal**: Diagnose and fix the UMLS/SNOMED grounding pipeline so entities get real CUI and SNOMED codes instead of 100% expert_review fallback
**Depends on**: Nothing (backend-only, independent of Phase 17)
**Requirements**: GRD-01, GRD-02, GRD-03, GRD-04
**Success Criteria** (what must be TRUE):
  1. Root cause of MCP concept_linking failure identified and fixed (UMLS API key, MCP server startup, tool return format, or other)
  2. Common medical terms like "acetaminophen", "osteoarthritis", "Heparin" successfully resolve to UMLS CUI
  3. Entities with UMLS CUI get SNOMED-CT codes via map_to_snomed
  4. Re-running grounding on existing protocols yields >50% entities with non-null CUI/SNOMED
**Plans**: 1 plan

Plans:
- [x] 18-01: Fix MCP tool result parsing, error handling, and SNOMED lookup with integration tests

### Phase 19: Extraction Structured Output Improvement
**Goal**: Make Gemini populate numeric_thresholds and conditions fields for criteria that contain numeric values or conditional dependencies
**Depends on**: Nothing (independent improvement)
**Requirements**: EXT-01, EXT-02, EXT-03
**Success Criteria** (what must be TRUE):
  1. Extraction system prompt includes few-shot examples for numeric_thresholds (age ranges, lab values, dosage limits)
  2. Extraction system prompt includes few-shot examples for conditions (conditional dependencies)
  3. Re-extracting criteria for existing protocols produces numeric_thresholds for criteria containing numeric values (e.g., age ranges, lab value cutoffs)
**Plans**: 1 plan

Plans:
- [x] 19-01: Few-shot examples for numeric_thresholds and conditions, enhanced Field descriptions, extraction verification

### Phase 20: MedGemma Agentic Grounding
**Goal**: Replace Gemini-based entity extraction + separate UMLS pipeline with MedGemma as an agentic reasoner that iteratively uses UMLS MCP tools to extract, ground, and map entities to UMLS CUI and SNOMED codes
**Depends on**: Phase 18 (UMLS MCP fixes must be in place)
**Requirements**: MGR-01, MGR-02, MGR-03, MGR-04
**Success Criteria** (what must be TRUE):
  1. `ModelGardenChatModel` and `AgentConfig.from_env()` ported from gemma-hackathon to `libs/inference/`, using `VERTEX_ENDPOINT_ID` from `.env` for MedGemma endpoint
  2. Agentic grounding node implements iterative loop: MedGemma extracts entities + suggests UMLS search terms → UMLS MCP `concept_search` returns CUI+SNOMED → MedGemma evaluates results and refines if needed → max 3 iterations
  3. Grounding graph simplified from 4 nodes to 2: `medgemma_ground` (agentic loop) → `validate_confidence`
  4. Common medical terms (acetaminophen, osteoarthritis, Heparin) grounded with CUI + SNOMED via the agentic loop
**Plans**: 2 plans

Plans:
- [x] 20-01: Port ModelGardenChatModel and AgentConfig from gemma-hackathon to libs/inference/
- [x] 20-02: Agentic grounding node, prompts, schemas, and simplified 2-node graph

### Phase 21: Upgrade to Gemini 3 Flash
**Goal**: Upgrade criteria extraction model from gemini-2.5-flash to gemini-3-flash-preview for improved extraction quality
**Depends on**: Nothing (independent config change)
**Requirements**: G3F-01, G3F-02
**Success Criteria** (what must be TRUE):
  1. `.env` GEMINI_MODEL_NAME and all hardcoded defaults in `extract.py`, `queue.py` updated to `gemini-3-flash-preview`
  2. Extraction verified working on existing protocol PDF with new model
**Plans**: 1 plan

Plans:
- [x] 21-01: Update all gemini-2.5-flash references to gemini-3-flash-preview

</details>

<details>
<summary>✅ v1.5 Structured Criteria Editor (Phases 22-28) — SHIPPED 2026-02-13</summary>

### Phase 22: Backend Data Model + API Extension
**Goal**: Extend the review action API to accept and persist structured field edits (entity/relation/value) while maintaining backward compatibility with existing text-only reviews
**Depends on**: Nothing (first phase of v1.5, backend foundation)
**Requirements**: API-01, API-02, API-03, EDIT-07
**Success Criteria** (what must be TRUE):
  1. ReviewActionRequest accepts optional `modified_structured_fields` (Dict[str, Any]) — existing text-only modify actions still work unchanged
  2. `_apply_review_action()` updates temporal_constraint, numeric_thresholds, and conditions from structured fields when provided
  3. Audit log captures before/after values for structured field changes with schema_version
  4. Existing text-only reviews (pre-v1.5) continue to display correctly in the UI
**Plans**: 1 plan

Plans:
- [x] 22-01: Extend ReviewActionRequest with structured fields, update _apply_review_action, add audit schema_version, integration tests

### Phase 23: Core Structured Editor Component
**Goal**: Build the StructuredFieldEditor component with entity/relation/value triplet fields, adaptive value input, and form validation — testable in isolation before integration
**Depends on**: Phase 22 (backend must accept structured data)
**Requirements**: EDIT-02, EDIT-03, EDIT-04
**Success Criteria** (what must be TRUE):
  1. StructuredFieldEditor.tsx renders entity/relation/value triplet fields for a criterion
  2. Relation dropdown offers full operator set (=, !=, >, >=, <, <=, within, not_in_last, contains, not_contains)
  3. Value input adapts based on relation type — single value for standard operators, min/max for range, duration+unit for temporal
  4. Form state managed via react-hook-form useFieldArray with proper cleanup when relation changes (no state leak)
**Plans**: 1 plan

Plans:
- [x] 23-01: Types, constants, Radix Select relation dropdown, adaptive ValueInput, and StructuredFieldEditor with react-hook-form state management

### Phase 24: CriterionCard Integration + Review Workflow
**Goal**: Wire the structured editor into the existing CriterionCard review workflow so reviewers can toggle between text and structured edit modes and save structured edits end-to-end
**Depends on**: Phase 23 (editor component must exist)
**Requirements**: EDIT-01, EDIT-05, EDIT-06
**Success Criteria** (what must be TRUE):
  1. Reviewer can toggle between text edit and structured edit modes on a criterion
  2. Structured edits save via existing modify action workflow (handleStructuredSave → useReviewAction mutation)
  3. Structured edits persist to database and display correctly after page refresh
  4. TypeScript types in useReviews.ts updated for ReviewActionRequest with modified_structured_fields
**Plans**: 1 plan

Plans:
- [x] 24-01: Toggle UI, StructuredFieldEditor integration, structured save callback, TypeScript type updates

### Phase 25: UMLS Concept Search Autocomplete
**Goal**: Replace the plain text entity field with a UMLS/SNOMED autocomplete search that populates CUI, SNOMED code, and preferred term from the existing UMLS MCP server
**Depends on**: Phase 23 (structured editor must exist)
**Requirements**: UMLS-01, UMLS-02, UMLS-03, UMLS-04, UMLS-05, API-04
**Success Criteria** (what must be TRUE):
  1. Entity field provides autocomplete search via UMLS MCP concept_search
  2. Autocomplete results show preferred term + CUI code + semantic type
  3. Search debounced (300ms minimum) with loading indicator, minimum 3 characters
  4. Selecting a UMLS concept populates entity fields (CUI, SNOMED code, preferred term)
  5. UMLS search proxy endpoint available for frontend autocomplete
**Plans**: 2 plans

Plans:
- [x] 25-01: Backend UMLS search proxy endpoint (GET /api/umls/search)
- [x] 25-02: Frontend useUmlsSearch hook, UmlsCombobox component, EntityCard integration

### Phase 26: Rationale Capture
**Goal**: Add optional rationale text capture to the structured editor so modify actions include reviewer reasoning for audit trail compliance
**Depends on**: Phase 24 (review workflow integration must exist)
**Requirements**: RATL-01, RATL-02, RATL-03
**Success Criteria** (what must be TRUE):
  1. Rationale text field available when modifying structured fields
  2. Rationale persisted with the review action in audit log
  3. Cancel clears rationale along with all other form state
**Plans**: 1 plan

Plans:
- [x] 26-01: Rationale textarea in modify mode, audit log persistence, cancel state cleanup

### Phase 27: Multi-Mapping Support
**Goal**: Enable reviewers to add multiple field mappings to a single criterion for complex criteria with multiple constraints (e.g., "18-65 years AND BMI <30")
**Depends on**: Phase 24 (single mapping save must work first)
**Requirements**: MULTI-01, MULTI-02, MULTI-03, MULTI-04
**Success Criteria** (what must be TRUE):
  1. Reviewer can add multiple field mappings to a single criterion
  2. Reviewer can remove individual field mappings from a criterion
  3. Each mapping has independent entity/relation/value fields
  4. Backend stores and returns array of field mappings per criterion
**Plans**: 1 plan

Plans:
- [x] 27-01: Multi-mapping useFieldArray UI + backend field_mappings array storage

### Phase 28: PDF Scroll-to-Source (Evidence Linking)
**Goal**: Clicking a criterion scrolls the PDF viewer to the source page and highlights the relevant text, enabling rapid evidence verification during review
**Depends on**: Phase 24 (review workflow must exist)
**Requirements**: EVID-01, EVID-02, EVID-03, EVID-04
**Success Criteria** (what must be TRUE):
  1. Clicking a criterion scrolls the PDF viewer to the source page
  2. Source text highlighted or visually indicated in PDF viewer
  3. Extraction service captures page number for each extracted criterion
  4. Evidence linking degrades gracefully when page data is unavailable
**Plans**: 2 plans

Plans:
- [x] 28-01: Backend: page_number in extraction schema, DB model, prompt, queue node, and API response
- [x] 28-02: Frontend: PdfViewer scroll-to-page, CriterionCard click handler, ReviewPage wiring, text highlighting

</details>

## v2.0 Pipeline Consolidation & E2E Quality (Current)

**Milestone Goal:** Consolidate the extraction and grounding pipeline into a unified architecture, replace UMLS MCP with ToolUniverse scoped grounding, fix all critical E2E bugs (audit trail, grounding confidence, dashboard), improve extraction determinism, and complete the editor polish for real-world corpus building.

**Parallel Execution:** Phases 30 and 31 run in parallel after Phase 29 completes (UI track || Pipeline track).

### Phase 29: Backend Bug Fixes
**Goal**: Fix critical bugs blocking regulatory compliance and user trust — grounding confidence >0%, visible audit trail, accurate dashboard pending count
**Depends on**: Nothing (first phase of v2.0, bug fixes before architectural changes)
**Requirements**: BUGF-01, BUGF-02, BUGF-03
**Success Criteria** (what must be TRUE):
  1. Grounding produces real UMLS/SNOMED codes with >0% confidence for at least 50% of extracted entities (debug current 0% confidence issue)
  2. Audit trail entries are visible on the Review page after approve/reject/modify actions (add batch_id filter to API query)
  3. Dashboard pending count includes batches with any unreviewed criteria, not just status='pending_review' (criteria-level query)
**Plans**: 2 plans

Plans:
- [ ] 29-01-PLAN.md — Fix grounding confidence 0% (BUGF-01): diagnostic logging + root cause fix in MedGemma agentic loop
- [ ] 29-02-PLAN.md — Audit trail visibility (BUGF-02) + pending count fix (BUGF-03): batch_id filter, inline audit history UI, criteria-level pending count

### Phase 30: UX Polish & Editor Pre-Loading || PARALLEL with Phase 31
**Goal**: Essential UX improvements for review workflow plus editor pre-loading and read-mode badges — frontend-only work that runs in parallel with backend pipeline consolidation
**Depends on**: Phase 29 (bug fixes complete; runs parallel with Phase 31)
**Requirements**: UX-01, UX-02, UX-03, UX-04, EDIT-01, EDIT-02
**Success Criteria** (what must be TRUE):
  1. Reviewed criteria have visual distinction from pending criteria via left border color (green for reviewed, yellow for pending)
  2. Reviewer can provide optional rationale when rejecting or approving criteria (extend existing modify rationale to all actions)
  3. Reviewer can search/filter criteria by text on the Review page (debounced search input with backend query)
  4. Criteria sections are sorted with headers (Inclusion first, then Exclusion)
  5. Saved field_mappings pre-populate the structured editor when entering modify mode (fix buildInitialValues() priority)
  6. Saved field_mappings are displayed as badges/chips in read mode (outside edit mode) showing entity/relation/value triplets
**Plans**: 2 plans

Plans:
- [ ] 30-01-PLAN.md — Review status borders, sticky search/filter bar, section sorting with headers
- [ ] 30-02-PLAN.md — Reject dialog with predefined reasons, field mapping read-mode badges with AND/OR connectors

### Phase 31: TerminologyRouter & Pipeline Consolidation || PARALLEL with Phase 30
**Goal**: Build entity-type-aware terminology routing with ToolUniverse API and consolidate extraction+grounding into a unified 5-node LangGraph pipeline — backend work that runs in parallel with frontend UX polish
**Depends on**: Phase 29 (bug fixes complete; runs parallel with Phase 30)
**Requirements**: GRND-01, GRND-02, GRND-04, GRND-06, PIPE-01, PIPE-02, PIPE-03
**Success Criteria** (what must be TRUE):
  1. TerminologyRouter routes entities to terminology APIs based on entity type (Medication->RxNorm, Condition->ICD-10+SNOMED, Lab->LOINC, Phenotype->HPO)
  2. UMLS/SNOMED grounding is retained via direct Python import (not MCP subprocess) for unroutable entity types
  3. ToolUniverse Python API used with selective tool loading (RxNorm, ICD-10, LOINC, HPO, UMLS REST) — not MCP subprocess
  4. Unroutable entity types (Demographic, Procedure, Biomarker) are explicitly skipped with logging, not silently dropped
  5. Extraction and grounding run in a flat 5-node LangGraph (ingest->extract->parse->ground->persist) with no outbox hop
  6. PipelineState TypedDict carries all data through pipeline (PDF bytes, extraction results, entities, grounding results) with no redundant DB reads
  7. criteria_extracted outbox event is removed; protocol_uploaded outbox is retained for async pipeline trigger
  8. Ground node delegates to helper functions for entity extraction and terminology routing (not inline logic)
  9. Pipeline compiles and runs end-to-end on test protocol with mock grounding (verifies state flow before real grounding integration)
**Plans**: 3 plans

Plans:
- [ ] 31-01-PLAN.md — Service skeleton, PipelineState, YAML routing config, TerminologyRouter with tests
- [ ] 31-02-PLAN.md — Extraction tools (pdf_parser, gemini_extractor), ingest/extract/parse nodes
- [ ] 31-03-PLAN.md — Ground node, persist node, MedGemma decider, 5-node graph assembly, outbox wiring

### Phase 32: Entity Model, Ground Node & Multi-Code Display
**Goal**: Replace ToolUniverse stub with real terminology API integration, add LangGraph PostgreSQL checkpointing for retry-from-failure, and display multi-terminology codes in the UI
**Depends on**: Phase 31 (pipeline skeleton and terminology clients must exist)
**Requirements**: GRND-03, GRND-05, PIPE-04, EDIT-03
**Success Criteria** (what must be TRUE):
  1. Entity model stores multi-system codes (rxnorm_code, icd10_code, loinc_code, hpo_code alongside existing umls_cui and snomed_code) — ALREADY DONE
  2. TerminologyRouter returns real terminology candidates for RxNorm, ICD-10, LOINC, HPO (ToolUniverse or NLM API fallback)
  3. Terminology search proxy endpoints available for frontend autocomplete across all systems
  4. LangGraph PostgreSQL checkpointing saves state after each pipeline node
  5. Failed protocols can be retried via checkpoint resume (not full pipeline restart)
  6. Multi-terminology codes (RxNorm, ICD-10, LOINC, HPO, SNOMED, UMLS) visible per entity as color-coded badges
  7. Per-system autocomplete editing for all terminology codes
  8. Grounding errors shown as red "Failed" badge with specific error reason
**Plans**: 3 plans

Plans:
- [ ] 32-01-PLAN.md — Real terminology API integration (ToolUniverse/NLM) and search proxy endpoints
- [ ] 32-02-PLAN.md — LangGraph PostgreSQL checkpointing and retry-from-checkpoint endpoint
- [ ] 32-03-PLAN.md — Multi-code badge display, per-system autocomplete, and retry UX

### Phase 33: Re-Extraction Tooling & Review Protection
**Goal**: Enable re-extraction on existing protocols without re-upload, with review protection to preserve human corrections and determinism improvements for reproducibility
**Depends on**: Phase 32 (pipeline must be complete for re-extraction)
**Requirements**: REXT-01, REXT-02, REXT-03, REXT-04
**Success Criteria** (what must be TRUE):
  1. Researcher can trigger re-extraction on an existing protocol without re-uploading the PDF (POST /protocols/{id}/reextract endpoint)
  2. Re-extraction creates a new batch alongside existing batches, not replacing them (preserves history)
  3. Batches with reviewed criteria are protected via is_locked flag (prevents overwrite, UI shows warning)
  4. Extraction uses temperature=0 and prompt granularity instructions for improved determinism (seed parameter for best-effort reproducibility)
  5. Re-extraction UI button in protocol detail page with confirmation modal explaining batch creation
**Plans**: 2 plans

Plans:
- [ ] 33-01-PLAN.md — Backend re-extraction endpoint, batch archiving, fuzzy review inheritance, temperature=0
- [ ] 33-02-PLAN.md — Frontend re-extraction button, confirmation modal, processing states

### Phase 34: Corpus Comparison & Export
**Goal**: Enable side-by-side diff of AI-extracted vs human-corrected criteria, export reviewed corpus for model evaluation, and display agreement metrics
**Depends on**: Phase 33 (re-extraction creates multiple batches for comparison)
**Requirements**: CORP-01, CORP-02, CORP-03
**Success Criteria** (what must be TRUE):
  1. Researcher can view side-by-side diff of AI-extracted vs human-corrected criteria (audit log based reconstruction)
  2. Reviewed criteria can be exported as JSON/CSV corpus with columns: criterion_text, ai_entities (original), human_entities (after review), entity_type, terminology_codes
  3. Metrics dashboard shows agreement rate and modification frequency by category/entity_type (computed from audit log)
  4. Batch-level comparison available when multiple batches exist for same protocol (old batch vs new batch after re-extraction)
  5. Corpus export includes extraction model version and prompt version for traceability
**Plans**: 3 plans

Plans:
- [ ] 34-01-PLAN.md — Data integrity check endpoint + CI test suite + agreement metrics endpoint
- [ ] 34-02-PLAN.md — Per-criterion AI re-run endpoint + batch comparison endpoint + protocol batches endpoint
- [ ] 34-03-PLAN.md — Frontend: agreement metrics, batch timeline, batch comparison view, criterion re-run dialog

### Phase 35: E2E Gap Closure
**Goal**: Fix all bugs discovered during E2E Playwright testing — re-extraction pipeline completion, criterion AI rerun SDK mismatch, and housekeeping (hooks fix commit, schema drift)
**Depends on**: Phase 34 (gap closure for Phase 34 UAT findings)
**Requirements**: GAP-1, GAP-5, GAP-6, GAP-7, GAP-8 (from 34-GAPS-v2.md)
**Success Criteria** (what must be TRUE):
  1. Re-extraction pipeline completes end-to-end: protocol status transitions to "pending_review" after re-extraction (not stuck at "grounding")
  2. Re-extracted batch has entities populated by ground_node (not 0 entities)
  3. Criterion AI rerun endpoint returns 200 with original vs revised structured fields (not 503)
  4. ProtocolDetail.tsx hooks fix committed (useState before conditional returns)
  5. Alembic version stamped so migrations can be applied going forward
**Plans**: 2 plans

Plans:
- [ ] 35-01-PLAN.md — Re-extraction pipeline fixes: persist_node status transition + ground_node entity population during re-extraction
- [ ] 35-02-PLAN.md — Rerun SDK fix (google.generativeai -> google.genai) + hooks commit + alembic stamp

---

## v1.2 GCP Cloud Run Deployment (Paused)

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
**Plans**: 1 plan

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
**Plans**: 1 plan

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
**Plans**: 1 plan

Plans:
- [ ] 15-01: TBD

---

## Dependency Graph

### v2.0 (Current)
```
Phase 29 (Backend Bug Fixes)
    ├── Phase 30 (UX Polish & Editor Pre-Loading)    ── PARALLEL
    └── Phase 31 (TerminologyRouter & Pipeline)      ── PARALLEL
                └── Phase 32 (Entity Model, Ground Node & Multi-Code Display)
                        └── Phase 33 (Re-Extraction & Review Protection)
                                └── Phase 34 (Corpus Comparison & Export)
                                        └── Phase 35 (E2E Gap Closure)
```

Waves: 29 -> [30 || 31] -> 32 -> 33 -> 34 -> 35

---

## Progress

**Execution Order:**
- v1.0: 1 -> 2 -> 3 -> 4 -> 5 -> 5.1 -> 5.2 -> 5.3 -> 6 -> 7
- v1.1: 8 -> 9 -> 10 -> [11-12 paused]
- v1.2: 13 -> 14 -> 15
- v1.3: 16
- v1.4: 17 + 18 + 19 (parallel) -> 20 (after 18) + 21 (independent)
- v1.5: 22 -> 23 -> 24 + 25 (parallel) -> 26 + 27 + 28 (after 24)
- v2.0: 29 -> [30 || 31] -> 32 -> 33 -> 34 -> 35

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
| 17. Frontend Structured Data Display | v1.4 | 1/1 | Complete | 2026-02-12 |
| 18. Grounding Pipeline Debug & Fix | v1.4 | 1/1 | Complete | 2026-02-12 |
| 19. Extraction Structured Output | v1.4 | 1/1 | Complete | 2026-02-12 |
| 20. MedGemma Agentic Grounding | v1.4 | 2/2 | Complete | 2026-02-12 |
| 21. Gemini 3 Flash Upgrade | v1.4 | 1/1 | Complete | 2026-02-13 |
| 22. Backend Data Model + API Extension | v1.5 | 1/1 | Complete | 2026-02-13 |
| 23. Core Structured Editor Component | v1.5 | 1/1 | Complete | 2026-02-13 |
| 24. CriterionCard Integration + Review Workflow | v1.5 | 1/1 | Complete | 2026-02-13 |
| 25. UMLS Concept Search Autocomplete | v1.5 | 2/2 | Complete | 2026-02-13 |
| 26. Rationale Capture | v1.5 | 1/1 | Complete | 2026-02-13 |
| 27. Multi-Mapping Support | v1.5 | 1/1 | Complete | 2026-02-13 |
| 28. PDF Scroll-to-Source (Evidence Linking) | v1.5 | 2/2 | Complete | 2026-02-13 |
| 29. Backend Bug Fixes | v2.0 | 0/TBD | Not started | - |
| 30. UX Polish & Editor Pre-Loading | v2.0 | 0/TBD | Not started | - |
| 31. TerminologyRouter & Pipeline Consolidation | v2.0 | 0/TBD | Not started | - |
| 32. Entity Model, Ground Node & Multi-Code Display | v2.0 | 0/3 | Planned | - |
| 33. Re-Extraction Tooling & Review Protection | v2.0 | 0/TBD | Not started | - |
| 34. Corpus Comparison & Export | v2.0 | Complete    | 2026-02-17 | - |
| 35. E2E Gap Closure | v2.0 | Complete    | 2026-02-17 | - |
| 36. E2E Test Infrastructure | v2.1 | 2/2 | Complete | 2026-02-17 |
| 37. E2E Test Cases & Baseline | v2.1 | 1/1 | Complete | 2026-02-17 |
| 38. Quality Evaluation Script | v2.1 | 0/2 | Planned | - |
| 39. Bug Catalog | v2.1 | 0/1 | Planned | - |
| 40. Legacy Cleanup & ToolUniverse Grounding | 2/2 | Complete   | 2026-02-17 | - |
| 41. Entity Decomposition & Docker GCP Credentials | v2.1 | 0/2 | Planned | - |
| 42. Pipeline Stability & UMLS Resilience | v2.1 | 0/2 | Planned | - |
| 43. Dashboard & Protocol List UX | v2.1 | 0/1 | Planned | - |

---

## v2.1 E2E Testing & Quality Evaluation (Phases 36-39)

**Milestone Goal:** Automated E2E testing against Docker Compose stack with quality evaluation.

### Phase 36: E2E Test Infrastructure
**Goal**: Developers can run the E2E suite against a live Docker Compose stack, with tests skipping gracefully when the stack is not available and test data cleaned up after each run
**Depends on**: Nothing (first phase of v2.1, scaffold before test cases)
**Requirements**: E2E-04, E2E-05
**Success Criteria** (what must be TRUE):
  1. Running `uv run pytest -m e2e` against a stopped stack prints a skip message for each test and exits with code 0 (not failure)
  2. Running `uv run pytest -m e2e` against a running Docker Compose stack executes tests against the real PostgreSQL and real Gemini API
  3. After each E2E test run, all protocols and criteria created during the test are deleted from the database (no leftover test data)
  4. Test conftest provides a fixture that detects Docker Compose availability and uploads a test PDF, returning the protocol_id
**Plans**: 2 plans

Plans:
- [x] 36-01-PLAN.md -- E2E conftest with Docker Compose detection, skip logic, and core fixtures
- [x] 36-02-PLAN.md -- Upload fixture, cleanup fixture, and infrastructure smoke test

### Phase 37: E2E Test Cases & Baseline
**Goal**: The E2E suite verifies that a real protocol PDF runs through the full pipeline and produces inclusion/exclusion criteria with grounded entities, and establishes a numeric regression baseline
**Depends on**: Phase 36 (test infrastructure must be in place)
**Requirements**: E2E-01, E2E-02, E2E-03, E2E-06
**Plans**: 1 plan

Plans:
- [x] 37-01-PLAN.md — Baseline config + full pipeline E2E tests (upload, criteria verification, entity grounding, regression baseline)

### Phase 38: Quality Evaluation Script
**Goal**: A standalone script runs the unified pipeline on 2-3 sample PDFs and generates a structured markdown report
**Depends on**: Nothing (independent script)
**Requirements**: QUAL-01, QUAL-02, QUAL-03, QUAL-04, QUAL-05, QUAL-06, QUAL-07
**Plans**: 2 plans

Plans:
- [ ] 38-01-PLAN.md — Core quality eval script: upload PDFs, collect results via API, compute stats, generate markdown report (QUAL-01 through QUAL-06)
- [ ] 38-02-PLAN.md — LLM heuristic assessment (QUAL-07): Gemini evaluates extraction completeness and grounding accuracy with reasoning

### Phase 39: Bug Catalog
**Goal**: The quality report includes a bug/problem catalog section that identifies ungrounded entities, pipeline errors, and structural anomalies
**Depends on**: Phase 38
**Requirements**: BUG-01, BUG-02, BUG-03, BUG-04, BUG-05
**Plans**: 1 plan

Plans:
- [ ] 39-01-PLAN.md — Bug catalog analysis functions + report section integration (ungrounded entities, pipeline errors, structural issues, severity categorization, recommendations)

### Phase 40: Legacy Cleanup & ToolUniverse Grounding
**Goal**: Delete legacy v1 services (grounding-service, extraction-service), replace broken UMLS/SNOMED direct imports with ToolUniverse SDK, eliminate all cross-dependencies on legacy code, and verify the unified pipeline grounds entities with real terminology codes
**Depends on**: Nothing (independent cleanup, can run after quality eval reveals the broken grounding)
**Requirements**: CLEAN-01 (delete legacy services), CLEAN-02 (ToolUniverse replaces UmlsClient in TerminologyRouter), CLEAN-03 (zero imports from grounding-service), CLEAN-04 (pipeline produces grounded entities with >0% CUI rate), CLEAN-05 (MedGemma agentic reasoning loop with 3-question retry and expert_review routing)
**Success Criteria** (what must be TRUE):
  1. `services/grounding-service/` and `services/extraction-service/` directories deleted; all imports, workspace refs, docker-compose entries, and pyproject.toml references removed
  2. TerminologyRouter uses ToolUniverse SDK (`tooluniverse` package) for ALL terminology lookups: `umls_search_concepts`, `snomed_search_concepts`, `icd_search_codes`, `loinc_search_codes`, RxNorm tool, HPO tool
  3. `umls-mcp-server` retained ONLY as a thin wrapper for ToolUniverse (or deleted if ToolUniverse replaces it entirely); no direct `UmlsClient` usage in the pipeline
  4. API service search endpoints (`/api/terminology/{system}/search`, `/api/umls/search`) work via ToolUniverse instead of UmlsClient
  5. Running the pipeline on a test PDF produces entities with non-zero grounding confidence and real CUI/SNOMED/terminology codes
  6. `uv run pytest` passes with no import errors from deleted services
  7. MedGemma agentic reasoning loop asks 3 questions (valid criterion? derived entity? rephrase?) before retry attempts
  8. Max 3 grounding attempts per entity, then route to expert_review queue with warning badge
  9. Consent entities skip grounding; Demographics (age/gender) attempt grounding via UMLS/SNOMED
**Plans**: 2 plans

Plans:
- [ ] 40-01-PLAN.md — Delete legacy services + integrate ToolUniverse SDK + rewrite endpoints/tests + MedGemma agentic loop
- [ ] 40-02-PLAN.md — End-to-end verification: live grounding codes + autocomplete + agentic loop + human checkpoint

### Phase 41: Entity Decomposition & Docker GCP Credentials
**Goal**: Fix the critical grounding pipeline: decompose full criterion sentences into discrete medical entities with correct types, and configure GCP credentials in Docker so MedGemma auth succeeds
**Depends on**: Phase 40 (ToolUniverse grounding must be in place)
**Requirements**: FIX-B3, FIX-B4, FIX-B5, FIX-B12
**Gap Closure:** Closes gaps B3, B4, B5, B12 from E2E Test Report 2026-02-18
**Success Criteria** (what must be TRUE):
  1. Parse node decomposes each criterion into discrete medical entities (e.g., "eGFR" not "The patient must have eGFR ≥ 30 mL/min") via a Gemini entity-decomposition prompt
  2. Entities have correct types (Medication, Condition, Lab, Procedure, Demographic) — not all "Condition"
  3. Docker Compose mounts GCP service account credentials and sets GOOGLE_APPLICATION_CREDENTIALS for MedGemma/Vertex AI
  4. MedGemma auth failure falls back gracefully to best UMLS candidate (not 186s retry timeout)
  5. Re-running pipeline on test PDF produces entities with non-zero grounding confidence and real terminology codes
**Plans**: 2 plans

Plans:
- [ ] 41-01-PLAN.md — Entity decomposition prompt + parse node integration + entity type mapping
- [ ] 41-02-PLAN.md — Docker GCP credential mount + MedGemma auth fallback + end-to-end verification

### Phase 42: Pipeline Stability & UMLS Resilience
**Goal**: Fix MLflow trace leaks, add UMLS search resilience (validation + retry + circuit breaker), and persist upload directory across container restarts
**Depends on**: Phase 41 (grounding must work before optimizing stability)
**Requirements**: FIX-B14, FIX-B15, FIX-B13
**Gap Closure:** Closes gaps B14, B15, B13 from E2E Test Report 2026-02-18
**Success Criteria** (what must be TRUE):
  1. MLflow traces are never stuck IN_PROGRESS: MLFLOW_TRACE_TIMEOUT_SECONDS set + try/finally span closure in trigger.py
  2. UMLS search validates queries client-side (rejects numeric-only, too-short, sentence-length queries) — eliminates 422 errors
  3. UMLS search retries on 502/503 with exponential backoff (max 3 attempts) and circuit breaker (10 failures → 60s cooldown)
  4. Upload directory persisted via Docker named volume across container restarts
**Plans**: 2 plans

Plans:
- [ ] 42-01-PLAN.md — MLflow trace leak fix + upload volume persistence with SHA-256 dedup
- [ ] 42-02-PLAN.md — ToolUniverse retry/circuit breaker + frontend query validation and circuit-open indicator

### Phase 43: Dashboard & Protocol List UX
**Goal**: Wire dashboard recent activity feed, deduplicate protocol list, and add retry/archive actions for dead letter protocols
**Depends on**: Nothing (independent UX fixes)
**Requirements**: FIX-B7, FIX-B6, FIX-B8
**Gap Closure:** Closes gaps B7, B6, B8 from E2E Test Report 2026-02-18
**Success Criteria** (what must be TRUE):
  1. Dashboard Recent Activity shows last 20 audit log entries (review actions, pipeline completions)
  2. Protocol list deduplicates re-uploaded protocols (show latest version, expandable version history)
  3. Dead Letter protocols have Retry and Archive action buttons in the UI
**Plans**: 1 plan

Plans:
- [ ] 43-01-PLAN.md — Dashboard activity feed + protocol dedup + dead letter retry/archive endpoints and UI

### v2.1 Dependency Graph
```
Phase 36 (E2E Test Infrastructure)
    └── Phase 37 (E2E Test Cases & Baseline)

Phase 38 (Quality Evaluation Script)  [independent]
    └── Phase 39 (Bug Catalog)

Phase 40 (Legacy Cleanup & ToolUniverse Grounding)  [independent]
    └── Phase 41 (Entity Decomposition & Docker GCP Credentials)
            └── Phase 42 (Pipeline Stability & UMLS Resilience)

Phase 43 (Dashboard & Protocol List UX)  [independent]
```

Tracks: [36 -> 37] || [38 -> 39] || [40 -> 41 -> 42] || [43]
