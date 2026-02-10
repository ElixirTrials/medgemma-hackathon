# Project Research Summary

**Project:** Clinical Trial Protocol Criteria Extraction System
**Domain:** Healthcare AI / Medical NLP
**Researched:** 2026-02-10
**Confidence:** HIGH

## Executive Summary

This system extracts and standardizes eligibility criteria from clinical trial protocol PDFs using AI-powered document understanding, medical entity recognition, and UMLS concept grounding, validated through human-in-the-loop (HITL) review workflows. The recommended approach uses Google Cloud infrastructure (Vertex AI for MedGemma models, Gemini for document extraction, GCS for PDF storage) with LangGraph orchestrating two separate agent workflows: extraction (agent-a) and grounding (agent-b), coordinated via event-driven architecture. The HITL review interface is the core value proposition—clinical researchers validate AI outputs through side-by-side PDF viewing, enabling efficient review while maintaining medical accuracy.

Critical risks center on AI reliability and data complexity. LLM hallucination rates of 15-55% for medical concept mapping require mandatory UMLS validation before database storage—no extracted SNOMED/UMLS code should be trusted without verification. PDF quality degradation (fax artifacts, scans) causes 38.8% F1 score drops, necessitating upfront quality detection and routing. Medical criteria contain nested temporal/conditional logic that gets lost in extraction ("diagnosed >5 years ago unless controlled") requiring structured schemas from day one. Inter-annotator variance in HITL review destroys model trust if annotation guidelines aren't established before the first review session.

The recommended build order follows architectural dependencies: infrastructure and data models first (PostgreSQL, SQLModel, GCS setup), then protocol upload, extraction workflow, HITL review UI, grounding workflow, and entity approval UI. This sequence allows each phase to deliver standalone value while building toward the complete pipeline. Plan for 6-7 weeks from infrastructure to production-hardened system with ~50 protocol pilot capacity.

## Key Findings

### Recommended Stack

The stack centers on Google Cloud ecosystem with specialized medical AI tooling. For PDF processing, pymupdf4llm (0.2.9) provides LLM-optimized extraction with table detection and layout preservation, specifically designed for clinical documents. Medical AI leverages LangExtract (1.1.1) for clinical entity extraction with source grounding, MedGemma 1.5 (4B) via Vertex AI for entity recognition, and MedCAT (2.5.3) for UMLS/SNOMED grounding. HITL workflows use LangGraph (1.0.8) with first-class interrupt/resume support for approval workflows, integrated with FastAPI (>=0.128.0) REST gateway and SQLModel (>=0.0.31) for clinical data integrity.

**Core technologies:**
- **pymupdf4llm** (0.2.9): LLM-optimized PDF extraction — purpose-built for clinical protocols with markdown conversion, table detection, multi-column support. Superior to raw PyMuPDF for AI pipelines.
- **LangExtract** (1.1.1): Clinical entity extraction — Google's healthcare library providing source grounding (maps extractions to PDF locations), chunking for long documents, optimized for clinical notes. Replaces ad-hoc prompt engineering.
- **LangGraph** (1.0.8): HITL orchestration — standard for 2026 HITL with interrupt() for approval workflows, state persistence, and audit trails. Enables review-approve-reject patterns.
- **MedGemma** (1.5-4b): Medical entity recognition — Google Health AI model deployed on Vertex AI for extracting conditions, medications, demographics from criteria text.
- **MedCAT** (2.5.3): UMLS/SNOMED grounding — production-ready library linking entities to SNOMED-CT UK Clinical + UMLS 2024AA. Enables concept normalization.
- **google-cloud-storage** (3.9.0): PDF storage — official library with resumable uploads, signed URLs for large files, versioning for protocol PDFs.
- **authlib** (1.6.7): Google OAuth — production-ready OAuth 2.0/OpenID Connect for clinical researcher authentication.

**Critical versions:**
- PyMuPDF >=1.24.0 required by pymupdf4llm (auto-installed)
- google-cloud-aiplatform >=1.70.0 for Vertex AI SDK (template has 1.130.0)
- LangGraph 1.0.8 for stable HITL API (template has 1.0.6+)

**What NOT to use:**
- PyPDF2 (deprecated 2023), pypdf standalone (lacks LLM optimization), pdfminer.six (brittle on complex layouts)
- Manual prompt engineering for entity extraction (no source grounding, poor chunking)
- Custom state machines for HITL (reinventing LangGraph)
- Firebase Auth (vendor lock-in when template already uses Google Cloud)

### Expected Features

Research reveals a clear MVP boundary for the 50-protocol pilot. Table stakes features include PDF upload with GCS storage, structured criteria extraction (inclusion/exclusion separation), entity recognition in criteria text, UMLS/SNOMED concept normalization, HITL review workflow (approve/reject/modify), audit trail for changes, user authentication, batch processing, basic quality metrics, and full-text search over criteria. Key differentiators are side-by-side PDF viewer with extracted criteria (eliminates context switching), pre-annotation with confidence scores (prioritizes review), and inline entity linking to UMLS browser (eliminates manual lookups). These differentiators reduce review time from hours to <20 minutes per protocol.

**Must have (table stakes):**
- PDF protocol upload & storage — standard workflow entry point
- Structured criteria extraction (inclusion/exclusion) — core functionality using Gemini structured output
- Medical entity recognition in criteria text — MedGemma via Vertex AI before grounding
- UMLS/SNOMED concept normalization — medical correctness requires standard terminologies
- HITL review workflow (approve/reject/modify) — non-negotiable for AI validation
- Side-by-side PDF viewer — major usability win, reduces context switching
- Audit trail for all changes — regulatory/compliance expectation
- Google OAuth authentication — identity management for clinical researchers
- Confidence scores for extractions — prioritizes reviewer attention (differentiator)
- Full-text search over criteria — find similar criteria across protocols

**Should have (competitive):**
- Batch approval by criteria type — reduces review burden after pattern confidence established (trigger: >100 protocols)
- Inline UMLS browser links — deep linking to concept pages (trigger: reviewers request faster lookups)
- Export to OMOP CDM format — enables downstream EHR integration (trigger: downstream system confirmed)
- Quality metrics dashboard — aggregate F1/precision/recall (trigger: measure improvement over time)

**Defer (v2+):**
- Historical criteria similarity (vector search) — requires vector DB, defer until >500 protocols
- Criteria template library — defer until larger corpus to identify patterns
- Patient matching from EHR — separate product scope, out of scope for extraction system
- Multi-tenant isolation — pilot is single research team
- Real-time collaborative editing — adds complexity (CRDTs, WebSockets) for minimal pilot value

**Anti-features to avoid:**
- Automatic approval without review — false positives dangerous in medical NLP
- Custom terminology beyond UMLS — breaks interoperability
- Mobile app for review — dense medical text inadequate for small screens
- Free-text criteria without structure — unusable for downstream systems

**Quality gates:**
- Entity extraction F1 score >85% (EliIE achieved 84-90%, AutoCriteria 89.42%)
- UMLS grounding accuracy >80% exact match
- Time per protocol review <20 minutes (vs hours for manual extraction)
- Pre-annotation acceptance rate >70% (validates AI quality)

### Architecture Approach

The system follows event-driven microservices architecture with two independent LangGraph agent workflows coordinated via transactional outbox pattern. Agent-a (extraction) handles protocol ingestion from GCS and Gemini-based criteria extraction, while agent-b (grounding) processes extracted criteria for MedGemma entity recognition and UMLS MCP grounding. Workflows communicate asynchronously via PostgreSQL shared database and event publishing, enabling failure isolation (extraction succeeds even if grounding fails), independent scaling (extraction is I/O-bound, grounding is compute-bound), and retry without reprocessing.

**Major components:**
1. **api-service** (FastAPI REST gateway) — Protocol upload with GCS signed URLs, HITL review endpoints, event publishing to outbox, Google OAuth authentication, orchestration of agent workflows
2. **agent-a-service** (Extraction workflow) — LangGraph StateGraph with nodes for protocol ingestion (GCS fetch), criteria extraction (Gemini Document AI), structure parsing (inclusion/exclusion separation), and review queue persistence
3. **agent-b-service** (Grounding workflow) — LangGraph StateGraph with nodes for entity extraction (MedGemma NER), UMLS grounding (MCP server calls), SNOMED mapping, and confidence validation
4. **hitl-ui** (React/Vite SPA) — Side-by-side PDF viewer, editable criteria cards, entity approval with SNOMED badges, real-time updates via WebSocket
5. **UMLS MCP Server** — Model Context Protocol server exposing UMLS Metathesaurus tools (concept search, semantic type prediction, concept linking) for agent-b grounding calls
6. **PostgreSQL** — Shared data store with SQLModel schemas (Protocol, Criteria, Entity, Review, OutboxEvent), full-text search on criteria, transactional outbox for event-driven coordination
7. **GCS Bucket** — PDF storage with versioning, quality metrics metadata, signed URLs for browser upload

**Key architectural patterns:**
- **LangGraph agent orchestration**: Workflows as DAGs with explicit state management, conditional branching, built-in persistence/checkpointing
- **Event-driven microservices with outbox**: Atomic persistence + event publishing, eventual consistency, guaranteed event delivery
- **HITL review workflow**: AI pre-screens and structures data, humans validate at key decision points, feedback loop for model improvement
- **MCP for external knowledge**: UMLS ontology access abstracted via MCP tools, decoupling medical knowledge from agent code
- **Separation of extraction and grounding**: Independent scaling, failure isolation, clear responsibility boundaries

**Data flow:**
1. User uploads PDF → React calls api-service → GCS signed URL → browser uploads directly to GCS → Protocol record created → ProtocolUploaded event published
2. agent-a receives event → fetches PDF from GCS → Gemini extracts criteria → parses into inclusion/exclusion → saves CriteriaBatch (status=pending_review) → publishes CriteriaExtracted event
3. HITL UI displays review queue → clinical researcher edits/approves → api-service updates status → publishes ReviewCompleted event
4. agent-b receives CriteriaExtracted → loads from DB → MedGemma extracts entities → UMLS MCP grounds to SNOMED → saves with confidence scores → publishes EntitiesGrounded event
5. HITL UI displays entities with SNOMED codes → reviewer approves grounding → final approval

### Critical Pitfalls

Eight critical pitfalls emerged from research, with clear prevention strategies and phase assignments. The most dangerous are LLM hallucination in medical concept mapping (15-55% hallucination rate requires UMLS validation before storage), PDF quality degradation (38.8% F1 drop on fax-degraded documents necessitates quality detection before extraction), and criteria complexity loss (temporal/conditional logic lost during extraction requires structured schemas from day one). These must be addressed in Phase 0-1 infrastructure—cannot defer to later phases.

1. **LLM Hallucination in Medical Concept Mapping** — Models generate nonexistent UMLS/SNOMED codes (15-55% rate). Prevention: validate every code against UMLS API before database storage, set confidence thresholds (<0.85 routes to HITL), use MedGemma semantic type prediction to filter candidates. Address in Phase 1.

2. **PDF Quality Degradation Breaking OCR** — Fax/scan distortions cause 38.8% F1 score drop. Prevention: pre-process all PDFs through quality detection, flag low-quality for enhanced OCR, test on fax-degraded samples during development. Address in Phase 0.

3. **Criteria Complexity and Temporal Context Loss** — Nested conditions and temporal constraints ("diagnosed >5 years ago unless controlled") get flattened. Prevention: structured output schemas with explicit temporal/conditional fields, side-by-side review UI to validate preservation. Address in Phase 1.

4. **Inter-Annotator Variance Destroying Model Trust** — Inconsistent HITL review standards poison training data. Prevention: annotation guidelines BEFORE first review, calibration sessions, track Cohen's kappa weekly (>0.8 target), flag inconsistencies. Address in Phase 2.

5. **Active Learning Selecting Uninformative Noisy Samples** — Uncertainty sampling surfaces corrupted PDFs, not informative examples. Prevention: hybrid strategy (uncertainty + diversity + quality filters), filter low OCR confidence before selection, 20% random sampling. Address in Phase 2.

6. **Negation and Assertion Detection Failures** — "No history of diabetes" extracted as positive finding. Prevention: assertion detection as separate pipeline stage (PRESENT, ABSENT, HYPOTHETICAL, HISTORICAL), validate negation recall, show assertion status in HITL UI. Address in Phase 1.

7. **Protocol Structure Variability Across Sponsors** — Extraction trained on NIH templates fails on pharma protocols. Prevention: collect diverse templates (~50 protocols across sponsors) BEFORE training, template detection routing, layout-aware parsing. Address in Phase 0.

8. **UMLS Coverage Gaps for Novel Therapies** — Only 44% of outcome concepts fully covered, novel drugs/biomarkers unmappable. Prevention: tiered grounding strategy (exact match → semantic similarity → expert review), store free-text + nearest neighbor, don't block on failed grounding. Address in Phase 1.

**Additional patterns to avoid:**
- Storing PDFs in PostgreSQL (bloat, slow backups) → use GCS with signed URLs
- Synchronous agent invocation from API (30-60s timeouts) → event-driven async
- Monolithic LangGraph workflow (tight coupling) → split extraction and grounding
- Missing confidence thresholds (trust all AI outputs) → validate and route by confidence

## Implications for Roadmap

Based on research, the roadmap should follow architectural dependency order with 7 distinct phases. Each phase delivers standalone value while building toward the complete pipeline, with clear handoff points between phases.

### Phase 0: Infrastructure & Data Models (Week 1)
**Rationale:** Foundation for all services. Establishes data contracts (SQLModel schemas for Protocol, Criteria, Entity, Review, OutboxEvent), database migrations, GCS buckets, and local development environment. No phase can begin without shared models and storage.

**Delivers:**
- `libs/shared/models.py` with SQLModel schemas
- `libs/events-py/models.py` with event definitions
- `services/api-service` skeleton with PostgreSQL, Alembic migrations
- `infra/docker-compose.yml` for local PostgreSQL
- GCS bucket configuration with quality metadata schema

**Addresses:**
- Pitfall 7 (Protocol structure variability) — diverse template collection during dataset prep
- Pitfall 2 (PDF quality) — quality metrics schema in GCS metadata
- Foundation for all table stakes features

**Avoids:**
- Technical debt from schema changes mid-development
- Protocol structure variability by collecting diverse samples upfront
- PDF quality issues by establishing quality detection infrastructure

**Research needs:** Standard patterns (PostgreSQL setup, SQLModel, Alembic). Skip research-phase.

---

### Phase 1: Protocol Upload & Storage (Week 1-2)
**Rationale:** User entry point. Cannot extract criteria without protocols in system. GCS integration isolated from AI dependencies, making it early validation milestone.

**Delivers:**
- `services/api-service/routers/protocols.py` with POST /protocols/upload, GET /protocols
- `services/api-service/services/gcs.py` with signed URL generation
- `apps/hitl-ui` basic scaffold with upload form and GCS direct upload
- PDF quality detection and metadata tagging

**Addresses:**
- Protocol upload (table stakes)
- PDF storage in GCS (table stakes)
- Pitfall 2 prevention (quality detection before extraction)

**Uses:** google-cloud-storage (3.9.0), FastAPI (0.128.0+), React/Vite

**Research needs:** Standard patterns (GCS signed URLs, FastAPI). Skip research-phase.

---

### Phase 2: Extraction Workflow (agent-a) (Week 2-3)
**Rationale:** Core value proposition. Delivers structured criteria from unstructured protocols. Independent of grounding workflow—can validate extraction quality before building entity recognition.

**Delivers:**
- `libs/inference/loaders.py` with Gemini client initialization
- `services/agent-a-service/graph.py` with LangGraph StateGraph
- `services/agent-a-service/nodes.py` (ingest, extract, parse, queue)
- Event publishing (ProtocolUploaded) and subscription
- Structured criteria schemas with temporal/conditional fields

**Addresses:**
- Structured criteria extraction (table stakes)
- Pitfall 1 prevention (validation hooks in extraction)
- Pitfall 3 prevention (structured schemas for complexity)
- Pitfall 6 prevention (assertion detection in pipeline)
- Batch protocol processing (table stakes)

**Implements:**
- LangGraph agent orchestration pattern
- Event-driven microservices pattern (extraction workflow)

**Uses:** LangGraph (1.0.8), LangExtract (1.1.1), pymupdf4llm (0.2.9), Gemini via Vertex AI

**Research needs:** **NEEDS RESEARCH-PHASE** for LangExtract integration patterns, Gemini structured output schema design, temporal/conditional criteria extraction strategies. Complex integration with limited production examples.

---

### Phase 3: HITL Review UI (Week 3-4)
**Rationale:** Enables human validation before grounding. Provides immediate user value (review and correct AI extractions). Critical for HITL workflow and model improvement feedback loop.

**Delivers:**
- `services/api-service/routers/criteria.py` with GET /criteria, PATCH /criteria/:id
- `services/api-service/routers/reviews.py` with POST /reviews/:batch_id/approve
- `apps/hitl-ui/pages/CriteriaReview.tsx` with review queue
- `apps/hitl-ui/components/CriteriaCard.tsx` (display/edit)
- Side-by-side PDF viewer component
- WebSocket integration for real-time updates
- Annotation guidelines documentation

**Addresses:**
- HITL review workflow (table stakes, core value prop)
- Side-by-side PDF viewer (differentiator)
- Audit trail for reviews (table stakes)
- Pitfall 4 prevention (annotation guidelines before first review)
- Confidence scores display (differentiator)

**Implements:**
- HITL review workflow pattern
- Side-by-side comparison UX

**Uses:** React/Vite, FastAPI WebSocket, SQLModel for audit logging

**Research needs:** Standard patterns (React forms, WebSocket). Skip research-phase.

---

### Phase 4: Grounding Workflow (agent-b) & UMLS MCP (Week 4-5)
**Rationale:** Grounding workflow separate from extraction. Requires MedGemma deployment (compute-intensive) and UMLS MCP server (external dependency). Can start after extraction proves valuable.

**Delivers:**
- UMLS MCP Server deployment (custom MCP server with UMLS Metathesaurus)
- `libs/inference/loaders.py` with MedGemma loader and MCP client
- `services/agent-b-service/graph.py` with LangGraph StateGraph
- `services/agent-b-service/nodes.py` (extract entities, ground, map, validate confidence)
- Event subscription for CriteriaExtracted
- Tiered grounding strategy (exact → similarity → expert review)

**Addresses:**
- Medical entity recognition (table stakes)
- UMLS/SNOMED grounding (table stakes)
- Pitfall 1 prevention (UMLS validation before storage)
- Pitfall 8 mitigation (tiered grounding for novel therapies)
- Confidence scoring (differentiator)

**Implements:**
- Separation of extraction and grounding pattern
- MCP for external knowledge pattern

**Uses:** MedGemma (1.5-4b via Vertex AI), MedCAT (2.5.3), MCP SDK, LangGraph (1.0.8)

**Research needs:** **NEEDS RESEARCH-PHASE** for UMLS MCP server setup (custom deployment), MedGemma deployment on Vertex AI (GPU configuration, batch optimization), MedCAT model selection and UMLS version compatibility. Complex medical AI integration.

---

### Phase 5: Entity Approval UI (Week 5-6)
**Rationale:** Closes HITL loop. Clinical researchers validate SNOMED mappings. Feedback enables model improvement. Completes end-to-end pipeline.

**Delivers:**
- `services/api-service/routers/entities.py` with GET /entities, PATCH /entities/:id
- `apps/hitl-ui/pages/EntityApproval.tsx` with entity list
- `apps/hitl-ui/components/EntityTag.tsx` with SNOMED badge
- `apps/hitl-ui/components/ApprovalWorkflow.tsx` for bulk approve/reject
- Inline UMLS browser links (differentiator)

**Addresses:**
- Entity validation (completes HITL workflow)
- Inline UMLS links (differentiator)
- Full-text search over criteria (table stakes)
- Google OAuth authentication (table stakes)

**Uses:** React/Vite, PostgreSQL full-text search, authlib (1.6.7)

**Research needs:** Standard patterns (React UI, PostgreSQL FTS). Skip research-phase.

---

### Phase 6: Production Hardening (Week 6-7)
**Rationale:** System works end-to-end, now make production-ready. Observability critical for debugging distributed workflows. Caching reduces costs and latency.

**Delivers:**
- Retry logic with exponential backoff (tenacity)
- Dead-letter queues for failed events
- Structured logging, Cloud Trace, error tracking
- Caching (criteria, entities, MCP results) with diskcache
- Input validation, rate limiting, API key rotation
- Terraform for GCP infrastructure (Cloud Run, Cloud SQL, GCS, Pub/Sub)
- Load testing (100 concurrent uploads)
- Security scan and PHI redaction validation

**Addresses:**
- System reliability targets (>95% pipeline success, <5min processing)
- Quality metrics (table stakes)
- Pitfall 5 prevention (active learning validation via A/B test)
- Performance traps (N+1 queries, synchronous processing)
- Security mistakes (encryption, PHI logging)

**Uses:** tenacity (8.2.0+), diskcache (5.6.3+), Terraform, Cloud Monitoring

**Research needs:** Standard patterns (observability, caching, Terraform). Skip research-phase.

---

### Phase Ordering Rationale

**Why this order:**
- **Phase 0 first:** All services depend on shared models and database schema. GCS bucket required for upload. Cannot parallelize with other phases.
- **Phase 1 before 2:** Need protocols in system before extraction. GCS integration simpler than LangGraph, validates infrastructure.
- **Phase 2 before 3:** HITL UI needs extracted criteria to review. Extraction workflow provides data for UI development.
- **Phase 3 before 4:** Validate extraction quality with human review before building expensive grounding infrastructure. Annotation guidelines established during Phase 3 inform Phase 4 confidence thresholds.
- **Phase 4 after 3:** Grounding requires compute (MedGemma GPU), external dependency (UMLS MCP). Can defer until extraction proves valuable.
- **Phase 5 after 4:** Entity approval UI needs grounded entities. Completes HITL loop.
- **Phase 6 last:** Production hardening requires complete pipeline to test end-to-end, identify bottlenecks, validate scaling.

**How this grouping avoids pitfalls:**
- PDF quality detection in Phase 0 prevents Pitfall 2 cascading through later phases
- Structured schemas in Phase 2 prevent Pitfall 3 (cannot retrofit complex criteria later)
- Annotation guidelines in Phase 3 prevent Pitfall 4 (inter-annotator variance poisons training data if deferred)
- UMLS validation in Phase 4 prevents Pitfall 1 (hallucination errors compound if allowed into database)
- Production hardening in Phase 6 addresses Pitfall 5 (active learning) via A/B testing with full pipeline

**Critical path dependencies:**
```
Phase 0 (Infrastructure)
    ↓
Phase 1 (Protocol Upload) → Phase 2 (Extraction)
                                ↓
                            Phase 3 (Review UI)
                                ↓
                            Phase 4 (Grounding)
                                ↓
                            Phase 5 (Entity Approval)
                                ↓
                            Phase 6 (Hardening)
```

**Parallel work opportunities:**
- Phase 1 and 2 can partially overlap after GCS integration complete (PDF upload functional, extraction development starts)
- Phase 4 UMLS MCP server deployment can start during Phase 3 UI development (separate infrastructure track)

### Research Flags

**Phases needing deeper research during planning:**

- **Phase 2 (Extraction Workflow):** Complex integration of LangExtract, Gemini structured output, and temporal/conditional criteria extraction. Limited production examples for medical protocol parsing. Need research on:
  - LangExtract source grounding API patterns
  - Gemini structured output schema design for nested medical criteria
  - Temporal constraint extraction strategies (handling "within 30 days," "prior to randomization")
  - Assertion detection integration (negation, hypothetical, historical)

- **Phase 4 (Grounding Workflow):** Medical AI deployment and UMLS MCP server setup. Complex domain-specific integration. Need research on:
  - UMLS MCP server deployment architecture (custom vs existing implementations)
  - MedGemma deployment on Vertex AI (GPU instance types, batch optimization, cost management)
  - MedCAT model selection for UMLS 2024AA + SNOMED-CT UK Clinical 40.2
  - Tiered grounding strategy implementation (exact match → semantic similarity → fallback)

**Phases with standard patterns (skip research-phase):**

- **Phase 0 (Infrastructure):** Standard PostgreSQL, SQLModel, Alembic, GCS setup. Well-documented in template.
- **Phase 1 (Protocol Upload):** Standard FastAPI + GCS signed URLs. Template includes GCS patterns.
- **Phase 3 (Review UI):** Standard React forms, WebSocket integration. UI patterns well-established.
- **Phase 5 (Entity Approval UI):** Standard React UI patterns, PostgreSQL full-text search.
- **Phase 6 (Hardening):** Standard observability, caching, Terraform. Template includes tenacity, diskcache.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | All versions verified from PyPI Feb 2026. pymupdf4llm, LangExtract, MedCAT explicitly designed for clinical text. LangGraph 1.0 GA with first-class HITL support. |
| Features | MEDIUM-HIGH | High confidence on HITL requirements (multiple industry sources, existing template). Medium confidence on differentiating features (limited specific UX research for clinical trial review). Small sample of commercial platform features. |
| Architecture | HIGH | LangGraph multi-agent patterns well-documented. Event-driven microservices standard. HITL workflows validated in Google Cloud docs. Medical entity grounding patterns from academic papers. |
| Pitfalls | HIGH | Hallucination rates documented in academic research. PDF quality degradation quantified (38.8% F1 drop). Inter-annotator agreement metrics from annotation platform literature. UMLS coverage gaps measured (44% outcome concepts). |

**Overall confidence:** HIGH

### Gaps to Address

**Commercial platform capabilities (LOW confidence):**
- Limited access to actual CTMS systems to evaluate UX patterns. Only public marketing pages and press releases available.
- Mitigation: Focus on documented pain points from research literature rather than feature parity with commercial systems. Validate with pilot users early (Phase 3).

**Novel therapy terminology handling (MEDIUM confidence):**
- UMLS coverage gaps documented (44% for outcomes), but specific strategy for local ontology extension needs validation.
- Mitigation: Track unmappable concept frequencies during Phase 4, establish threshold (>5 protocols) for local ontology additions, plan quarterly UMLS update process.

**Active learning strategy effectiveness (MEDIUM confidence):**
- Uncertainty sampling + diversity filters recommended, but specific implementation for clinical protocols lacks production validation.
- Mitigation: Implement A/B test during Phase 6 (active learning vs random sampling), validate 20%+ annotation time reduction before production use.

**Annotation guidelines specificity (MEDIUM confidence):**
- Inter-annotator agreement targets clear (Cohen's kappa >0.8), but specific edge cases for clinical trial criteria need empirical discovery.
- Mitigation: Conduct calibration sessions during Phase 3 with 10 diverse protocols, document disagreements, iterate guidelines before full pilot.

**MedGemma deployment optimization (MEDIUM confidence):**
- General Vertex AI patterns documented, but specific GPU instance sizing and batch optimization for MedGemma 1.5-4B needs empirical testing.
- Mitigation: Phase 4 research-phase should include load testing with protocol corpus, optimize batch size and GPU instances before production deployment.

**Temporal criteria extraction accuracy (MEDIUM confidence):**
- Research documents challenge (nested conditions, temporal constraints), but specific extraction schemas and validation strategies need development.
- Mitigation: Phase 2 research-phase should survey existing temporal constraint schemas (OMOP CDM temporal fields, EliIE temporal annotations) and test on complex oncology protocols.

## Sources

### Primary Sources (HIGH confidence)

**Technology Stack:**
- [pymupdf4llm PyPI](https://pypi.org/project/pymupdf4llm/) — Version 0.2.9, Jan 2026 release for RAG/LLM workflows
- [LangExtract GitHub](https://github.com/google/langextract) — Google's healthcare library, July 2025 release
- [LangGraph PyPI](https://pypi.org/project/langgraph/) — Version 1.0.8, Feb 2026 GA release with HITL support
- [MedCAT PyPI](https://pypi.org/project/medcat/) — Version 2.5.3, Jan 2026 release with UMLS 2024AA support
- [authlib PyPI](https://pypi.org/project/authlib/) — Version 1.6.7, Feb 2026 OAuth 2.0 library

**Medical NLP Research:**
- [AutoCriteria: LLM-powered eligibility extraction - PubMed 2023](https://pubmed.ncbi.nlm.nih.gov/37952206/) — 89.42% F1 score benchmark
- [EliIE: Clinical trial eligibility extraction - JAMIA 2017](https://academic.oup.com/jamia/article/24/6/1062/3098256) — 84-90% F1 scores, error type taxonomy
- [LLM Hallucination in Clinical Concept Mapping - JMIR 2025](https://medinform.jmir.org/2025/1/e71252) — 15-55% hallucination rates documented

**HITL Workflows:**
- [LangGraph Human-in-the-loop Deployment with FastAPI](https://shaveen12.medium.com/langgraph-human-in-the-loop-hitl-deployment-with-fastapi-be4a9efcd8c0) — Implementation patterns
- [Human-in-the-Loop AI Complete Guide 2026 - Parseur](https://parseur.com/blog/human-in-the-loop-ai) — Best practices, 80% enterprises using HITL
- [Google Cloud HITL Documentation](https://docs.google.com/document-ai/docs/hitl) — Official patterns

**UMLS and Medical Grounding:**
- [UMLS and SNOMED-CT for Outcome Concepts - JAMIA](https://academic.oup.com/jamia/article/30/12/1895/7249289) — 44% coverage measurement
- [Improving Medical Entity Linking - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC8952339/) — Semantic type prediction strategies
- [Clinical Trial Knowledge Base - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC8407851/) — 87,504+ standard concepts

**PDF Processing:**
- [Document Parsing Challenges - arXiv 2026](https://arxiv.org/html/2410.21169v4) — 38.8% F1 drop on fax-degraded PDFs
- [AI OCR Models Comparative Analysis](https://intuitionlabs.ai/pdfs/comparative-analysis-of-ai-ocr-models-for-pdf-to-structured-text.pdf) — Quality metrics

### Secondary Sources (MEDIUM confidence)

**Architecture Patterns:**
- [LangGraph Multi-Agent Orchestration Guide](https://latenode.com/blog/ai-frameworks-technical-infrastructure/langgraph-multi-agent-orchestration/langgraph-multi-agent-orchestration-complete-framework-guide-architecture-analysis-2025) — Framework patterns
- [Event-Driven Architecture Best Practices - IBM](https://developer.ibm.com/articles/eda-and-microservices-architecture-best-practices/) — Microservices coordination

**Clinical Trial Platforms:**
- [Mount Sinai AI Trial Matching Platform 2026](https://www.mountsinai.org/about/newsroom/2026/mount-sinai-launches-ai-powered-clinical-trial-matching-platform-to-expand-access-to-cancer-research) — Commercial platform features
- [Tempus Clinical Trial Matching](https://www.tempus.com/oncology/clinical-trial-matching/) — Feature comparison baseline

**Annotation Workflows:**
- [Data Annotation Trends 2026 - Humans in the Loop](https://humansintheloop.org/data-annotation-trends-2026-forecast-best-practices/) — Inter-annotator agreement targets
- [HITL Annotation Pipelines - V2 Solutions](https://www.v2solutions.com/whitepapers/hitl-annotation-pipelines-for-ai/) — Scalable annotation patterns

### Tertiary Sources (LOW confidence, needs validation)

**Commercial Platform UX:**
- Marketing pages for Tempus, Simplified Clinical — Feature lists only, cannot access actual systems
- Mitigation: Validate assumptions during Phase 3 pilot user interviews

**Future Feature Demand:**
- General trends (decentralized trials, representative enrollment mandates) from press releases
- Mitigation: Build extensible architecture, defer speculative features to v1.x/v2+

---
*Research completed: 2026-02-10*
*Ready for roadmap: Yes*
