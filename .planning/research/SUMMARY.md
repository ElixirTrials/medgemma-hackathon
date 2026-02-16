# Project Research Summary

**Project:** Clinical Trial Criteria Extraction Pipeline - v2.0 Consolidation & Multi-Terminology Grounding
**Domain:** Clinical trial criteria extraction with human-in-the-loop review
**Researched:** 2026-02-16
**Confidence:** HIGH

## Executive Summary

This system extracts structured eligibility criteria from clinical trial protocol PDFs using Gemini for extraction and MedGemma for entity grounding, then routes them through a human review interface. Current architecture splits extraction and grounding into two separate LangGraph services connected via outbox events, adding 2-5s latency and complexity with zero operational benefit (both run in the same process). Research confirms that **consolidation into a single 5-node pipeline** (ingest → extract → parse → ground → persist) eliminates the false microservice boundary while preserving all functionality.

The current UMLS-only grounding (SNOMED search via MCP subprocess) produces 0% confidence for all entities due to subprocess lifecycle failures and MedGemma 4b-it JSON parsing issues. Research identifies **entity-type-aware routing via direct API clients** (RxNorm for medications, ICD-10 for conditions, LOINC for lab tests, HPO for phenotypes) as the proven pattern used by commercial systems. ToolUniverse wraps these APIs but adds unnecessary complexity; building thin HTTP clients (50-100 lines each) provides better control and eliminates subprocess overhead. The hybrid approach (ToolUniverse tools for 60-70% of entities, UMLS for the rest) offers immediate improvements while maintaining coverage.

Key risks center on data integrity during consolidation: removing the outbox without replacing its retry mechanism creates a data loss window, and re-extraction without review protection destroys human corrections. The research identifies 10 critical pitfalls with proven mitigation strategies, including transactional pipeline execution, per-entity grounding (not batch-level fallback), and JSONB schema versioning to prevent frontend crashes on old data.

## Key Findings

### Recommended Stack

**Core insight:** The existing stack is sound. All required packages (google-genai, langgraph, pydantic) are already installed. The consolidation requires ZERO new major dependencies—just thin HTTP clients for terminology APIs.

**Core technologies:**
- **google-genai (>=1.55.0)** — Structured output for extraction AND entity extraction (move from MedGemma to Gemini for entity extraction to fix JSON parse failures)
- **langgraph (>=1.0.6)** — Flat graph consolidation pattern; subgraphs add unnecessary state transformation overhead for this sequential pipeline
- **RxNorm/LOINC/ICD-10/HPO direct API clients** — Entity-type-aware grounding; thin HTTP clients (not ToolUniverse MCP) eliminate subprocess overhead while accessing the same NLM APIs
- **Existing UMLS client (direct import, not MCP)** — Keep for Procedure/Biomarker grounding where ToolUniverse lacks coverage

**Critical recommendation:** Use Gemini with structured output for entity extraction (not MedGemma). MedGemma 4b-it lacks structured output support, causing the JSON parse failures that produce 0% confidence. Entity extraction is structured information extraction (identify spans, classify types), not medical reasoning—Gemini handles this well with proper prompts.

**What NOT to add:**
- ToolUniverse as runtime dependency (research toolkit with 211+ tools, not production-ready)
- MCP subprocess for grounding (5-15s startup overhead per batch)
- New LLM libraries (existing models cover all needs)

### Expected Features

Research categorizes features across 10 target areas. Priorities derived from user expectations, regulatory requirements (21 CFR Part 11), and corpus-building workflows.

**Must have (table stakes):**
- Fix grounding confidence (currently 0% for all entities) — regulatory blocker
- Dashboard pending count includes in-progress batches — users miss work
- Audit trail visibility — regulatory requirement
- Re-extraction preserves reviewed criteria — corpus quality depends on this
- Entity-type-aware terminology routing — medications to RxNorm, conditions to ICD-10, labs to LOINC
- Rationale prompt on reject actions — regulatory requirement

**Should have (competitive differentiators):**
- Merged extraction+grounding graph — eliminates 2-5s latency, simplifies debugging
- Multi-code resolution per entity — RxNorm + SNOMED + ICD-10 for interoperability
- Corpus export with AI vs human diff view — core value proposition for model evaluation
- Editor pre-loading from saved field_mappings — prevents data loss during editing
- Extraction determinism (temperature=0 + seed) — reproducibility for evaluation

**Defer (v2+):**
- Inter-annotator agreement tracking — needs dual-review workflow
- Selective per-criterion re-extraction — complex; batch-level sufficient for MVP
- HPO phenotype grounding — valuable for oncology but only ~10% of entities
- Pipeline consolidation into one Python package — keep packages separate, share graph

**Anti-features identified:**
- Fully merging extraction-service and grounding-service Python packages (destroys separation of concerns)
- Real-time streaming extraction progress (Gemini structured output isn't streamable)
- Auto-save structured edits on blur (pollutes audit trail)
- Required rationale for approve actions (kills throughput)

### Architecture Approach

**Decision: Single protocol-processor-service with flat 5-node graph.** The current two-service split provides zero decoupling value—both import the same DB engine, run in the same process, and the outbox between them is an intra-process message that adds 1-3 seconds and failure modes.

**Consolidated graph structure:**
```
START → ingest → extract → parse → ground → persist → END
```

**Major components:**
1. **ingest/extract/parse nodes** — Move unchanged from extraction-service; Gemini File API structured extraction
2. **ground node** — NEW; merges queue persistence + entity extraction + terminology routing; replaces both queue_node and medgemma_ground_node
3. **persist node** — Adapted from validate_confidence_node; Entity validation/persistence, batch status updates
4. **TerminologyRouter** — Entity-type-aware dispatch to RxNorm/LOINC/ICD-10/HPO/UMLS; thin HTTP clients (50-100 lines each)
5. **Unified PipelineState** — Single TypedDict with extraction + grounding fields; eliminates state duplication and redundant DB reads

**Critical architectural insight:** The ground node must persist criteria BEFORE entity extraction because criteria IDs are needed for entity-criteria linkage. Current architecture handles this via outbox (queue_node persists, outbox fires, grounding loads). Consolidated architecture handles it within a single node.

**Outbox pattern fate:**
- KEEP protocol_uploaded outbox (bridges user HTTP upload to async pipeline)
- REMOVE criteria_extracted outbox (no longer needed; grounding is in-graph)
- KEEP entities_grounded outbox (optional; for future downstream consumers)

**Integration strategy for ToolUniverse:**
Complement UMLS, don't replace. Build entity-type routing layer:
- Medication → RxNorm API (primary) + UMLS SNOMED (secondary)
- Condition → UMLS SNOMED (primary) + ICD-10 (secondary)
- Lab_Value → LOINC API (primary) + UMLS SNOMED (secondary)
- Procedure → UMLS SNOMED only (ToolUniverse lacks procedure tool)
- Demographic → ICD-10 for age/gender codes
- Biomarker → UMLS SNOMED (primary) + HPO (secondary)

**Data flow changes:**
- Current: 3 outbox events (protocol_uploaded, criteria_extracted, entities_grounded), redundant DB read (grounding re-loads criteria), 2-3s latency overhead
- Proposed: 1 required outbox event (protocol_uploaded), 1 optional (entities_grounded), zero redundant reads, ~0s overhead

### Critical Pitfalls

Research identified 10 critical pitfalls with proven mitigation strategies. Top 5 for roadmap planning:

1. **Outbox removal creates silent data loss window** — Removing the criteria_extracted outbox without replacing its atomicity guarantee creates a window where criteria persist but grounding never runs. **Mitigation:** Wrap entire pipeline (extract + ground + persist) in single transaction that only commits when ALL steps succeed, OR keep lightweight "grounding_needed" recovery mechanism.

2. **ToolUniverse MCP subprocess lifecycle causes grounding timeouts** — Each grounding call spawning new subprocess adds 5-15s startup overhead and creates zombie processes (same failure mode producing current 0% confidence). **Mitigation:** Use direct Python API clients (not MCP subprocess), OR run ToolUniverse as long-lived sidecar in docker-compose.

3. **Entity type mismatch between extraction and tool routing** — Extraction outputs `Condition`, `Medication`, `Lab_Value`, but ToolUniverse expects `DISEASE`, `MEDICATION`, `LAB_TEST`. Unmapped types silently dropped. **Mitigation:** Define canonical entity type mapping upfront; add explicit "unroutable" handling with logging.

4. **Dashboard pending count semantic confusion** — Dashboard shows "0 Pending" when batches exist with unreviewed criteria because it only counts `status='pending_review'` (transitions to `in_progress` after first review). **Mitigation:** Query batches with ANY unreviewed criteria (criteria-level check, not batch-level).

5. **Re-extraction without review protection destroys gold-standard data** — Running re-extraction creates new CriteriaBatch without checking if existing batch has reviews; human corrections become invisible. **Mitigation:** Add `is_locked` flag to batches with reviews; implement "diff view" showing old (reviewed) vs new (re-extracted) criteria side-by-side.

**Other critical pitfalls:**
- Audit trail entries created but invisible due to query scope mismatch (missing batch_id filter)
- Gemini extraction non-determinism undermines corpus comparison (add granularity instructions to prompt)
- JSONB schema evolution breaks old criteria on UI load (add schema_version field, run migration)
- ToolUniverse rate limits cascade across tools (per-tool rate limiting required)
- Pipeline state schema merge causes type safety regression (use minimal shared state, run mypy --strict)

## Implications for Roadmap

Based on combined research, the recommended phase structure prioritizes **bug fixes first** (grounding, audit, dashboard), then **consolidation with new grounding**, then **corpus tooling**. Pipeline consolidation is deferred to Phase 2 because it requires grounding to work first.

### Phase 1: Critical Bug Fixes & UX Polish
**Rationale:** Fix what's broken before adding complexity. Three critical bugs block regulatory compliance and user trust: 0% grounding confidence, empty audit trail, misleading dashboard pending count. These are LOW-complexity, HIGH-impact fixes.

**Delivers:**
- Grounding confidence >0% (debug MedGemma JSON parsing, UMLS MCP tool errors)
- Audit trail visible in Review page (add batch_id filter to API query)
- Dashboard pending count includes in-progress batches (criteria-level query)
- Visual distinction for reviewed vs pending criteria (left border colors)
- Rationale prompt on reject actions (required field in modal)

**Addresses features from FEATURES.md:**
- Bug fixes: Grounding confidence, audit trail, dashboard pending count
- UX improvements: Visual distinction, criteria search, sortable columns
- Rationale: Required for regulatory compliance

**Avoids pitfalls:**
- Dashboard pending count semantic confusion (Pitfall 4)
- Audit trail entries invisible (Pitfall 5)

**Complexity:** LOW (query changes, UI tweaks, MedGemma debugging)
**Duration:** 3-5 days
**Needs research-phase:** NO (all patterns established)

---

### Phase 2: Entity-Type-Aware Grounding & Pipeline Consolidation
**Rationale:** Grounding must work before consolidation makes sense. This phase merges the two biggest architectural changes: direct API grounding (replaces UMLS MCP subprocess) and pipeline consolidation (removes outbox hop). Both address the 0% confidence root cause and eliminate latency.

**Delivers:**
- TerminologyRouter with direct API clients (RxNorm, LOINC, ICD-10, HPO, UMLS)
- Entity-type routing (Medication→RxNorm, Condition→ICD-10, Lab_Value→LOINC, etc.)
- Consolidated 5-node graph (ingest → extract → parse → ground → persist)
- Multi-code resolution (store rxnorm_code, icd10_code, loinc_code, hpo_code per entity)
- Entity model extension with new code fields + Alembic migration
- Gemini-based entity extraction (replaces MedGemma to fix JSON parse failures)

**Uses stack elements from STACK.md:**
- google-genai with structured output for entity extraction
- langgraph flat graph consolidation
- Direct HTTP clients for RxNorm/LOINC/ICD-10/HPO APIs
- Existing UMLS client (direct import, not MCP)

**Implements architecture component:**
- Consolidated PipelineState
- TerminologyRouter with BaseTerminologyClient interface
- Ground node combining persistence + grounding
- Removal of criteria_extracted outbox event

**Avoids pitfalls:**
- Outbox removal data loss window (Pitfall 1) — wrap pipeline in single transaction
- ToolUniverse subprocess lifecycle failures (Pitfall 2) — use direct API clients
- Entity type mismatch (Pitfall 3) — define canonical mapping upfront
- Pipeline state type safety regression (Pitfall 10) — minimal shared state, mypy --strict

**Complexity:** HIGH (most complex phase; combines two architectural changes)
**Duration:** 10-14 days
**Needs research-phase:** YES — verify RxNorm/LOINC/ICD-10/HPO API response formats via test calls

**Sub-phase breakdown:**
1. Create protocol-processor skeleton (4-node graph without grounding) — LOW RISK
2. Build TerminologyRouter + direct API clients — MEDIUM RISK
3. Implement ground node (persistence + entity extraction + routing) — HIGH RISK
4. Implement persist node + Entity model migration — MEDIUM RISK
5. Integration switchover (update api-service imports) — LOW RISK
6. Cleanup (remove old services) — LOW RISK

---

### Phase 3: Editor Pre-Loading & Read-Mode Display
**Rationale:** With grounding working and multi-system codes stored, surface them in the UI. Editor pre-loading prevents data loss when reviewers navigate away; read-mode display shows entity codes as badges.

**Delivers:**
- Saved field_mappings pre-populate structured editor (fix buildInitialValues() priority)
- Read-mode field_mappings display as badges/chips (entity/relation/value triplets)
- Multi-terminology codes displayed per entity (RxNorm, ICD-10, LOINC badges)
- Graceful fallback for unstructured criteria (pre-v1.5 data)
- Visual distinction between AI-extracted and human-reviewed mappings (schema_version)

**Addresses features from FEATURES.md:**
- Editor pre-loading (table stakes)
- Read-mode display (table stakes)
- Multi-code resolution display (differentiator)

**Avoids pitfalls:**
- JSONB schema evolution breaks old criteria (Pitfall 8) — add schema_version, run migration

**Complexity:** MEDIUM (react-hook-form lifecycle, JSONB schema handling)
**Duration:** 4-6 days
**Needs research-phase:** NO (patterns established in CriterionCard.tsx)

---

### Phase 4: Re-Extraction Tooling & Review Protection
**Rationale:** With grounding stable and editor working, enable re-extraction for prompt iteration. Must implement review protection BEFORE allowing re-extraction on protocols with existing reviews.

**Delivers:**
- POST /protocols/{id}/reextract endpoint (publishes ProtocolUploaded event for existing file_uri)
- Review protection: is_locked flag on batches with reviewed criteria
- Re-extraction creates new batch alongside old (not replacing)
- UI button in protocol detail page with confirmation modal
- Extraction determinism improvements (temperature=0 + seed + granularity instructions)

**Addresses features from FEATURES.md:**
- Re-extraction tooling (table stakes)
- Deterministic extraction (table stakes)
- Review protection (must-have)

**Avoids pitfalls:**
- Re-extraction destroys gold-standard data (Pitfall 7) — is_locked flag + diff view
- Gemini non-determinism undermines corpus comparison (Pitfall 6) — prompt tightening

**Complexity:** MEDIUM (API endpoint + lock mechanism + UI integration)
**Duration:** 4-6 days
**Needs research-phase:** NO (patterns established)

---

### Phase 5: Corpus Comparison & Export
**Rationale:** With re-extraction working and multiple batches per protocol, build corpus comparison tools for AI evaluation. This is the payoff for all previous work—enabling systematic model improvement.

**Delivers:**
- Side-by-side diff view: AI extraction vs human correction (audit log based)
- Batch-level comparison: old batch vs new batch after re-extraction
- Export reviewed criteria as JSON/CSV corpus (criterion_text, ai_entities, human_entities)
- Metrics dashboard: agreement rate, modification frequency by category/entity_type
- Version-tagged corpus snapshots (extraction model version + prompt version)

**Addresses features from FEATURES.md:**
- Corpus comparison (table stakes)
- Corpus export (table stakes)
- Metrics dashboard (differentiator)

**Avoids pitfalls:**
- None directly; builds on stable foundation from previous phases

**Complexity:** MEDIUM-HIGH (audit log diff computation, fuzzy matching for re-extraction comparison)
**Duration:** 6-8 days
**Needs research-phase:** NO (corpus export formats are standard JSON/CSV)

---

### Phase Ordering Rationale

**Why bug fixes first:** Grounding confidence 0% is a regulatory blocker. Audit trail empty violates 21 CFR Part 11. Dashboard pending count misleads users. These must be fixed before adding new features.

**Why consolidation in Phase 2 (not Phase 1):** Consolidation requires grounding to work. The current 0% confidence issue must be debugged first to understand whether it's a MedGemma problem, UMLS MCP problem, or both. Once root cause is clear, consolidation can proceed with confidence.

**Why grounding + consolidation together:** Both address the same root cause (subprocess lifecycle failures causing 0% confidence). Fixing grounding with direct API clients naturally eliminates the MCP subprocess, which is 80% of what consolidation does. Doing them separately would mean refactoring the MCP code twice.

**Why editor pre-loading after grounding:** Multi-terminology codes must be stored (Phase 2) before they can be displayed (Phase 3). Editor pre-loading depends on having stable multi-code data to load.

**Why re-extraction after editor:** Re-extraction testing requires a working editor to verify that human corrections are preserved. Can't test review protection without reviews to protect.

**Why corpus comparison last:** Requires multiple extraction batches (re-extraction tooling from Phase 4), audit trail (Phase 1), and working editor (Phase 3). This is the "payoff" phase that depends on everything before it.

### Research Flags

**Phases needing deeper research during planning:**
- **Phase 2 (grounding):** Entity-type routing implementation needs test calls to RxNorm/LOINC/ICD-10/HPO APIs to verify response formats. Research confirmed APIs exist and are free, but exact request/response schemas need verification before building clients.
- **Phase 5 (corpus comparison):** Fuzzy matching algorithm for re-extraction comparison (Levenshtein distance? Embeddings-based similarity?) needs spike to determine best approach.

**Phases with standard patterns (skip research-phase):**
- **Phase 1 (bug fixes):** Query changes, UI tweaks, MedGemma debugging—all established patterns
- **Phase 3 (editor):** React-hook-form lifecycle, JSONB schema handling—patterns exist in CriterionCard.tsx
- **Phase 4 (re-extraction):** API endpoint + outbox event—same pattern as protocol upload

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Existing stack is sound; consolidation requires zero new major dependencies; RxNorm/LOINC/ICD-10 APIs verified via official NLM documentation |
| Features | HIGH | Feature priorities derived from codebase analysis (Dashboard.tsx, reviews.py, CriterionCard.tsx), E2E test report, and regulatory requirements (21 CFR Part 11) |
| Architecture | HIGH | Consolidation approach verified via codebase analysis (exact file references), LangGraph official docs for flat graph pattern, and transactional outbox pattern literature |
| Pitfalls | HIGH | All 10 pitfalls derived from codebase analysis (exact line references), E2E test report documenting actual failures, and recovery strategies based on outbox pattern literature |

**Overall confidence:** HIGH

Research based on complete codebase analysis (120+ file references), official documentation (Google GenAI SDK, LangGraph, NLM APIs), E2E test report (13 issues documented 2026-02-13), and established patterns (transactional outbox, JSONB schema evolution).

### Gaps to Address

**Gap 1: ToolUniverse tool quality**
- **Issue:** ToolUniverse documentation confirms RxNorm/ICD-10/LOINC/HPO tools exist, but tool quality/reliability for clinical entity resolution not independently verified.
- **Resolution:** Build direct API clients instead of depending on ToolUniverse. The underlying NLM APIs are stable and production-ready. ToolUniverse is a research toolkit wrapper.
- **Phase:** Phase 2 (terminology router); verify API responses during implementation via test calls.

**Gap 2: Gemini determinism**
- **Issue:** Gemini does not guarantee deterministic output even with temperature=0 and seed. This is a known limitation (GitHub issue #745).
- **Resolution:** Accept approximate determinism; design corpus comparison to use fuzzy text matching (80%+ similarity threshold) rather than exact equality.
- **Phase:** Phase 4 (extraction determinism); add prompt granularity instructions + seed parameter as best-effort mitigation.

**Gap 3: HPO and LOINC coverage**
- **Issue:** ToolUniverse documentation confirms HPO tool exists, but no dedicated LOINC tool found (LOINC coverage via NLM Clinical Tables API). HPO tool may only cover phenotype names, not context-aware mapping.
- **Resolution:** Use NLM Clinical Tables API directly for LOINC (clinicaltables.nlm.nih.gov/api/loinc/v3/search). For HPO, use HPO/Monarch API or fall back to UMLS SNOMED for biomarker entities.
- **Phase:** Phase 2 (terminology router); verify HPO API response format during implementation.

**Gap 4: MedGemma vs Gemini for entity extraction**
- **Issue:** Current system uses MedGemma 4b-it for entity extraction, which lacks structured output support and causes JSON parse failures. Research recommends Gemini for entity extraction, but this changes the model entirely.
- **Resolution:** Spike during Phase 2: Test Gemini entity extraction with few-shot examples on 3 protocols. Compare entity quality vs MedGemma. If quality is acceptable (>80% entity recall), proceed with Gemini. If not, consider MedGemma 27b (if available on Model Garden) or improve MedGemma 4b-it prompt engineering.
- **Phase:** Phase 2 (ground node implementation); early spike before committing to Gemini-only approach.

## Sources

### Primary (HIGH confidence)
- **Codebase analysis** — 120+ file references verified across services (extraction-service, grounding-service, api-service, hitl-ui) with exact line numbers
- **E2E test report** — `.planning/research/E2E-REPORT.md` documenting 13 issues from 2026-02-13 testing
- **Official API documentation** — Google GenAI SDK (structured output, Pydantic integration), NLM RxNorm API, NLM LOINC API, UMLS REST API
- **LangGraph documentation** — Flat graph pattern, state management, subgraph composition patterns
- **Regulatory standards** — 21 CFR Part 11 (audit trail requirements for clinical systems)

### Secondary (MEDIUM confidence)
- **ToolUniverse documentation** — Harvard Zitnik Lab (zitniklab.hms.harvard.edu/ToolUniverse/), tool categories verified but tool quality not independently tested
- **ToolUniverse GitHub** — mims-harvard/ToolUniverse repository, RxNorm tool source code verified, HPO/LOINC tool existence confirmed but not tested
- **Clinical terminology standards** — PMC6115234 (SNOMED/LOINC/RxNorm integration), SNOMED to ICD-10 mapping documentation
- **Transactional outbox pattern** — microservices.io pattern documentation, AWS prescriptive guidance

### Tertiary (LOW confidence)
- **Gemini non-determinism** — GitHub issue #745 (deprecated-generative-ai-python), community forum discussions; Google does not guarantee determinism
- **ToolUniverse production readiness** — Research toolkit from Harvard, not production-hardened; dependency footprint analysis shows 211+ tools when only 5-6 needed

---

*Research completed: 2026-02-16*
*Ready for roadmap: YES*
*Consolidated files: STACK-pipeline-consolidation.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md*
