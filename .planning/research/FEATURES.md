# Feature Research

**Domain:** Pipeline consolidation, multi-terminology grounding, E2E quality fixes, and editor polish for clinical trial criteria extraction
**Researched:** 2026-02-16
**Confidence:** HIGH (codebase-verified) / MEDIUM (domain practices)

---

## Feature Categories

Features are organized by the 10 target areas from the milestone context, then classified as table stakes, differentiators, or anti-features within each.

---

## Category 1: Pipeline Consolidation

### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Single-command re-extraction for a protocol | Researchers expect to re-run extraction without re-uploading PDFs; current system requires re-upload or manual outbox event | LOW | Add `POST /protocols/{id}/reextract` endpoint that publishes ProtocolUploaded event for existing file_uri |
| Re-extraction preserves reviewed criteria | Researchers will not tolerate losing human corrections; corpus building depends on reviewed data being immutable | MEDIUM | Requires `is_locked` flag on criteria with `review_status IS NOT NULL`; new batch created alongside existing, not replacing |
| Clear pipeline status visibility | Researchers need to know whether a protocol is extracting, grounding, or ready for review; current status field exists but transitions are unclear | LOW | Already have status field on Protocol; needs consistent state machine: `uploaded -> extracting -> extracted -> grounding -> pending_review` |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Merged extraction+grounding graph | Eliminates outbox hop between extraction and grounding; reduces latency by ~2-5s; simplifies debugging since both graphs share the same LangGraph invocation | HIGH | Currently extraction (4 nodes) publishes CriteriaExtracted event, outbox processor picks it up, invokes grounding (2 nodes). Merging into 6-node graph eliminates async boundary but increases coupling |
| Selective re-extraction (per-criterion) | Re-extract only low-confidence criteria instead of entire protocol; saves cost and preserves approved criteria naturally | HIGH | Requires criterion-level extraction invocation; current system only extracts full protocol |

### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Fully merging extraction-service and grounding-service Python packages | "Simpler codebase" | Destroys separation of concerns; extraction uses Gemini, grounding uses MedGemma with different model configs; package merge would create massive import graph and confuse ownership | Keep packages separate but allow a single LangGraph to span both; import from both packages in a combined graph module |
| Real-time streaming extraction progress | "Show criteria appearing one by one" | Gemini structured output returns complete JSON in one response, not streamable; fake streaming adds complexity without real benefit | Show progress bar with stages: "Fetching PDF... Extracting... Grounding... Done" |

---

## Category 2: ToolUniverse / Multi-Terminology Grounding

### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Entity-type-aware terminology routing | Medications must map to RxNorm, conditions to ICD-10/SNOMED, lab values to LOINC, phenotypes to HPO; sending "metformin" to ICD-10 is nonsensical | MEDIUM | Route based on `entity_type` field already extracted: Medication -> RxNorm API, Condition -> ICD-10 + SNOMED, Lab_Value -> LOINC FHIR, Demographic/Biomarker -> HPO |
| RxNorm medication lookup via NLM API | Standard drug name normalization; RxNorm API is free, well-documented, returns RXCUI + normalized drug names | MEDIUM | Base URL: `https://rxnav.nlm.nih.gov/REST/`; `getApproximateMatch` for fuzzy drug name search; no API key required |
| ICD-10-CM condition coding via NLM Clinical Tables | Standard diagnosis coding; free API at `clinicaltables.nlm.nih.gov/api/icd10cm/v3/search` | MEDIUM | Returns code + description pairs; supplement with SNOMED mapping (existing UMLS MCP) for clinical depth |
| LOINC lab test lookup via FHIR Terminology Server | Standard lab observation coding; FHIR endpoint at `fhir.loinc.org/CodeSystem/$lookup` | MEDIUM | Requires free LOINC credentials; returns observation identifiers for lab values |
| UMLS/SNOMED as fallback for unrouted entities | Not all entities fit RxNorm/ICD-10/LOINC cleanly; UMLS is the universal fallback | LOW | Already implemented via UMLS MCP concept_search; becomes the catch-all after type-specific routing |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| HPO phenotype grounding | Maps clinical phenotypes to HPO codes for rare disease trials; NLM Clinical Tables API at `clinicaltables.nlm.nih.gov/api/hpo/v3/search` | MEDIUM | Particularly valuable for oncology and rare disease protocols; entity_type "Biomarker" and "Condition" with phenotype characteristics |
| Multi-code resolution (store all applicable codes) | A single entity like "type 2 diabetes" may have ICD-10 (E11), SNOMED (44054006), and UMLS (C0011860) codes; storing all enables downstream interoperability | LOW | Extend Entity model to store `rxnorm_code`, `icd10_code`, `loinc_code`, `hpo_code` alongside existing `umls_cui` and `snomed_code` |
| Confidence scoring per terminology source | Different APIs have different match quality; showing "RxNorm: 95%, SNOMED: 78%" helps reviewers focus | LOW | Each API returns different confidence signals; normalize to 0-1 scale per source |

### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Building a local terminology database | "Faster lookups, offline access" | RxNorm alone is 200k+ concepts; SNOMED is 350k+; maintaining sync is a full-time job; regulatory implications of stale data | Use REST APIs with disk caching (existing pattern in UMLS client); cache TTL of 7 days for resolved codes |
| Automatic entity type reclassification | "AI should know 'metformin' is a medication even if extraction says 'Condition'" | Reclassifying extraction output creates confusion about source of truth; introduces disagreement between extraction and grounding | Instead, add entity_type correction as a HITL review action; reviewer can change type and trigger re-grounding |

---

## Category 3: Critical Bug Fixes (E2E Quality)

### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Audit trail visibility (non-empty audit log) | Regulatory requirement; reviewers must see their review history; currently returns empty because audit log entries exist but are not displayed in context | LOW | Bug: Dashboard "Recent Activity" hardcodes "No recent activity" instead of querying audit log API. Fix: call `useAuditLog(1, 5)` in Dashboard and render entries |
| Grounding confidence > 0% | 100% of entities showing 0% confidence means grounding is fundamentally broken; MedGemma agentic loop needs debugging | MEDIUM | Root cause likely in `medgemma_ground_node`: JSON parse failures from MedGemma output, or UMLS MCP tool errors silently swallowed. Need to inspect actual MedGemma responses |
| Dashboard pending count > 0 | Dashboard queries `useBatchList(1, 1, 'pending_review')` but batches may be in 'in_progress' status after first review; pending count should include both statuses | LOW | Fix: query both `pending_review` and `in_progress` batches, or compute count from criteria with `review_status IS NULL` |
| Approve/reject persists correctly | E2E tests showed review actions may not update batch status transitions properly | LOW | Verify `_update_batch_status` transitions: pending_review -> in_progress -> approved/rejected; add integration test |

### Differentiators

None -- bug fixes are not differentiators. They are debt that must be paid.

### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| "Fix all bugs at once" in a single phase | "Ship faster" | Grounding confidence fix requires MedGemma debugging which may take days; mixing with trivial dashboard fixes blocks the trivial fixes | Fix in priority order: dashboard count (5 min) -> audit visibility (30 min) -> grounding confidence (1-3 days) |

---

## Category 4: Extraction Quality Improvements

### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Deterministic extraction (temperature=0 + seed) | Re-running extraction on the same protocol should produce identical results; needed for reproducibility and evaluation | LOW | Already set `temperature=0` in extraction; add `seed=42` to Gemini call for full determinism. Verify in `extract.py` |
| Prompt tightening for consistent output quality | Current prompt already has few-shot examples but may produce inconsistent category assignments or miss criteria | MEDIUM | Analyze extraction output across 3+ protocols; identify systematic errors (e.g., missing exclusion criteria, wrong categories); add corrective few-shot examples |
| Extraction model version tracking | Must know which model produced each extraction for evaluation; `extraction_model` field exists on CriteriaBatch | LOW | Already implemented; verify `GEMINI_MODEL_NAME` env var flows into `extraction_model` field in queue_node |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Structured output schema enforcement via Gemini JSON mode | Forces Gemini to output valid JSON matching the Pydantic schema exactly; reduces parse failures | LOW | Already using `with_structured_output(ExtractionResult)`; verify this uses Gemini's native JSON mode rather than prompt-based extraction |
| Per-criterion confidence calibration | Current confidence scores are LLM self-assessed (unreliable); calibrate against reviewer agreement rates | HIGH | Requires corpus of reviewed criteria to compute calibration curve; defer to corpus comparison phase |

### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Multiple extraction models per protocol | "Compare Gemini vs GPT-4 vs Claude" | Adds 3x cost, creates comparison UI complexity, model outputs have different schemas | Single model (Gemini) with version tracking; compare versions over time via corpus evaluation |

---

## Category 5: Editor Pre-loading (field_mappings Populate Modify Mode)

### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Saved field_mappings pre-populate structured editor | When a reviewer already modified structured fields, clicking "Modify Fields" again must show the saved values, not empty or AI-inferred defaults | MEDIUM | `buildInitialValues()` already handles Priority 1 (existing field_mappings from `conditions.field_mappings`) before Priority 2 (AI-inferred). Bug: verify this path works when `conditions` has `field_mappings` key. Potential issue: react-hook-form `defaultValues` vs `values` timing |
| Form populates on navigation (not just initial mount) | Navigating away and back to a criterion must re-populate the form from current data | LOW | Use react-hook-form `values` prop or `reset()` in useEffect when criterion data changes |
| Database ID separation from useFieldArray IDs | Editing a saved mapping must update the correct database record, not create a duplicate | MEDIUM | Store database IDs as `database_id` field in form state; use `field.id` from useFieldArray only for React keys |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Dirty-state indicator showing unsaved changes | Reviewer sees which fields were modified since last save; reduces accidental data loss | LOW | Compare current form values to last-saved values; show yellow border or "unsaved" badge |

### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Auto-save structured edits on blur | "Never lose work" | Auto-save creates audit log entries for every field change; pollutes audit trail; may save incomplete/incorrect mappings | Manual save with unsaved-changes warning on navigation |

---

## Category 6: Read-Mode field_mappings Display

### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Structured fields displayed as badges/chips in read mode | When not editing, criterion cards must show entity/relation/value mappings as visual chips (similar to existing threshold badges) | MEDIUM | Check `conditions.field_mappings` array; render each mapping as `[entity] [relation] [value]` chip. Must handle null/undefined gracefully for pre-structured-editor criteria |
| Graceful fallback for unstructured criteria | Criteria created before structured editing must not crash; show "No structured fields" or display raw conditions list | LOW | TypeScript type guard: `isFieldMappings(conditions)` checks for `field_mappings` array existence |
| Visual distinction between AI-extracted and human-reviewed mappings | Reviewers must know which mappings are AI-generated vs human-corrected; prevents assuming AI output is verified | LOW | Use `schema_version` from audit log: `text_v1` = no structured fields, `structured_v1` = single edit, `v1.5-multi` = multi-mapping |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Expandable entity detail showing UMLS CUI, SNOMED code, and terminology source | Clicking an entity badge reveals its codes without entering edit mode; quick verification | LOW | Tooltip or accordion showing `umls_cui`, `snomed_code`, `rxnorm_code` etc. |

### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Full structured editor in read mode (always editable) | "Fewer clicks to edit" | Removes the review-then-edit workflow; accidental edits become possible; no clear approve/modify distinction | Keep read-mode as display-only; require explicit "Modify Fields" click to enter edit mode |

---

## Category 7: Corpus Comparison (AI-Original vs Human-Corrected)

### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Side-by-side diff view: AI extraction vs human correction | Core use case for corpus building; researchers must see exactly what the AI got right and what the human changed | HIGH | Requires storing original AI extraction separately from human-modified version. Audit log already captures `before_value` and `after_value`; build diff view from audit history |
| Export reviewed criteria as JSON/CSV corpus | Researchers need machine-readable corpus for model evaluation and fine-tuning | MEDIUM | `GET /export/corpus?format=json` endpoint; include `criterion_text`, `ai_entities`, `human_entities`, `review_status`, `reviewer_id`, `schema_version` |
| Metrics dashboard: agreement rate, modification frequency | Researchers need aggregate statistics: "How often does the AI get it right? What categories need the most correction?" | MEDIUM | Compute from audit log: % approved vs modified vs rejected, broken down by category, entity_type, and protocol |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Inter-annotator agreement (IAA) tracking | Gold-standard corpus quality metric; multiple reviewers per criterion enables Cohen's Kappa calculation | HIGH | Requires dual-review workflow: randomly assign 10-20% of criteria to second reviewer. Store `reviewer_count` per criterion. Compute Kappa on dual-reviewed subset |
| Version-tagged corpus snapshots | Freeze corpus at a point in time for reproducible evaluation; tag with extraction model version and prompt version | MEDIUM | `POST /corpus/snapshot` creates versioned export with metadata: model, prompt hash, date, criteria count |

### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Real-time model retraining from corrections | "Corpus should immediately improve the model" | Fine-tuning Gemini/MedGemma requires careful data curation, evaluation, and regression testing; real-time retraining risks quality degradation from noisy corrections | Batch corpus export -> offline evaluation -> manual decision to retrain |
| Automatic quality scoring of corrections | "Score the human reviewer's work quality" | Circular: who grades the grader? Requires ground truth that doesn't exist yet | Use IAA (inter-annotator agreement) instead; disagreement flags for adjudication |

---

## Category 8: Re-extraction Tooling

### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Re-run pipeline on existing protocol via API | After prompt improvements, researchers need to re-extract without re-uploading | LOW | `POST /protocols/{id}/reextract` publishes ProtocolUploaded event using existing `file_uri`; protocol already has all metadata |
| Lock reviewed criteria before re-extraction | Must not destroy human corrections; new batch created alongside, not replacing | MEDIUM | Add `is_locked` computed from `review_status IS NOT NULL`; re-extraction creates new CriteriaBatch for same protocol_id |
| UI button for re-extraction with confirmation | Researcher clicks "Re-extract" on protocol detail page with warning: "This will create a new extraction batch" | LOW | Button in protocol detail view; confirmation modal; calls reextract endpoint |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Re-extraction comparison: old batch vs new batch | After re-extracting, show which criteria were added/removed/changed between batches | HIGH | Batch-level diff: match criteria by text similarity (fuzzy), show added/removed/modified. Valuable for prompt iteration evaluation |
| Batch-level re-grounding | Re-run grounding only (without re-extraction) after ToolUniverse integration; useful when grounding code changes but extraction is stable | LOW | `POST /protocols/{id}/reground?batch_id=X` publishes CriteriaExtracted event for existing batch |

### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Automatic re-extraction when prompt changes | "Deploy new prompt -> all protocols re-extracted" | Expensive (Gemini API cost), destroys reproducibility, may break reviewed criteria | Manual re-extraction per protocol with researcher confirmation |

---

## Category 9: UX Improvements

### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Visual distinction between reviewed and pending criteria | Reviewer must instantly see which criteria still need attention; currently all cards look the same except for a small status badge | LOW | Add left border color: green for approved, red for rejected, blue for modified, gray/no border for pending. Already have `isLowConfidence` border pattern to extend |
| Criteria search within a batch | Batches can have 40-60 criteria; scrolling through all is tedious; need text search to find specific criteria | LOW | Client-side filter on criteria list using text match; no API change needed |
| Sortable column headers on criteria list | Sort by confidence, type, category, review_status; currently only sorts by confidence via API param | LOW | API already supports `sort_by` and `sort_order` params; add clickable headers in UI |
| Approve/reject keyboard shortcuts | Reviewers processing 50+ criteria need speed; mouse clicking is slow | LOW | `a` for approve, `r` for reject, `m` for modify, `n/p` for next/previous criterion |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Batch progress bar | Visual indicator showing "23/47 criteria reviewed" with color-coded segments (approved/rejected/modified/pending) | LOW | Data already available from `criteria_count` and `reviewed_count` in BatchResponse |
| Criteria grouping by category | Group criteria by category (demographics, medical_history, lab_values, etc.) with collapsible sections | MEDIUM | Client-side grouping of flat criteria list; reduces cognitive load for large batches |
| Review session timer | Show how long a reviewer has been working on a batch; useful for workload estimation and corpus building metrics | LOW | Client-side timer started on batch page entry; stored in localStorage |

### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Drag-and-drop criteria reordering | "Let reviewers organize criteria" | Extraction order maps to protocol order which is the source of truth; reordering breaks evidence linking (page numbers) and creates confusion about which order is "correct" | Sort options (by confidence, by page, by category) instead of manual reorder |
| Dark mode | "Modern UI" | Low priority; adds CSS maintenance burden; not requested by clinical researcher users | Defer to v2+ unless users request |

---

## Category 10: Approve/Reject Rationale Prompt

### Table Stakes

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Rationale prompt on reject action | Regulatory requirement (21 CFR Part 11); rejections must have documented reason; currently `comment` field is optional | LOW | Show modal/inline textarea on reject with required text before submission; already have `comment` field on ReviewActionRequest |
| Rationale prompt on approve action (optional) | Some auditors want to know why criteria were approved without modification; optional but visible | LOW | Show collapsible rationale textarea on approve; pre-fill with "Approved as extracted" default |
| Rationale displayed in audit log view | Reviewers and auditors must see rationale alongside each review action in the audit trail | LOW | Already stored as `details.rationale` in audit log; render in audit log list view |

### Differentiators

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Rationale templates/presets | Dropdown of common rationale phrases: "Extraction matches protocol text", "Entity code corrected", "Criterion text reformatted for clarity" | LOW | Reduces typing; improves consistency of audit trail language |

### Anti-Features

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Required rationale for every approve action | "Complete audit trail" | Friction kills throughput; reviewers approve 70-80% of criteria; requiring rationale for routine approvals adds 5-10 seconds per criterion, multiplied by 40+ criteria per batch | Optional rationale for approve; required only for reject/modify |

---

## Feature Dependencies

```
[Pipeline Consolidation]
    |
    +--requires--> [Bug Fixes: Grounding Confidence]
    |                  (grounding must work before consolidation makes sense)
    |
    +--requires--> [Re-extraction Tooling]
                       (re-extraction is how you test consolidated pipeline)

[ToolUniverse Grounding]
    |
    +--requires--> [Bug Fixes: Grounding Confidence]
    |                  (fix existing UMLS grounding before adding new terminologies)
    |
    +--enhances--> [Read-Mode field_mappings Display]
                       (multi-terminology codes appear as badges)

[Editor Pre-loading]
    +--requires--> [Read-Mode field_mappings Display]
    |                  (must display before allowing edit of saved data)
    |
    +--enhances--> [Approve/Reject Rationale]
                       (rationale visible in read mode after review)

[Corpus Comparison]
    +--requires--> [Editor Pre-loading]
    |                  (need saved structured edits to compare)
    |
    +--requires--> [Re-extraction Tooling]
    |                  (need multiple extraction batches to compare)
    |
    +--requires--> [Bug Fixes: Audit Trail]
                       (audit log provides before/after for diff view)

[UX Improvements]
    +--independent (can be done in any order)
    +--enhances--> [All other categories]

[Approve/Reject Rationale]
    +--enhances--> [Corpus Comparison]
                       (rationale explains why corrections were made)
```

### Dependency Notes

- **Bug Fixes MUST come first:** Grounding confidence 0%, empty audit trail, and dashboard pending count are blockers for ToolUniverse integration, corpus comparison, and audit visibility respectively
- **ToolUniverse depends on working grounding:** Adding RxNorm/ICD-10/LOINC/HPO routing on top of broken UMLS grounding compounds problems
- **Corpus comparison depends on multiple features:** Requires working audit trail, saved structured edits, and re-extraction to produce meaningful diffs
- **UX improvements are independent:** Can be shipped in any phase without dependencies
- **Pipeline consolidation is high-risk, high-reward:** Merging graphs simplifies architecture but risks introducing new bugs; should be attempted after bug fixes stabilize the system

---

## MVP Definition

### Phase 1: Fix What's Broken (v1.6-alpha)

- [x] Dashboard pending count includes both `pending_review` and `in_progress` batches
- [x] Audit trail populated in Dashboard "Recent Activity" section
- [x] Grounding confidence investigation and fix (MedGemma JSON parsing, UMLS MCP tool errors)
- [x] Visual distinction for reviewed vs pending criteria (left border color)
- [x] Approve/reject rationale prompt (required for reject, optional for approve)

### Phase 2: Polish Existing Features (v1.6-beta)

- [ ] Read-mode field_mappings display as badges/chips
- [ ] Editor pre-loading from saved field_mappings
- [ ] Criteria search within batch (client-side filter)
- [ ] Sortable column headers
- [ ] Extraction determinism (seed parameter)

### Phase 3: New Capabilities (v1.7)

- [ ] ToolUniverse multi-terminology grounding (RxNorm, ICD-10, LOINC, HPO routing)
- [ ] Re-extraction tooling (API endpoint + UI button + lock mechanism)
- [ ] Corpus comparison (diff view + JSON export)
- [ ] Pipeline consolidation evaluation (merged graph vs current architecture)

### Future Consideration (v2+)

- [ ] Inter-annotator agreement tracking
- [ ] Selective per-criterion re-extraction
- [ ] Per-criterion confidence calibration from corpus data
- [ ] Batch-level comparison after re-extraction

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority | Category |
|---------|------------|---------------------|----------|----------|
| Dashboard pending count fix | HIGH | LOW | P1 | Bug Fix |
| Audit trail visibility | HIGH | LOW | P1 | Bug Fix |
| Grounding confidence fix | HIGH | MEDIUM | P1 | Bug Fix |
| Reviewed/pending visual distinction | HIGH | LOW | P1 | UX |
| Reject rationale (required) | HIGH | LOW | P1 | Rationale |
| Read-mode field_mappings badges | MEDIUM | MEDIUM | P2 | Editor |
| Editor pre-loading from saved data | MEDIUM | MEDIUM | P2 | Editor |
| Criteria search within batch | MEDIUM | LOW | P2 | UX |
| Sortable column headers | MEDIUM | LOW | P2 | UX |
| Extraction determinism (seed) | MEDIUM | LOW | P2 | Extraction |
| Re-extraction API + UI | HIGH | MEDIUM | P2 | Re-extraction |
| RxNorm medication lookup | HIGH | MEDIUM | P2 | Grounding |
| ICD-10 condition coding | HIGH | MEDIUM | P2 | Grounding |
| LOINC lab test lookup | MEDIUM | MEDIUM | P2 | Grounding |
| Entity-type routing | HIGH | MEDIUM | P2 | Grounding |
| Corpus export (JSON/CSV) | MEDIUM | MEDIUM | P3 | Corpus |
| AI vs human diff view | MEDIUM | HIGH | P3 | Corpus |
| Pipeline consolidation (merged graph) | LOW | HIGH | P3 | Architecture |
| HPO phenotype grounding | LOW | MEDIUM | P3 | Grounding |
| IAA tracking | LOW | HIGH | P3 | Corpus |
| Multi-code resolution per entity | MEDIUM | LOW | P3 | Grounding |
| Keyboard shortcuts | MEDIUM | LOW | P3 | UX |
| Batch progress bar | LOW | LOW | P3 | UX |
| Re-extraction batch comparison | LOW | HIGH | P3 | Re-extraction |

**Priority key:**
- P1: Must fix -- broken features, regulatory requirements, user-blocking bugs
- P2: Should build -- next-milestone features that enable core new capabilities
- P3: Nice to have -- valuable but deferrable without blocking the system

---

## Competitor Feature Analysis

| Feature | AutoCriteria (JAMIA 2024) | Chia Corpus | John Snow Labs Healthcare NLP | Our System |
|---------|---------------------------|-------------|-------------------------------|------------|
| Criteria extraction | GPT-4 with domain-specific prompts | Manual annotation (12,409 criteria) | Spark NLP pipeline | Gemini multimodal PDF extraction |
| Entity grounding | Post-processing with medical ontologies | 15 entity types, no auto-grounding | ICD-10, RxNorm, SNOMED sentence resolvers | MedGemma + UMLS MCP (expanding to ToolUniverse) |
| Multi-terminology | Not reported | Not applicable | RxNorm + ICD-10 + SNOMED pipeline | Planned: RxNorm, ICD-10, LOINC, HPO via entity-type routing |
| HITL review | Not available | Annotation tool (brat) | Annotation Lab (commercial) | Custom React UI with structured editor |
| Corpus comparison | Manual evaluation | IAA on 11% subset | NLP Lab comparison features | Planned: AI vs human diff view |
| Evidence linking | Not available | Not available | Not available | PDF scroll-to-source with page numbers |
| Structured editing | Not available | Not available | Entity modification in Annotation Lab | Entity/relation/value triplet editor with UMLS autocomplete |

**Our competitive advantage:** End-to-end system from PDF upload through structured editing to corpus export, with evidence linking (PDF scroll-to-source) that no competitor offers. The HITL review workflow with multi-mapping and UMLS autocomplete is more advanced than annotation-only tools.

**Our gap:** Multi-terminology grounding (RxNorm, ICD-10, LOINC) is standard in commercial NLP pipelines (John Snow Labs) but missing from our system. ToolUniverse integration closes this gap.

---

## Sources

### Clinical Trial Criteria Extraction Systems
- [AutoCriteria: GPT-based extraction system (JAMIA 2024)](https://academic.oup.com/jamia/article/31/2/375/7413158)
- [iTEST: NLP-powered clinical decision support (JMIR 2025)](https://medinform.jmir.org/2025/1/e80072)
- [Systematic review of trial-matching pipelines using LLMs](https://www.arxiv.org/pdf/2509.19327)
- [Chia corpus: 12,409 annotated eligibility criteria](https://www.nature.com/articles/s41597-020-00620-0)
- [Leaf Clinical Trials Corpus](https://www.nature.com/articles/s41597-022-01521-0)

### Terminology Services and APIs
- [RxNorm API](https://lhncbc.nlm.nih.gov/RxNav/APIs/RxNormAPIs.html)
- [ICD-10-CM API (NLM Clinical Tables)](https://clinicaltables.nlm.nih.gov/apidoc/icd10cm/v3/doc.html)
- [LOINC FHIR Terminology Service](https://loinc.org/fhir/)
- [HPO API (NLM Clinical Tables)](https://clinicaltables.nlm.nih.gov/apidoc/hpo/v3/doc.html)
- [SNOMED CT, LOINC, and RxNorm overview (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC6115234/)

### Entity Resolution and Grounding
- [Clinical entity resolution benchmarks: Spark NLP vs cloud providers](https://www.johnsnowlabs.com/comparison-of-clinical-entity-resolution-icd10-rxnorm-snomed-benchmarks-spark-nlp-vs-aws-google-cloud-and-azure/)
- [IMO comprehensive clinical entity extraction pipeline](https://marketplace.databricks.com/details/6fe025cc-9cc5-45f5-a3ae-bf61891e6e87/Intelligent-Medical-Objects-IMO_Comprehensive-clinical-entity-extraction-NLP-pipeline-ICD-SNOMED-RxNorm-NDC-LOINC-HCPCS-more)
- [Human vs NLP annotation comparison (PMC)](https://pmc.ncbi.nlm.nih.gov/articles/PMC8378608/)

### HITL and Corpus Building
- [Top 6 annotation tools for HITL evaluation (John Snow Labs)](https://www.johnsnowlabs.com/top-6-annotation-tools-for-hitl-llms-evaluation-and-domain-specific-ai-model-training/)
- [Transformer-based relation extraction with annotated corpus (Nature 2026)](https://www.nature.com/articles/s41597-026-06608-6)

### Codebase-Specific References
- Dashboard.tsx: `useBatchList(1, 1, 'pending_review')` at line 12 -- pending count bug
- reviews.py: `_apply_review_action()` at lines 455-507 -- structured field handling
- medgemma_ground.py: agentic grounding loop -- confidence propagation
- CriterionCard.tsx: `buildInitialValues()` at lines 186-302 -- editor pre-loading logic

---

*Feature research for: Pipeline consolidation, multi-terminology grounding, E2E quality fixes, and editor polish*
*Researched: 2026-02-16*
*Confidence: HIGH for bug fixes and editor features (codebase-verified), MEDIUM for ToolUniverse integration (API docs verified but not integration-tested)*
