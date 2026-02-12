# Requirements: Documentation Site

**Defined:** 2026-02-12
**Core Value:** Comprehensive documentation that bridges high-level intent and low-level code, making the system accessible to engineers, PMs, and clinical researchers

## v1.1 Requirements

Requirements for documentation site milestone. Each maps to roadmap phases.

### Documentation Infrastructure

- [ ] **INFRA-01**: MkDocs configuration updated with native Mermaid.js via superfences (replacing deprecated mermaid2 plugin)
- [ ] **INFRA-02**: mkdocs.yml navigation structure includes all 6 documentation sections with correct hierarchy
- [ ] **INFRA-03**: Documentation build passes in strict mode with zero warnings

### System Architecture

- [ ] **ARCH-01**: system-architecture.md contains a Mermaid C4 Container diagram showing React UI, FastAPI, PostgreSQL, LangGraph agents, and FastMCP interactions
- [ ] **ARCH-02**: system-architecture.md contains a wiring diagram section explaining service communication patterns (REST for frontend-to-backend, transactional outbox for event-driven agent triggers)

### User Journeys

- [ ] **JOUR-01**: user-journeys.md contains "Upload & Extraction" narrative with Mermaid sequence diagram (Researcher to HITL UI to API to GCS to Outbox to Extraction Service to DB)
- [ ] **JOUR-02**: user-journeys.md contains "Grounding & HITL Review" narrative with Mermaid sequence diagram (CriteriaExtracted to Grounding Service to DB to HITL UI to Approval to Audit Log)

### Component Deep Dives

- [ ] **COMP-01**: components/api-service.md documents responsibilities, key endpoints, configuration, and environment variables
- [ ] **COMP-02**: components/extraction-service.md documents LangGraph graph nodes, PDF parsing, Gemini integration, and configuration
- [ ] **COMP-03**: components/grounding-service.md documents MedGemma integration, UMLS MCP tools, grounding strategy, and configuration
- [ ] **COMP-04**: components/hitl-ui.md documents React component structure, state management, key screens, and hooks

### Data Models & State

- [ ] **DATA-01**: data-models.md documents database schema (Protocol, Criteria, CriteriaBatch, Entity, Review, AuditLog) with field descriptions and relationships
- [ ] **DATA-02**: data-models.md documents LangGraph state (ExtractionState TypedDict, GroundingState TypedDict) with field descriptions and data flow

### Implementation Status

- [ ] **STAT-01**: implementation-status.md contains feature status table marking each feature as Stable, Beta, or Stubbed
- [ ] **STAT-02**: implementation-status.md contains test coverage analysis comparing src vs tests across all services

### Code Tour

- [ ] **TOUR-01**: code-tour.md contains 5+ "slides" following the protocol lifecycle from upload to review
- [ ] **TOUR-02**: Each code tour slide includes: title, user story, code location (file path), relevant code snippet, and explanation of why it matters

## v1.0 Requirements (Archived)

All 22 v1.0 requirements shipped. See .planning/MILESTONES.md for details.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Video walkthroughs | Expensive to maintain, validate text-first approach |
| Real-time collaborative editing | Over-engineering for documentation, use git workflow |
| Auto-translation | Machine translation dangerous for technical/medical content |
| Live code execution in docs | Security risk, high complexity |
| API auto-generation | Defer until API stabilizes post-pilot |
| Documentation versioning (mike) | Single version until product has releases |
| PDF export per section | Web-first, validate before adding |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| INFRA-01 | Phase 8 | Pending |
| INFRA-02 | Phase 8 | Pending |
| INFRA-03 | Phase 8 | Pending |
| ARCH-01 | Phase 9 | Pending |
| ARCH-02 | Phase 9 | Pending |
| DATA-01 | Phase 9 | Pending |
| DATA-02 | Phase 9 | Pending |
| JOUR-01 | Phase 10 | Pending |
| JOUR-02 | Phase 10 | Pending |
| COMP-01 | Phase 11 | Pending |
| COMP-02 | Phase 11 | Pending |
| COMP-03 | Phase 11 | Pending |
| COMP-04 | Phase 11 | Pending |
| STAT-01 | Phase 12 | Pending |
| STAT-02 | Phase 12 | Pending |
| TOUR-01 | Phase 12 | Pending |
| TOUR-02 | Phase 12 | Pending |

**Coverage:**
- v1.1 requirements: 17 total
- Mapped to phases: 17
- Unmapped: 0

---
*Requirements defined: 2026-02-12*
*Last updated: 2026-02-12 after roadmap creation*
