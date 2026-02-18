# Requirements: Clinical Trial Criteria Extraction System

**Defined:** 2026-02-17
**Core Value:** Clinical researchers can upload a protocol PDF and get accurately extracted, UMLS-grounded eligibility criteria that they can review and approve in a single workflow — replacing manual extraction that takes hours per protocol.

## v2.1 Requirements

Requirements for E2E Testing & Quality Evaluation milestone.

### E2E Testing

- [ ] **E2E-01**: E2E test can upload a real PDF from data/ and receive extracted criteria via the full Docker Compose pipeline
- [ ] **E2E-02**: E2E test verifies extracted criteria have inclusion and exclusion sections populated
- [ ] **E2E-03**: E2E test verifies entities are grounded with non-zero confidence for medical terms
- [ ] **E2E-04**: E2E tests use pytest marker `@pytest.mark.e2e` and skip when Docker Compose is not running
- [ ] **E2E-05**: E2E test fixtures manage test protocol cleanup after each run
- [ ] **E2E-06**: E2E test establishes a regression baseline (expected min criteria count, min entity count per test PDF)

### Quality Evaluation

- [ ] **QUAL-01**: Quality script runs the pipeline on 2-3 sample PDFs from data/ and collects results
- [ ] **QUAL-02**: Report includes per-protocol stats: criteria count, entity count, CUI rate, grounding method distribution
- [ ] **QUAL-03**: Report includes aggregate stats: mean/median confidence, overall CUI rate, entity type distribution
- [ ] **QUAL-04**: Report includes confidence distribution breakdown (0-0.5, 0.5-0.7, 0.7-0.9, 0.9-1.0)
- [ ] **QUAL-05**: Report includes per-terminology-system grounding success (UMLS, SNOMED, RxNorm, ICD-10, LOINC, HPO)
- [ ] **QUAL-06**: Report output is a structured markdown file with tables
- [ ] **QUAL-07**: Report includes LLM heuristic assessment of extraction completeness and grounding accuracy (no ground truth — LLM judges quality with reasoning)

### Bug Catalog

- [ ] **BUG-01**: Report catalogs ungrounded entities (entities with no CUI and no terminology codes)
- [ ] **BUG-02**: Report catalogs pipeline errors (extraction failures, grounding timeouts, parse errors)
- [ ] **BUG-03**: Report catalogs structural issues (criteria without entities, entities without criteria)
- [ ] **BUG-04**: Problems are categorized by severity (critical/warning/info) and type
- [ ] **BUG-05**: Bug catalog includes actionable recommendations per issue category

### E2E Bug Fixes (Gap Closure)

- [ ] **FIX-B3**: Parse node decomposes criterion sentences into discrete medical entities before grounding (not full sentences)
- [ ] **FIX-B4**: Entities have correct types (Medication, Condition, Lab, Procedure, Demographic) — not all "Condition"
- [ ] **FIX-B5**: Entity text is the specific medical term (e.g., "eGFR"), not the full criterion sentence
- [ ] **FIX-B12**: Docker Compose mounts GCP credentials for MedGemma/Vertex AI; auth failure falls back gracefully
- [x] **FIX-B14**: MLflow traces are never stuck IN_PROGRESS (timeout + try/finally span closure)
- [ ] **FIX-B15**: UMLS search validates queries client-side, retries on 502/503, circuit breaker for sustained failures
- [x] **FIX-B13**: Upload directory persisted via Docker named volume across container restarts
- [ ] **FIX-B7**: Dashboard Recent Activity shows last 20 audit log entries
- [ ] **FIX-B6**: Protocol list deduplicates re-uploaded protocols
- [ ] **FIX-B8**: Dead Letter protocols have Retry and Archive action buttons

## Future Requirements

### MLFlow Observability (v2.2)

- **MLFL-01**: MLFlow tracks per-node execution duration within the pipeline
- **MLFL-02**: MLFlow tracks individual tool invocations (UMLS search, NLM API calls, MedGemma inference)
- **MLFL-03**: MLFlow tracks grounding decisions per entity (search terms tried, candidates evaluated, final selection)
- **MLFL-04**: MLFlow dashboard shows quality metrics aggregated across pipeline runs

## Out of Scope

| Feature | Reason |
|---------|--------|
| CI/CD integration of E2E tests | Docker Compose E2E tests are too slow/expensive for CI — run locally |
| Performance benchmarking | Focus is quality metrics, not latency optimization |
| Golden dataset curation | Would require domain expert annotation — defer to v3 |
| Automated regression prevention | Manual baseline comparison sufficient for pilot |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| E2E-01 | Phase 37 | Pending |
| E2E-02 | Phase 37 | Pending |
| E2E-03 | Phase 37 | Pending |
| E2E-04 | Phase 36 | Pending |
| E2E-05 | Phase 36 | Pending |
| E2E-06 | Phase 37 | Pending |
| QUAL-01 | Phase 38 | Pending |
| QUAL-02 | Phase 38 | Pending |
| QUAL-03 | Phase 38 | Pending |
| QUAL-04 | Phase 38 | Pending |
| QUAL-05 | Phase 38 | Pending |
| QUAL-06 | Phase 38 | Pending |
| QUAL-07 | Phase 38 | Pending |
| BUG-01 | Phase 39 | Pending |
| BUG-02 | Phase 39 | Pending |
| BUG-03 | Phase 39 | Pending |
| BUG-04 | Phase 39 | Pending |
| BUG-05 | Phase 39 | Pending |
| FIX-B3 | Phase 41 | Pending |
| FIX-B4 | Phase 41 | Pending |
| FIX-B5 | Phase 41 | Pending |
| FIX-B12 | Phase 41 | Pending |
| FIX-B14 | Phase 42 | Complete |
| FIX-B15 | Phase 42 | Pending |
| FIX-B13 | Phase 42 | Complete |
| FIX-B7 | Phase 43 | Pending |
| FIX-B6 | Phase 43 | Pending |
| FIX-B8 | Phase 43 | Pending |

**Coverage:**
- v2.1 requirements: 28 total
- Mapped to phases: 28
- Unmapped: 0

---
*Requirements defined: 2026-02-17*
*Last updated: 2026-02-18 after gap closure phases 41-43 added from E2E Test Report*
