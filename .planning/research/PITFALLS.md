# Pitfalls Research

**Domain:** Clinical Trial Protocol Criteria Extraction System
**Researched:** 2026-02-10
**Confidence:** HIGH

## Critical Pitfalls

### Pitfall 1: LLM Hallucination in Medical Concept Mapping

**What goes wrong:**
LLMs generate nonexistent UMLS/SNOMED concept identifiers when mapping clinical terms to standardized vocabularies, with hallucination rates of 15%-55% in production systems. This results in incorrect medical codes being stored in the database, breaking downstream clinical decision support.

**Why it happens:**
LLMs are trained on general medical text but lack grounding in authoritative medical ontologies. When encountering clinical terms with multiple possible codes or ambiguous context, models confidently generate plausible-looking but nonexistent concept IDs rather than admitting uncertainty.

**How to avoid:**
- Implement post-extraction validation that verifies every generated UMLS/SNOMED code exists in the actual ontology
- Use the UMLS MCP server to validate codes immediately after extraction, before database storage
- Set up assertion confidence thresholds—reject extractions below 0.85 confidence and route to HITL review
- Use MedGemma's semantic type prediction to filter irrelevant candidate concepts before disambiguation
- Implement three-stage verification: (1) code exists, (2) semantic type matches, (3) context aligns with definition

**Warning signs:**
- Model outputs UMLS codes that fail lookup in UMLS API
- Extraction pipeline shows high confidence (>0.9) but codes don't resolve
- Human reviewers frequently reject "confidently extracted" entities
- Same clinical term maps to different codes across similar protocols
- Codes exist but semantic types don't match extracted entity types (e.g., "Procedure" code for a "Finding")

**Phase to address:**
Phase 1 (Core Extraction Pipeline) - Build validation into extraction from day one. Cannot defer to later phases.

---

### Pitfall 2: PDF Quality Degradation Breaking OCR

**What goes wrong:**
Fax-degraded PDFs and scanned protocols cause OCR failures, with simulated fax distortions decreasing extraction F1 scores by 38.8% on average. Medical gene symbols, patient IDs, and numeric lab values become unreadable or misrecognized, leading to incomplete or incorrect criteria extraction.

**Why it happens:**
Clinical trial protocols are frequently faxed between institutions (still common in healthcare in 2026), scanned from paper, or stored as low-quality image PDFs. OCR models struggle with degraded text, non-Latin characters, arbitrary letter-number combinations (gene names, IDs), and dense tabular layouts with spatial relationships.

**How to avoid:**
- Pre-process all PDFs through quality detection before extraction—flag low-quality documents for human review
- Use hybrid multimodal parsing: OCR for text + vision models for tables/figures + layout analysis for structure
- Implement confidence scoring per-section: extract text quality metrics (blur, contrast, skew) and route low-quality sections to enhanced OCR or manual review
- For numeric data (lab values, patient counts), use specialized numeric extraction models rather than general OCR
- Store original PDFs in GCS with quality metrics—allow reviewers to view source when extraction confidence is low
- Test extraction pipeline on fax-degraded samples during development, not just clean PDFs

**Warning signs:**
- Gene symbols, transcript IDs, or patient identifiers extracted with frequent errors
- Numeric criteria (e.g., "CD4 count >500") missing or garbled
- Table-based inclusion/exclusion criteria partially extracted or skipped
- Extraction accuracy varies wildly between protocols from different institutions
- Manual review reveals OCR errors that propagated through entire pipeline

**Phase to address:**
Phase 0 (Infrastructure Setup) - PDF quality detection and routing must exist before extraction begins.

---

### Pitfall 3: Criteria Complexity and Temporal Context Loss

**What goes wrong:**
Inclusion/exclusion criteria contain nested conditional logic and temporal constraints that get flattened or misrepresented during extraction. Example: "Patients with diabetes diagnosed >5 years ago unless controlled with HbA1c <7% in last 6 months" becomes oversimplified to "diabetes exclusion," losing critical nuance.

**Why it happens:**
Clinical trial eligibility criteria are syntactically and semantically complex, written in unstructured free-text. LLMs struggle with temporal constraints ("within 30 days of randomization"), context-dependent conditions ("unless controlled"), and multi-level nesting. Training data lacks explicit structure for representing conditional eligibility logic.

**How to avoid:**
- Use structured output schemas with explicit temporal and conditional fields (not just free-text extraction)
- Implement criteria parsing that preserves logical operators (AND/OR/UNLESS), temporal windows, and measurement thresholds
- During extraction, represent criteria as semantic triples: (entity, condition, temporal_constraint)
- Show HITL reviewers both extracted structured data AND original protocol section side-by-side for validation
- Build validation rules: if original text contains temporal words ("days," "months," "prior to"), extracted output must have temporal field populated
- Test extraction on complex oncology protocols (most nested criteria) rather than simple healthy-volunteer trials

**How to detect:**
- Extracted criteria are significantly shorter than protocol text (oversimplification)
- Temporal keywords in protocol ("before," "after," "within") but no temporal data in extraction
- Reviewers frequently add "missing context" during HITL review
- Criteria with "unless" or "except" clauses extracted without conditional logic
- Numeric thresholds present in protocol but absent in structured output

**Phase to address:**
Phase 1 (Core Extraction Pipeline) - Schema design must support complex criteria from the start. Cannot retrofit later.

---

### Pitfall 4: Inter-Annotator Variance Destroying Model Trust

**What goes wrong:**
Clinical researchers reviewing extracted criteria apply inconsistent standards—one approves "Type 2 diabetes" as sufficient, another requires specific HbA1c thresholds. This inconsistency poisons training data, causes model accuracy to plummet on retraining, and erodes trust when users see conflicting decisions.

**Why it happens:**
HITL annotation lacks clear guidelines on extraction granularity, acceptable simplification levels, and edge case handling. Different clinical backgrounds (oncology vs. cardiology researchers) lead to domain-specific interpretations. Annotation interfaces don't show examples or previous decisions for consistency.

**How to avoid:**
- Create detailed annotation guidelines BEFORE starting HITL review: define acceptable simplification, required fields, edge case handling
- Implement calibration sessions: all reviewers annotate same 10 protocols, discuss disagreements, establish shared standards
- Show annotators "similar previous decisions" during review to maintain consistency
- Track inter-annotator agreement metrics (Cohen's kappa) weekly—flag and resolve divergence >0.7 disagreement
- Use two-stage review for complex protocols: primary reviewer + validation reviewer for 20% sample
- Build annotation interface that flags potential inconsistencies ("you rejected this yesterday but approved similar today")

**Warning signs:**
- Inter-annotator agreement scores below 0.8 (0.6-0.7 is problematic, <0.6 is critical)
- Model performance degrades after retraining on HITL-reviewed data (should improve)
- Reviewers spend >10 minutes per protocol (suggests unclear guidelines)
- High "skip/unclear" rates during review (guidelines inadequate)
- Users complain "system inconsistently extracts similar criteria across protocols"

**Phase to address:**
Phase 2 (HITL Review Workflow) - Annotation standards must be established during HITL system design, not patched later.

---

### Pitfall 5: Active Learning Selecting Uninformative Noisy Samples

**What goes wrong:**
Simplistic uncertainty-based active learning surfaces edge cases that are noisy outliers (corrupted PDFs, non-English protocols, legacy formats) rather than informative examples. Annotators waste time on garbage data, model gets biased toward rare pathological cases.

**Why it happens:**
Model uncertainty doesn't distinguish between "informative uncertainty" (new pattern to learn) and "uninformative noise" (corrupted input). Active learning prioritizes high-uncertainty samples, but highest uncertainty often comes from broken data, not valuable learning opportunities.

**How to avoid:**
- Replace pure uncertainty sampling with hybrid strategy: uncertainty + diversity + quality filters
- Filter out low-quality PDFs (OCR confidence <0.7) BEFORE active learning selection
- Implement domain-based sampling: ensure selected protocols span therapeutic areas, phases, sponsors
- Use random sampling for 20% of HITL review to avoid bias toward edge cases
- Track annotation time: samples taking >15 minutes likely noise, not signal—exclude from future selection
- Compare active learning performance against random selection baseline—validate it's actually helping

**Warning signs:**
- Annotators frequently mark samples as "corrupted/unusable" during HITL review
- Active learning selects multiple protocols from same obscure sponsor/trial type
- Annotation time increases rather than decreases over time (should stabilize)
- Model performance on held-out test set doesn't improve despite more annotations
- Selected samples cluster around pathological cases rather than spanning normal variation

**Phase to address:**
Phase 2 (HITL Review Workflow) - Active learning strategy must be validated before production use.

---

### Pitfall 6: Negation and Assertion Detection Failures

**What goes wrong:**
Extraction pipeline misinterprets "consider pneumonia" as confirmed diagnosis, or "no history of diabetes" as positive for diabetes. System extracts entities but loses critical context about whether conditions are present, absent, hypothetical, or historical.

**Why it happens:**
Medical NLP requires assertion detection (confirmed vs. hypothetical vs. negated) beyond entity extraction. Clinical notes use negation to indicate condition absence, modals ("consider," "possible") for hypotheses, and temporal markers ("history of") for past events. Standard NER doesn't capture this context.

**How to avoid:**
- Implement assertion detection as separate pipeline stage after entity extraction
- Tag each extracted criterion with assertion status: PRESENT, ABSENT, HYPOTHETICAL, HISTORICAL, CONDITIONAL
- Use specialized medical assertion detection models (cTAKES, MedCAT) rather than general LLMs
- For eligibility criteria, distinguish between inclusion requirements (must have) and exclusion requirements (must NOT have)
- Validate negation detection specifically: create test set with negative criteria, measure recall
- Show assertion status prominently in HITL review UI—reviewers must confirm assertion correctness

**Warning signs:**
- Extracted criteria include negated conditions ("no diabetes") as positive findings
- Hypothetical diagnoses ("rule out cancer") extracted as confirmed conditions
- Historical conditions ("previous MI") not distinguished from current conditions
- Reviewers frequently correct assertion status during HITL review
- Downstream users report "system extracts too many irrelevant conditions"

**Phase to address:**
Phase 1 (Core Extraction Pipeline) - Assertion detection must be built in from the start, cannot bolt on later.

---

### Pitfall 7: Protocol Structure Variability Across Sponsors

**What goes wrong:**
Extraction pipeline trained on NIH protocol templates fails catastrophically on pharma sponsor protocols with different section headers, terminology, and organization. System extracts eligibility criteria from wrong sections, misses key exclusions, or mislabels protocol metadata.

**Why it happens:**
No standardized clinical trial protocol structure—each sponsor, CRO, and institution uses different templates. Section names vary ("Inclusion Criteria" vs. "Subject Selection" vs. "Eligibility Requirements"). Layout and formatting differ (tables vs. lists vs. paragraphs). Training data dominated by one template type creates brittleness.

**How to avoid:**
- Collect pilot sample (~50 protocols) spanning multiple sponsors, phases, and therapeutic areas BEFORE training extraction models
- Use protocol template detection as first pipeline stage—route different templates to specialized extractors
- Implement section detection that's robust to header variations: train on multiple synonyms for each section type
- For ~50 protocol pilot, manually create mapping of section headers to canonical types across all templates
- Use layout-aware parsing (not just text extraction) to handle both tabular and prose formats
- Build validation: if protocol from Sponsor X, verify typical sections present (detect corrupted/partial PDFs)

**Warning signs:**
- Extraction accuracy varies dramatically by sponsor (>20% gap between best and worst)
- Sections frequently mislabeled (e.g., "Study Design" content extracted as "Eligibility Criteria")
- Protocols from new sponsors require manual review >80% of the time
- Section detection fails silently—extracts wrong content without flagging uncertainty
- Model performs well on training data templates but fails on first real-world deployment

**Phase to address:**
Phase 0 (Infrastructure Setup) - Template diversity must be incorporated during dataset collection, not discovered in production.

---

### Pitfall 8: UMLS Coverage Gaps for Novel Therapies

**What goes wrong:**
Extraction pipeline cannot ground novel targeted therapies, immunotherapies, or gene therapy protocols to UMLS/SNOMED because concepts don't exist yet in ontologies. System marks ~30-40% of eligibility criteria as "unmappable," forcing excessive manual review.

**Why it happens:**
UMLS coverage incomplete for cutting-edge therapies—only 44% of outcome concepts fully covered, with metabolism/nutrition and infectious disease domains particularly sparse. New drug names, gene targets, and biomarkers take months to be added to UMLS after FDA approval. Complex oncology criteria combine multiple concepts, requiring 2+ UMLS codes.

**How to avoid:**
- Implement tiered grounding strategy: (1) exact UMLS match, (2) semantic similarity to existing concepts, (3) domain expert review queue
- For unmappable concepts, store free-text AND closest UMLS neighbor with similarity score
- Build domain-specific extension ontology for common novel terms in your therapeutic areas
- Track unmappable concept frequencies—if same novel term appears in >5 protocols, add to local ontology
- Don't block protocol processing on failed grounding—allow partial grounding with flagged review
- Set realistic expectations: 70-80% grounding success rate reasonable for novel therapy trials, not 95%+

**Warning signs:**
- >40% of extracted criteria fail UMLS grounding (indicates coverage gap, not extraction failure)
- Same novel therapy names repeatedly flagged as unmappable across multiple protocols
- Grounding succeeds but mapped concepts semantically mismatched (e.g., drug name mapped to disease)
- Complex criteria require 3+ UMLS codes to represent fully (UMLS too granular)
- Reviewers spend most time fixing grounding rather than validating extraction

**Phase to address:**
Phase 1 (Core Extraction Pipeline) - Grounding strategy must handle partial matches and missing concepts from the start.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Skip PDF quality detection, process all documents | Faster initial development, simpler pipeline | 38.8% F1 score drop on degraded PDFs, manual review overload, user trust erosion | Never—quality detection is foundational |
| Store only extracted data, not original protocol sections | Smaller database, simpler schema | Cannot debug extraction errors, cannot retrain models, cannot audit discrepancies | Never—regulatory compliance requires source retention |
| Use general LLM for grounding instead of UMLS validation | Faster extraction, no ontology integration needed | 15-55% hallucination rate, nonexistent codes, patient safety risk | Never for clinical deployment—only for demos |
| Single reviewer per protocol (no validation sample) | 2x review throughput, lower annotation cost | Inconsistent standards, poor inter-annotator agreement, degraded model performance | Acceptable for MVP if guidelines strong and reviewers experienced |
| Train on protocols from single sponsor/template | Easier to collect data, higher initial accuracy | Catastrophic failure on new templates, brittle system, constant retraining | Acceptable for proof-of-concept if scope limited to one sponsor |
| Extract criteria as free-text, skip structure preservation | Simpler extraction pipeline, faster development | Loss of temporal constraints, conditional logic, numeric thresholds—unusable for downstream | Never for production—defeats purpose of structured extraction |
| Use uncertainty sampling for active learning without quality filters | Standard approach, easy to implement | Wastes annotation budget on noisy outliers, biases model toward pathological cases | Acceptable if combined with diversity sampling and quality filters |
| Defer assertion detection to post-processing | Faster initial extraction pipeline | Negation errors, hypothetical diagnoses as confirmed, excessive false positives | Acceptable for Phase 1 if mitigated by prominent display in HITL review |

## Integration Gotchas

Common mistakes when connecting to external services.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| UMLS MCP Server | Query once per protocol and cache all results locally for session | Query per extracted entity with retry logic; rate limit compliance; handle temporary failures gracefully |
| Gemini for extraction | Send entire protocol in single prompt (exceeds context window or costs) | Chunk by section (eligibility, design, endpoints separately); use structured output schema; validate JSON responses |
| MedGemma (Vertex AI) | Assume same latency as local models, no timeout handling | Set 30-60 second timeouts; implement exponential backoff; queue extraction jobs asynchronously; monitor quota usage |
| GCS for PDFs | Store PDFs without metadata (quality scores, provenance, extraction version) | Store PDFs with custom metadata (upload date, sponsor, quality metrics, extraction pipeline version for re-processing) |
| PostgreSQL for criteria | Store extracted criteria as JSONB blob without validation | Use structured schema with foreign keys to UMLS codes table; validate code existence on insert; enable full-text search on criteria text |
| React HITL UI | Load all 50 protocols into client-side state at once | Paginate server-side; lazy load protocols on demand; cache reviewed protocols locally; stream validation results |

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Synchronous PDF extraction in API endpoint | Simple architecture, easy to debug | User timeout after 30 seconds, API gateway kills request | >10 page protocols (~30% of trials) |
| Loading entire protocol into LLM context | Thorough extraction, simple prompting | Context window limits (128K tokens), high costs ($1-5/protocol) | Protocols >100 pages (~15-20% of trials) |
| Processing all 50 protocols on upload | Immediate results, simple UX | Frontend freeze, browser crashes, server CPU spike | More than ~5 protocols in batch |
| Storing all extraction attempts in database | Complete audit trail, easy debugging | Database bloat, slow queries, high storage costs | After reprocessing protocols 3-4 times during development |
| Running HITL review UI on shared FastAPI backend | Simple deployment, one service | Review latency spikes during batch processing, poor UX | More than 2 concurrent reviewers |
| N+1 queries to UMLS for each criterion across protocols | Works correctly, straightforward code | 100+ database queries per protocol review page load | More than 10 criteria per protocol (~80% of protocols) |

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Storing original protocols in GCS without encryption at rest | HIPAA violation, patient identifiable information leak, regulatory penalties | Enable GCS default encryption; use customer-managed encryption keys (CMEK); audit access logs; set retention policies |
| Logging extracted patient demographics or identifiers | PHI exposure in logs, compliance violation | Implement log filtering to redact patient identifiers; never log extracted clinical data at DEBUG level; use audit table in database instead |
| Not implementing role-based access control for HITL review | Unauthorized access to trial data, competitive intelligence leak | Separate roles: reviewer, admin, read-only; authenticate users via OAuth; audit who reviewed which protocols |
| Exposing UMLS concept IDs without validating existence | Injection-like attacks via fake codes, data poisoning | Validate all UMLS codes against authoritative source before storage; treat UMLS codes as untrusted input |
| Allowing unrestricted PDF uploads without scanning | Malware embedded in PDFs, system compromise | Scan uploaded PDFs with antivirus; restrict file types to application/pdf only; validate PDF structure; set file size limits |
| Not redacting protocol metadata in exports | Sponsor confidential information leak, competitive harm | Strip protocol metadata (sponsor names, investigator identities, site locations) before exporting criteria; provide aggregated data only |

## UX Pitfalls

Common user experience mistakes in this domain.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Showing raw UMLS codes (C0011849) without human-readable labels | Users cannot verify correctness, abandon system as "unreadable" | Display preferred term + code: "Diabetes Mellitus (C0011849)"; link to UMLS browser for details |
| No side-by-side comparison of extracted criteria vs. original protocol | Reviewers cannot efficiently validate extraction, miss errors | Split-screen UI: original protocol section left, extracted structured data right; highlight matched text |
| Requiring reviewers to manually type corrections | Slow, error-prone, poor UX, low adoption | Provide dropdown suggestions from UMLS; click-to-edit fields; keyboard shortcuts; save partial progress |
| Not showing extraction confidence scores | Reviewers waste time on high-confidence correct extractions | Sort criteria by confidence (lowest first); auto-approve >0.95 confidence; highlight low-confidence sections |
| All-or-nothing approval: accept entire protocol or reject | Forces reviewers to fix minor issues, slows workflow | Criterion-level approval: accept 90%, flag 10% for re-extraction; partial saves |
| No feedback loop from HITL corrections to model | Model never improves, same errors repeat indefinitely | Track rejection patterns; retrain monthly on corrections; show reviewers "model learned from your feedback" |
| Auto-saving without indicating save status | Users lose work on network failures, distrust system | Visual save indicators; offline support with sync; explicit "Save" button; show last saved timestamp |
| No search/filter across reviewed protocols | Cannot find similar examples, inconsistent decisions | Full-text search across criteria; filter by therapeutic area, phase, sponsor; link to similar protocols |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **PDF Extraction:** Often missing quality detection—verify low-quality documents flagged and routed appropriately
- [ ] **Entity Extraction:** Often missing assertion detection (negation, hypothetical)—verify "no diabetes" correctly marked as ABSENT
- [ ] **UMLS Grounding:** Often missing validation that codes exist—verify every code resolves in UMLS API before storage
- [ ] **Temporal Criteria:** Often missing temporal constraint preservation—verify "within 30 days" represented in structured output
- [ ] **Conditional Logic:** Often missing nested condition handling—verify "unless controlled" represented as conditional
- [ ] **Annotation Guidelines:** Often missing edge case definitions—verify guidelines cover ambiguous cases, simplification rules, conflict resolution
- [ ] **Inter-Annotator Agreement:** Often missing ongoing monitoring—verify Cohen's kappa tracked weekly, not just initial calibration
- [ ] **Active Learning:** Often missing quality filters—verify noise detection prevents degraded PDFs from review queue
- [ ] **Error Recovery:** Often missing failed extraction handling—verify system gracefully handles timeouts, malformed PDFs, API failures
- [ ] **Audit Trail:** Often missing protocol version tracking—verify which extraction pipeline version processed each protocol
- [ ] **Data Retention:** Often missing original protocol storage—verify source PDFs stored in GCS with metadata, not just extracted data
- [ ] **Compliance:** Often missing PHI redaction—verify logs, exports, and UI don't expose patient-identifiable information

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| LLM Hallucination in Production | MEDIUM | Run validation script on all stored UMLS codes; mark invalid codes for re-grounding; reprocess affected protocols with validation enabled; notify users of corrections |
| PDF Quality Degradation Undetected | HIGH | Implement quality detection retroactively; re-score all stored PDFs; flag low-quality protocols for re-review; prioritize re-extraction of critical trials; accept some data loss |
| Criteria Complexity Lost | HIGH (possible rewrite) | Cannot fully recover—re-extract all protocols with new schema; migrate existing data to structured format; manual review of complex criteria; communicate data update to users |
| Poor Inter-Annotator Agreement | MEDIUM | Pause annotation; conduct calibration sessions; update guidelines; re-review protocols with high disagreement; calculate agreement on new sample before resuming |
| Active Learning Bias | LOW | Switch to random sampling for next batch; retrain model excluding noisy samples; validate performance on held-out test set; adjust selection criteria |
| Negation Detection Missing | MEDIUM | Add assertion detection pipeline stage; reprocess all protocols; compare before/after to quantify impact; manual review of high-stakes criteria |
| Protocol Structure Variability | HIGH | Collect diverse templates; retrain section detection; implement template-specific routing; manually fix misclassified protocols; expand training data |
| UMLS Coverage Gaps | LOW | Build local extension ontology; map novel terms to nearest UMLS neighbors; track unmappable frequencies; submit new terms to UMLS for future inclusion |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| LLM Hallucination in Medical Concept Mapping | Phase 1: Core Extraction Pipeline | Automated test: all extracted codes validate against UMLS API (100% success rate) |
| PDF Quality Degradation Breaking OCR | Phase 0: Infrastructure Setup | Manual test: process 10 fax-degraded protocols, verify quality flags and enhanced OCR routing |
| Criteria Complexity and Temporal Context Loss | Phase 1: Core Extraction Pipeline | Manual review: 20 complex oncology protocols, verify temporal/conditional preservation >90% |
| Inter-Annotator Variance Destroying Model Trust | Phase 2: HITL Review Workflow | Metric: Cohen's kappa >0.8 on 10-protocol calibration sample before production launch |
| Active Learning Selecting Uninformative Noisy Samples | Phase 2: HITL Review Workflow | A/B test: active learning vs. random sampling, verify active learning reduces annotation time by >20% |
| Negation and Assertion Detection Failures | Phase 1: Core Extraction Pipeline | Automated test: negation test set (30 negative criteria), recall >95% |
| Protocol Structure Variability Across Sponsors | Phase 0: Infrastructure Setup | Manual test: process 5 protocols from different sponsors, verify section detection accuracy >85% |
| UMLS Coverage Gaps for Novel Therapies | Phase 1: Core Extraction Pipeline | Metric: grounding success rate >70% on novel therapy protocols, with graceful fallback for failures |

## Sources

### Clinical Trial Protocol Extraction Challenges
- [Benchmarking LLM-based Information Extraction Tools for Medical Documents](https://www.medrxiv.org/content/10.64898/2026.01.19.26344287v1.full.pdf)
- [Augmenting the Clinical Trial Design Process with Information Extraction](https://snorkel.ai/blog/augmenting-the-clinical-trial-design-information-extraction/)
- [Parsable Clinical Trial Eligibility Criteria Representation Using Natural Language Processing](https://pmc.ncbi.nlm.nih.gov/articles/PMC10148319/)

### PDF Parsing and OCR Issues
- [Document Parsing Unveiled: Techniques, Challenges, and Prospects](https://arxiv.org/html/2410.21169v4)
- [Comparative Analysis of AI OCR Models for PDF to Structured Text](https://intuitionlabs.ai/pdfs/comparative-analysis-of-ai-ocr-models-for-pdf-to-structured-text.pdf)
- [The Best Way to Parse Complex PDFs for RAG](https://www.instill-ai.com/blog/the-best-way-to-parse-complex-pdfs-for-rag-hybrid-multimodal-parsing)

### LLM Medical Entity Extraction
- [Large Language Models for Data Extraction from Unstructured EHR](https://pmc.ncbi.nlm.nih.gov/articles/PMC11751965/)
- [LLM Hallucination Rates in Clinical Concept Mapping](https://medinform.jmir.org/2025/1/e71252)
- [Harnessing Healthcare-Specific LLMs for Clinical Entity Extraction](https://www.johnsnowlabs.com/harnessing-healthcare-specific-llms-for-clinical-entity-extraction/)

### UMLS and SNOMED Grounding
- [Suitability of UMLS and SNOMED-CT for Encoding Outcome Concepts](https://academic.oup.com/jamia/article/30/12/1895/7249289)
- [Improving Broad-Coverage Medical Entity Linking](https://pmc.ncbi.nlm.nih.gov/articles/PMC8952339/)
- [Efficient Biomedical Entity Linking: Clinical Text Standardization](https://arxiv.org/html/2405.15134)

### HITL Annotation Workflows
- [Preventing Diagnostic Errors in Healthcare AI with Human-in-the-Loop](https://humansintheloop.org/preventing-ai-diagnostic-errors-healthcare/)
- [Scalable HITL Annotation Pipelines for AI Success](https://www.v2solutions.com/whitepapers/hitl-annotation-pipelines-for-ai/)
- [Human-in-the-Loop Review Workflows for LLM Applications](https://www.comet.com/site/blog/human-in-the-loop/)

### Medical NLP Production Deployment
- [Why LLM Output Alone Cannot Drive Clinical Decisions](https://www.johnsnowlabs.com/why-llm-output-alone-cannot-drive-clinical-decisions-lessons-from-production-deployments/)
- [When the AI Got It Wrong: Lessons from Real-World LLM Failure](https://www.johnsnowlabs.com/when-the-ai-got-it-wrong-lessons-from-a-real-world-llm-failure/)
- [NLP in Healthcare Use Cases and Challenges](https://spsoft.com/tech-insights/nlp-in-healthcare-use-cases/)

### Protocol Standardization
- [Development of Clinical Trial Protocol Templates at NIAID](https://pmc.ncbi.nlm.nih.gov/articles/PMC2736100/)
- [Standardization of Clinical Trials](https://pmc.ncbi.nlm.nih.gov/articles/PMC5308078/)

---
*Pitfalls research for: Clinical Trial Protocol Criteria Extraction System*
*Researched: 2026-02-10*
