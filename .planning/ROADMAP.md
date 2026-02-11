# Roadmap: Clinical Trial Protocol Criteria Extraction System

## Overview

This roadmap delivers a system where clinical researchers upload protocol PDFs and receive accurately extracted, UMLS-grounded eligibility criteria through a human-in-the-loop review workflow. The 7 phases follow architectural dependency order: infrastructure and data models first, then protocol upload, AI extraction, human review, entity grounding, entity approval with auth, and production hardening. Each phase delivers standalone verifiable value while building toward the complete end-to-end pipeline.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Infrastructure & Data Models** - Foundation: database schemas, event system, and local dev environment
- [x] **Phase 2: Protocol Upload & Storage** - User entry point: PDF upload to GCS with quality detection
- [x] **Phase 3: Criteria Extraction Workflow** - Core AI: Gemini-based structured criteria extraction via agent-a
- [x] **Phase 4: HITL Review UI** - Human validation: side-by-side PDF viewer with criteria review
- [ ] **Phase 5: Entity Grounding Workflow** - Medical AI: MedGemma entity extraction and UMLS grounding via agent-b
- [ ] **Phase 6: Entity Approval, Auth & Search** - Complete the loop: entity approval UI, authentication, and search
- [ ] **Phase 7: Production Hardening** - Reliability: retry logic, error handling, and pipeline success targets

## Phase Details

### Phase 1: Infrastructure & Data Models
**Goal**: All services share consistent data contracts, the database is migrations-ready, and local development runs with a single command
**Depends on**: Nothing (first phase)
**Requirements**: REQ-01.1, REQ-01.2, REQ-01.3
**Research flags**: Standard patterns. Skip research-phase.
**Success Criteria** (what must be TRUE):
  1. SQLModel classes for Protocol, Criteria, CriteriaBatch, Entity, Review, AuditLog, and OutboxEvent exist in shared models with created_at/updated_at timestamps and JSONB fields
  2. Alembic migrations auto-generate from SQLModel metadata and apply cleanly to a fresh PostgreSQL database
  3. Event types (ProtocolUploaded, CriteriaExtracted, ReviewCompleted, EntitiesGrounded) are defined with outbox persistence pattern
  4. `docker compose up` starts PostgreSQL with persistent volume and all three services pass health checks
**Plans**: 2 plans

Plans:
- [ ] 01-01-PLAN.md -- Domain SQLModel classes, event types, and Alembic migration
- [ ] 01-02-PLAN.md -- Outbox processor, Dockerfiles, and Docker Compose infrastructure

### Phase 2: Protocol Upload & Storage
**Goal**: Clinical researchers can upload protocol PDFs through the UI and see them listed with status tracking and quality scores
**Depends on**: Phase 1
**Requirements**: REQ-02.1, REQ-02.2, REQ-02.3
**Research flags**: Standard patterns. Skip research-phase.
**Success Criteria** (what must be TRUE):
  1. User can upload a PDF through the HITL UI, which uploads directly to GCS via signed URL (no server-side proxy), and sees the protocol appear in a list
  2. Protocol list displays paginated results with status badges (uploaded, extracting, extracted, reviewed) served from server-side pagination
  3. PDF quality score is computed on upload (text extractability, page count, encoding type), stored in GCS metadata, and visible in protocol detail view
  4. Upload rejects non-PDF files and files exceeding 50MB with clear error messages
**Plans**: 2 plans

Plans:
- [ ] 02-01-PLAN.md -- Backend API: GCS signed URL upload, PDF quality analyzer, paginated list and detail endpoints
- [ ] 02-02-PLAN.md -- Frontend UI: Upload dialog, paginated protocol list with status badges, detail view with quality scores

### Phase 3: Criteria Extraction Workflow
**Goal**: Uploaded protocols are automatically processed by agent-a to extract structured inclusion/exclusion criteria with temporal constraints, assertion status, and confidence scores
**Depends on**: Phase 2
**Requirements**: REQ-03.1, REQ-03.2, REQ-03.3, REQ-03.4
**Research flags**: NEEDS RESEARCH-PHASE. Complex integration of LangExtract, Gemini structured output, and temporal/conditional criteria extraction. Research needed on: LangExtract source grounding API patterns, Gemini structured output schema design for nested medical criteria, temporal constraint extraction strategies, assertion detection integration.
**Success Criteria** (what must be TRUE):
  1. When a protocol is uploaded, agent-a automatically extracts criteria and creates a CriteriaBatch with status=pending_review within 5 minutes
  2. Each extracted criterion has structured fields: text, type (inclusion/exclusion), category, temporal_constraint, conditions, numeric_thresholds, assertion status (PRESENT/ABSENT/HYPOTHETICAL/HISTORICAL/CONDITIONAL), and confidence score (0.0-1.0)
  3. PDF parsing via pymupdf4llm preserves tables and multi-column layouts, with parsed content cached to avoid re-parsing
  4. CriteriaExtracted event is published via outbox pattern and agent-b can subscribe to it
**Plans**: 2 plans

Plans:
- [x] 03-01-PLAN.md -- Extraction foundation: ExtractionState, Pydantic schemas, PDF parser with caching, Jinja2 prompts, trigger handler
- [x] 03-02-PLAN.md -- Graph nodes and integration: 4 LangGraph nodes (ingest/extract/parse/queue), graph assembly, outbox handler registration, verification

### Phase 4: HITL Review UI
**Goal**: Clinical researchers can efficiently review AI-extracted criteria with side-by-side PDF comparison, edit individual criteria, and maintain a complete audit trail
**Depends on**: Phase 3
**Requirements**: REQ-04.1, REQ-04.2, REQ-04.3, REQ-04.4
**Research flags**: Standard patterns. Skip research-phase.
**Success Criteria** (what must be TRUE):
  1. Reviewer sees a queue of pending CriteriaBatches and can approve, reject, or modify each criterion individually (not all-or-nothing), with partial progress saved across sessions
  2. Split-screen view shows original protocol PDF (left panel with page navigation, loaded via GCS signed URL) alongside extracted criteria cards (right panel)
  3. Each criterion displays a confidence badge (high/medium/low with configurable thresholds), criteria are sortable by confidence (lowest first), and low-confidence items are visually highlighted
  4. Every review action (approve/reject/modify) is logged with reviewer_id, timestamp, action type, and before/after values, queryable via API with 100% completeness
**Plans**: 2 plans

Plans:
- [x] 04-01-PLAN.md -- Review API endpoints (batch list, criteria, review actions, PDF URL, audit log) + frontend TanStack Query hooks
- [x] 04-02-PLAN.md -- Review UI: split-screen PDF viewer + criteria cards with confidence badges, review queue, route wiring

### Phase 5: Entity Grounding Workflow
**Goal**: Extracted criteria are automatically processed by agent-b to identify medical entities via MedGemma and ground them to UMLS/SNOMED concepts via the MCP server, with tiered fallback for coverage gaps
**Depends on**: Phase 3 (needs CriteriaBatch data and CriteriaExtracted events)
**Requirements**: REQ-05.1, REQ-05.2, REQ-05.3
**Research flags**: NEEDS RESEARCH-PHASE. Complex medical AI integration. Research needed on: UMLS MCP server deployment architecture, MedGemma deployment on Vertex AI (GPU config, batch optimization), MedCAT model selection for UMLS 2024AA, tiered grounding strategy implementation.
**Success Criteria** (what must be TRUE):
  1. agent-b automatically processes criteria when CriteriaExtracted event fires, extracting medical entities (Condition, Medication, Procedure, Lab_Value, Demographic, Biomarker) with span positions and context windows
  2. Every extracted entity is grounded to UMLS CUI and SNOMED-CT code via the MCP server, with every generated code validated against the UMLS API before database storage
  3. Tiered grounding strategy works: exact match first, then semantic similarity, then routed to expert review queue -- failed grounding stores free-text plus nearest neighbor without blocking the pipeline
  4. EntitiesGrounded event is published on completion, and each grounding has a confidence score (0.0-1.0)
**Plans**: 3 plans

Plans:
- [ ] 05-01-PLAN.md -- UMLS MCP server with FastMCP: concept_search, concept_linking, semantic_type_prediction tools + UMLS REST API client with mock fallback
- [ ] 05-02-PLAN.md -- Agent-b foundation: GroundingState TypedDict, Pydantic entity schemas, Jinja2 extraction prompts, CriteriaExtracted trigger handler, UMLS validation client
- [ ] 05-03-PLAN.md -- Grounding graph nodes and integration: 4 LangGraph nodes (extract_entities/ground_to_umls/map_to_snomed/validate_confidence), graph assembly, outbox handler registration

### Phase 6: Entity Approval, Auth & Search
**Goal**: Clinical researchers can authenticate, validate grounded entities with SNOMED codes, and search across criteria -- completing the full end-to-end HITL workflow
**Depends on**: Phase 4 (HITL UI exists), Phase 5 (grounded entities exist)
**Requirements**: REQ-05.4, REQ-06.1, REQ-07.1
**Research flags**: Standard patterns. Skip research-phase.
**Success Criteria** (what must be TRUE):
  1. Researcher logs in via Google OAuth, receives a JWT, and all API endpoints require valid authentication
  2. Entity list view displays SNOMED badge (code + preferred term) with human-readable labels, and researcher can approve, reject, or modify each entity mapping individually
  3. Full-text search via GET /criteria/search?q= returns relevance-ranked results with filters for protocol, criteria type, and approval status, backed by GIN index on criteria text
**Plans**: TBD

Plans:
- [ ] 06-01: TBD
- [ ] 06-02: TBD
- [ ] 06-03: TBD

### Phase 7: Production Hardening
**Goal**: The end-to-end pipeline achieves target reliability and performance metrics for the 50-protocol pilot
**Depends on**: Phase 6 (complete pipeline exists)
**Requirements**: REQ-08.1, REQ-08.2
**Research flags**: Standard patterns. Skip research-phase.
**Success Criteria** (what must be TRUE):
  1. All external API calls (Gemini, Vertex AI, UMLS MCP, GCS) use tenacity retry with exponential backoff (max 3 retries) and circuit breaker for sustained failures, with structured logging for retry events
  2. Pipeline achieves >95% success rate from upload to criteria extraction, with failed extractions surfacing to the user with actionable error messages and dead-letter handling for unrecoverable failures
  3. Average processing time per protocol is <5 minutes end-to-end
**Plans**: TBD

Plans:
- [ ] 07-01: TBD
- [ ] 07-02: TBD

## Requirement Coverage

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

**Coverage: 22/22 v1 requirements mapped. No orphans.**

## Dependency Graph

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

*Phase 5 depends on Phase 3 (not Phase 4). Phases 4 and 5 can partially overlap: UMLS MCP server deployment can begin during Phase 4 UI development.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6 -> 7

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Infrastructure & Data Models | 2/2 | Complete | 2026-02-11 |
| 2. Protocol Upload & Storage | 2/2 | Complete | 2026-02-11 |
| 3. Criteria Extraction Workflow | 2/2 | Complete | 2026-02-11 |
| 4. HITL Review UI | 2/2 | Complete | 2026-02-11 |
| 5. Entity Grounding Workflow | 3/3 | Complete | 2026-02-11 |
| 6. Entity Approval, Auth & Search | 0/TBD | Not started | - |
| 7. Production Hardening | 0/TBD | Not started | - |
