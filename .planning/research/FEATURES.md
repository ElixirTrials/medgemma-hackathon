# Feature Research

**Domain:** Clinical Trial Protocol Criteria Extraction & UMLS Grounding with HITL Review
**Researched:** 2026-02-10
**Confidence:** MEDIUM-HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete or unusable for clinical research.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| PDF protocol upload & storage | Standard workflow starts with protocol documents | LOW | Use GCS bucket per project requirements |
| Structured criteria extraction (inclusion/exclusion) | Core functionality - must separate criteria types | MEDIUM | Gemini API with structured output |
| UMLS/SNOMED concept normalization | Medical correctness requires standard terminologies | HIGH | UMLS MCP + concept ID mapping |
| Human review workflow (approve/reject/modify) | HITL is non-negotiable - AI errors require expert correction | MEDIUM | Per architecture review, core value prop |
| Audit trail for all changes | Regulatory/compliance expectation for clinical data | MEDIUM | Track who changed what when |
| Entity recognition in criteria text | Must identify medical concepts before grounding | MEDIUM | MedGemma via Vertex AI |
| Full-text search over criteria | Researchers need to find similar criteria across protocols | MEDIUM | PostgreSQL full-text search adequate for pilot |
| User authentication | Clinical data requires identity management | LOW | Google OAuth per project requirements |
| Batch protocol processing | Small pilot needs to process ~50 protocols efficiently | LOW | Queue-based processing acceptable |
| Basic quality metrics (extraction accuracy) | Users need confidence indicators for AI suggestions | MEDIUM | F1 score, precision/recall per entity type |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valuable for adoption and retention.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Side-by-side PDF viewer with extracted criteria | Reduces context switching - reviewer sees source and extraction together | LOW | Major usability win vs separate windows |
| Pre-annotation with confidence scores | Highlights low-confidence extractions for priority review | MEDIUM | Saves reviewer time on obvious cases |
| Inline entity linking to UMLS browser | Click medical term → see full UMLS concept with definitions, relationships | MEDIUM | Massive time saver vs manual UMLS lookups |
| Criteria template detection | Recognize common protocol patterns (age ranges, lab values, diagnosis criteria) | HIGH | AutoCriteria paper shows 89.42% F1 with templates |
| Historical criteria similarity matching | "This exclusion criterion appears in 12 other protocols" | HIGH | Helps reviewers spot inconsistencies, requires vector search (deferred) |
| Batch approval by criteria type | "Approve all age criteria" for trusted extraction patterns | LOW | Reduces review burden for high-confidence patterns |
| Export to OMOP CDM format | Enables downstream EHR integration for trial matching | HIGH | Standard but complex - defer to v1.x |
| Collaborative review annotations | Multiple reviewers can comment/discuss ambiguous criteria | MEDIUM | Defer to v1.x - single reviewer adequate for pilot |
| Criteria change tracking across protocol versions | Protocol amendments are common - track what changed | MEDIUM | Defer to v1.x - pilot uses single versions |
| Real-time extraction progress indicators | User sees PDF → criteria → entities → UMLS grounding pipeline | LOW | Better UX than black box processing |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Automatic approval without review | "Trust the AI completely" | False positives in medical NLP are dangerous - 54.7% error rate on similar terms in research | Always require human review with option for batch approval of high-confidence patterns |
| Real-time collaborative editing | "Like Google Docs for criteria" | Adds complexity (CRDTs, WebSockets) for minimal pilot value - 70% sites say tech complexity already too high | Asynchronous review workflow with notification summary |
| Custom terminology beyond UMLS | "Add our own medical terms" | Breaks interoperability - UMLS is the standard (87K+ concepts in CTKB) | Use UMLS semantic types + local aliases mapping to UMLS CUIs |
| Mobile app for review | "Review on phone/tablet" | Clinical review requires careful reading of dense medical text - small screens inadequate | Responsive web UI with tablet support, not native app |
| Automated patient matching from criteria | "Match criteria to EHR patients" | Out of scope for criteria extraction system - requires EHR integration, patient privacy | Export structured criteria for downstream trial matching systems |
| Free-text criteria without structure | "Just extract paragraphs" | Unusable for downstream systems - research shows structured extraction (entity+attribute+relation) required | Enforce OMOP CDM-like structure: entity, attribute, value, negation, temporal |
| Perfect extraction without errors | "Why do I need to review?" | Medical NLP error types: similar term confusion (T-cell vs Pre-B cell), temporal reasoning (new vs historical diagnosis), template boilerplate | Highlight low-confidence extractions, provide confidence scores, enable efficient correction |

## Feature Dependencies

```
Protocol PDF Upload
    └──requires──> PDF Storage (GCS)
    └──triggers──> Criteria Extraction

Criteria Extraction (Gemini)
    └──requires──> PDF in storage
    └──produces──> Structured criteria text
    └──triggers──> Entity Extraction

Entity Extraction (MedGemma)
    └──requires──> Criteria text
    └──produces──> Medical entities (spans, types)
    └──triggers──> UMLS Grounding

UMLS Grounding (MCP)
    └──requires──> Extracted entities
    └──requires──> UMLS MCP server running
    └──produces──> UMLS CUI + SNOMED mappings

HITL Review Workflow
    └──requires──> All pipeline stages complete
    └──enables──> Approve/Reject/Modify
    └──requires──> Audit logging

Audit Logging
    └──required-by──> HITL Review
    └──required-by──> User Authentication
    └──enables──> Compliance reporting

Side-by-side PDF Viewer
    ├──enhances──> HITL Review (reduces context switching)
    └──requires──> PDF URL from storage

Confidence Scores
    ├──enhances──> HITL Review (prioritizes attention)
    └──requires──> Entity Extraction + UMLS Grounding results

Full-text Search
    └──requires──> Criteria in database
    └──conflicts──> Vector similarity search (choose one for pilot)
```

### Dependency Notes

- **Criteria Extraction → Entity Extraction → UMLS Grounding:** Sequential pipeline stages, must complete in order
- **HITL Review requires all stages complete:** Cannot review partial results - confusing UX
- **Side-by-side PDF Viewer enhances HITL Review:** Research shows context switching is major pain point
- **Confidence Scores enable Pre-annotation strategy:** 80% AI handles, 20% expert review per 2026 best practices
- **Full-text Search conflicts with Vector Search:** Pilot should use PostgreSQL full-text; vector search deferred

## MVP Definition

### Launch With (v1)

Minimum viable product for 50-protocol pilot with clinical researchers.

- [x] **Protocol PDF upload with GCS storage** — Core workflow entry point
- [x] **Gemini-based structured criteria extraction** — Separates inclusion/exclusion criteria from protocol text
- [x] **MedGemma entity extraction** — Identifies medical concepts in criteria text
- [x] **UMLS concept grounding via MCP** — Normalizes entities to standard terminologies
- [x] **HITL review UI with approve/reject/modify** — Core value prop: expert validation
- [x] **Side-by-side PDF viewer** — Reduces context switching (key differentiator)
- [x] **Audit logging for reviews** — Compliance requirement
- [x] **Google OAuth authentication** — Identity management
- [x] **PostgreSQL full-text search** — Find criteria across protocols
- [x] **Confidence scores for extractions** — Prioritize reviewer attention (differentiator)

### Add After Validation (v1.x)

Features to add once core workflow proves valuable.

- [ ] **Batch approval by criteria type** — Reduces review burden after pattern confidence established (trigger: >100 protocols reviewed)
- [ ] **Inline UMLS browser links** — Deep linking to UMLS concept pages (trigger: reviewers request faster lookups)
- [ ] **Export to OMOP CDM format** — Enables EHR integration for trial matching (trigger: downstream system confirmed)
- [ ] **Collaborative review annotations** — Multiple reviewers comment on ambiguous criteria (trigger: team size >3 reviewers)
- [ ] **Quality metrics dashboard** — Aggregate F1/precision/recall across protocols (trigger: need to measure improvement over time)
- [ ] **Criteria change tracking** — Protocol amendment support (trigger: protocol versions arrive)
- [ ] **Real-time progress indicators** — Show pipeline stage status (trigger: UX feedback on "black box" feeling)

### Future Consideration (v2+)

Features to defer until product-market fit established and pilot scales.

- [ ] **Historical criteria similarity (vector search)** — Requires vector DB, high complexity (defer: until >500 protocols)
- [ ] **Criteria template library** — Pre-built patterns for common criteria (defer: need larger corpus to identify patterns)
- [ ] **Patient matching integration** — Connect to EHR systems (defer: separate product scope)
- [ ] **Multi-tenant isolation** — Support multiple research teams (defer: pilot is single team)
- [ ] **Mobile-optimized review** — Tablet/phone support (defer: validate desktop workflow first)
- [ ] **PII field-level encryption** — Per project requirements, deferred (defer: acceptable risk for pilot)
- [ ] **Real-time notifications** — Push alerts for new protocols (defer: small pilot doesn't need it)

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority | MVP |
|---------|------------|---------------------|----------|-----|
| PDF upload + GCS storage | HIGH | LOW | P1 | v1 |
| Structured criteria extraction (Gemini) | HIGH | MEDIUM | P1 | v1 |
| Entity extraction (MedGemma) | HIGH | MEDIUM | P1 | v1 |
| UMLS grounding (MCP) | HIGH | HIGH | P1 | v1 |
| HITL review workflow | HIGH | MEDIUM | P1 | v1 |
| Side-by-side PDF viewer | HIGH | LOW | P1 | v1 |
| Audit logging | HIGH | MEDIUM | P1 | v1 |
| Google OAuth | HIGH | LOW | P1 | v1 |
| Full-text search | MEDIUM | MEDIUM | P1 | v1 |
| Confidence scores | HIGH | MEDIUM | P1 | v1 |
| Batch approval | MEDIUM | LOW | P2 | v1.x |
| Inline UMLS links | MEDIUM | MEDIUM | P2 | v1.x |
| OMOP CDM export | MEDIUM | HIGH | P2 | v1.x |
| Quality metrics dashboard | MEDIUM | MEDIUM | P2 | v1.x |
| Collaborative annotations | LOW | MEDIUM | P2 | v1.x |
| Progress indicators | MEDIUM | LOW | P2 | v1.x |
| Vector similarity search | MEDIUM | HIGH | P3 | v2+ |
| Template library | LOW | HIGH | P3 | v2+ |
| Patient matching | LOW | HIGH | P3 | v2+ |
| Multi-tenancy | LOW | HIGH | P3 | v2+ |

**Priority key:**
- P1: Must have for pilot launch (validate core workflow)
- P2: Should have, add when pilot shows traction
- P3: Nice to have, defer until scaling beyond pilot

## Quality Gates & Success Metrics

### Extraction Quality (Table Stakes)

Clinical researchers will reject system if extraction quality is poor.

**Target metrics (based on research benchmarks):**
- **Entity extraction F1 score:** >85% (EliIE achieved 84-90%, AutoCriteria 89.42%)
- **UMLS grounding accuracy:** >80% exact match (DR.KNOWS showed 4% improvement with UMLS paths)
- **Criteria separation accuracy:** >90% (inclusion vs exclusion classification)
- **False positive rate:** <15% (research shows 54.7% error on similar medical terms - must beat this)

### HITL Review Efficiency (Differentiator)

System succeeds if it saves researchers time vs manual extraction.

**Target metrics:**
- **Time per protocol review:** <20 minutes (vs hours for manual extraction)
- **Pre-annotation acceptance rate:** >70% (validates AI quality)
- **Reviewer corrections per protocol:** <10 (indicates good AI quality)
- **Side-by-side viewer usage:** >90% of sessions (validates UX choice)

### System Reliability (Table Stakes)

**Target metrics:**
- **Pipeline success rate:** >95% (PDF → criteria → entities → UMLS)
- **Average processing time:** <5 minutes per protocol
- **Audit log completeness:** 100% (all review actions logged)
- **Authentication uptime:** >99.9% (Google OAuth dependency)

## Competitor Feature Analysis

### Research Systems (Academic Benchmarks)

| Feature | EliIE (2017) | AutoCriteria (2023) | Criteria2Query | Our Approach |
|---------|--------------|---------------------|----------------|--------------|
| Criteria extraction | Free-text parsing, 4-step pipeline | LLM-based structured extraction | NLP entity/relation | Gemini structured output |
| Entity recognition | Custom NER | LLM prompting (89.42% F1) | Criteria2Query NLP | MedGemma (Vertex AI) |
| UMLS normalization | OMOP CDM v5.0 compliant | Not specified | OMOP CDM via UMLS | UMLS MCP server |
| HITL workflow | Not mentioned | Not mentioned | Not mentioned | Core feature (differentiator) |
| Output format | OMOP CDM database | Structured entities | OMOP CDM | OMOP-compatible + JSON |
| Architecture | Local NLP pipeline | LLM API-based | Local NLP pipeline | GCP microservices + LangGraph |

### Commercial Trial Matching Platforms (2026)

| Feature | Tempus | Mount Sinai AI | Generic CTMS | Our Approach |
|---------|--------|----------------|--------------|--------------|
| Protocol ingestion | ✓ | ✓ | ✓ | GCS + Gemini extraction |
| HITL review | Minimal | ✓ | ✓ | Core focus (side-by-side UI) |
| UMLS grounding | ✓ | ✓ | Varies | UMLS MCP + SNOMED |
| EHR integration | ✓ | ✓ | ✓ | Deferred to v2 (export only) |
| Patient matching | ✓ (core feature) | ✓ (core feature) | ✓ | Out of scope (anti-feature) |
| Trial matching | ✓ (core feature) | ✓ (core feature) | ✓ | Out of scope (anti-feature) |
| Confidence scoring | Minimal | ✓ | Minimal | P1 feature (differentiator) |
| Audit compliance | ✓ | ✓ | ✓ | P1 feature (table stakes) |

**Key insight:** Commercial systems focus on **trial matching** (patient → trial). Our system focuses on **criteria extraction + grounding** (protocol → structured data). This is a narrower, more tractable scope for pilot.

**Differentiators from commercial systems:**
1. **Side-by-side PDF viewer** — Most systems separate protocol viewing from review
2. **Confidence scoring for extractions** — Guides reviewer attention to ambiguous cases
3. **UMLS MCP integration** — Leverages latest UMLS APIs vs older static databases
4. **LangGraph agent architecture** — Modular pipeline stages for easier debugging

**Acceptable gaps (not competing on):**
1. **Patient matching** — Out of scope, export to downstream systems
2. **EHR integration** — Deferred to v2, OMOP export sufficient for pilot
3. **Multi-site coordination** — Pilot is single-team only
4. **Call center / navigator services** — Pure software system, no human services

## Research Confidence Assessment

### High Confidence Areas

**HITL workflow requirements (HIGH confidence)**
- Sources: Multiple industry reports, Google Cloud HITL docs, clinical trial platforms
- Evidence: 80% of enterprises using generative AI in 2026, HITL "no longer optional" for high-stakes domains
- Validation: Existing template has HITL UI scaffold, architecture review confirmed HITL as core value

**UMLS grounding importance (HIGH confidence)**
- Sources: Multiple academic papers, UMLS documentation, CTKB knowledge base research
- Evidence: 87,504+ standard concepts in clinical trial knowledge bases, medical knowledge graphs improve LLM diagnosis by 4%
- Validation: UMLS MCP server exists in reference prototype

**Extraction quality benchmarks (HIGH confidence)**
- Sources: EliIE (JAMIA 2017), AutoCriteria (PubMed 2023), academic systematic reviews
- Evidence: F1 scores 84-90% for structured extraction, specific error types documented (similar terms, temporal reasoning)
- Validation: Multiple papers with reproducible metrics

### Medium Confidence Areas

**Differentiating features (MEDIUM confidence)**
- Sources: HITL best practices (2026), UX patterns from annotation platforms
- Evidence: Side-by-side viewer reduces context switching (general UX principle), confidence scoring enables pre-annotation strategy
- Gap: Limited specific research on clinical trial criteria review UX
- Mitigation: Validate with pilot users early

**Feature prioritization (MEDIUM confidence)**
- Sources: Clinical trial pain points research, trial matching platform features
- Evidence: 70% of sites say trials more complex in last 5 years, protocol completeness issues documented
- Gap: Small sample of commercial platform features (limited public documentation)
- Mitigation: Interview pilot users to validate priorities

### Low Confidence Areas

**Commercial platform capabilities (LOW confidence)**
- Sources: Marketing pages, press releases, limited product documentation
- Evidence: Feature lists for Tempus, Mount Sinai platform, generic CTMS systems
- Gap: Cannot access actual systems to evaluate UX, only public-facing descriptions
- Mitigation: Focus on documented pain points rather than feature parity

**Future feature demand (LOW confidence)**
- Sources: General trends (decentralized trials, representative enrollment mandates)
- Evidence: Market momentum toward hybrid trials, SPIRIT 2025 protocol guidelines
- Gap: Unclear which features pilot users will request after seeing v1
- Mitigation: Build extensible architecture, defer speculative features to v1.x/v2+

## Sources

### HITL Workflows & Best Practices
- [Human-in-the-Loop AI (HITL) - Complete Guide to Benefits, Best Practices & Trends for 2026 | Parseur](https://parseur.com/blog/human-in-the-loop-ai)
- [Human In The Loop | Clinical Trial Software | Simplified Clinical](https://www.simplifiedclinical.com/human-in-the-loop/)
- [Human-in-the-Loop Overview | Document AI | Google Cloud Documentation](https://docs.cloud.google.com/document-ai/docs/hitl)
- [Data Annotation Trends 2026: Forecast & Best Practices | Humans in the Loop](https://humansintheloop.org/data-annotation-trends-2026-forecast-best-practices/)
- [Top 6 Annotation Tools for HITL LLMs Evaluation and Domain-Specific AI Model Training - John Snow Labs](https://www.johnsnowlabs.com/top-6-annotation-tools-for-hitl-llms-evaluation-and-domain-specific-ai-model-training/)

### Clinical Trial Criteria Extraction
- [AutoCriteria: a generalizable clinical trial eligibility criteria extraction system powered by large language models - PubMed](https://pubmed.ncbi.nlm.nih.gov/37952206/)
- [EliIE: An open-source information extraction system for clinical trial eligibility criteria | Journal of the American Medical Informatics Association | Oxford Academic](https://academic.oup.com/jamia/article/24/6/1062/3098256)
- [EliIE: An open-source information extraction system for clinical trial eligibility criteria - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC6259668/)
- [Systematic Literature Review on Clinical Trial Eligibility Matching](https://arxiv.org/html/2503.00863v1)
- [The Leaf Clinical Trials Corpus: a new resource for query generation from clinical trial eligibility criteria | Scientific Data](https://www.nature.com/articles/s41597-022-01521-0)

### UMLS & Medical Concept Grounding
- [On the role of the UMLS in supporting diagnosis generation proposed by Large Language Models - PubMed](https://pubmed.ncbi.nlm.nih.gov/39142598/)
- [Large Language Models and Medical Knowledge Grounding for Diagnosis Prediction | medRxiv](https://www.medrxiv.org/content/10.1101/2023.11.24.23298641v2.full)
- [Leveraging Medical Knowledge Graphs Into Large Language Models for Diagnosis Prediction: Design and Application Study - PubMed](https://pubmed.ncbi.nlm.nih.gov/39993309/)
- [A knowledge base of clinical trial eligibility criteria - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC8407851/)
- [Improving broad-coverage medical entity linking with semantic type prediction and large-scale datasets - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC8952339/)

### OMOP CDM Standards
- [An OMOP CDM-Based Relational Database of Clinical Research Eligibility Criteria - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC5893219/)
- [Building an OMOP common data model-compliant annotated corpus for COVID-19 clinical trials - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC8079156/)

### Clinical Trial Platform Features
- [A unified framework for pre-screening and screening tools in oncology clinical trials | npj Precision Oncology](https://www.nature.com/articles/s41698-026-01306-3)
- [Mount Sinai Launches AI-Powered Clinical Trial-Matching Platform to Expand Access to Cancer Research | Mount Sinai](https://www.mountsinai.org/about/newsroom/2026/mount-sinai-launches-ai-powered-clinical-trial-matching-platform-to-expand-access-to-cancer-research)
- [Clinical trial matching - Tempus](https://www.tempus.com/oncology/clinical-trial-matching/)

### Clinical Trial Pain Points & Challenges
- [State of Clinical Trials 2025 Industry Trends and Key Insights Report](https://ccrps.org/clinical-research-blog/state-of-clinical-trials-2025-industry-trends-and-key-insights-report)
- [SPIRIT 2025 statement: updated guideline for protocols of randomized trials | Nature Medicine](https://www.nature.com/articles/s41591-025-03668-w)
- [Automatic Trial Eligibility Surveillance Based on Unstructured Clinical Data - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC6717538/)

### Medical NLP Error Analysis
- [Improving biomedical entity linking for complex entity mentions with LLM-based text simplification - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC11281847/)
- [An overview of Biomedical Entity Linking throughout the years - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC9845184/)
- [Automated classification of clinical trial eligibility criteria text based on ensemble learning and metric learning | BMC Medical Informatics and Decision Making](https://bmcmedinformdecismak.biomedcentral.com/articles/10.1186/s12911-021-01492-z)

### Evaluation Metrics
- [On evaluation metrics for medical applications of artificial intelligence - PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC8993826/)
- [Oncology's AI Moment: How LLMs Are Becoming Active Participants in Tumor Board Decisions - John Snow Labs](https://www.johnsnowlabs.com/oncologys-ai-moment-how-llms-are-becoming-active-participants-in-tumor-board-decisions/)

---
*Feature research for: Clinical Trial Protocol Criteria Extraction & UMLS Grounding with HITL Review*
*Researched: 2026-02-10*
*Confidence: MEDIUM-HIGH (High for HITL/UMLS requirements, Medium for commercial platform comparison)*
