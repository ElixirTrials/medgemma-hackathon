# ElixirTrials: AI-Powered Clinical Trial Eligibility Criteria Extraction

## Your Team

**Noah Dolev** (noah@elixirtrials.com) &mdash; Software engineering, AI pipeline architecture, system design
**Maxime Gendre** (maxime@elixirtrials.com) &mdash; Clinical informatics, terminology grounding, product design

**Special Award Track**: Agentic Workflow Prize

---

## Problem Statement

Clinical trial eligibility criteria are buried in unstructured PDF protocols. Manually extracting, coding, and structuring these criteria takes **40+ hours per trial**. With over 300,000 active trials on ClinicalTrials.gov, this bottleneck directly delays:

- **Cohort identification** for observational studies using OHDSI/OMOP networks
- **Patient-trial matching** for recruitment optimization
- **Feasibility analysis** for site selection and protocol design

The users are **clinical informaticists, trial coordinators, and OHDSI researchers** who need structured, standards-coded eligibility criteria to query patient databases. Today they manually read protocols, identify criteria, look up terminology codes, and build cohort definitions &mdash; a tedious, error-prone process that demands both clinical expertise and informatics knowledge.

**With ElixirTrials**: Upload a protocol PDF, review AI-extracted criteria in a split-pane interface, approve or correct, and export to OHDSI CIRCE, FHIR R4, or OMOP SQL &mdash; reducing the process from days to minutes.

---

## Overall Solution: Effective Use of HAI-DEF Models

ElixirTrials uses a **two-model architecture** built around MedGemma 4B-IT and Gemini 2.5 Flash:

**MedGemma 4B-IT** (`google/medgemma-4b-it`) serves as the **medical reasoning agent**. For each extracted entity, MedGemma evaluates terminology candidates from 6 vocabulary systems (UMLS, SNOMED CT, LOINC, RxNorm, ICD-10, HPO) and selects the best match with confidence scoring and clinical reasoning.

When initial grounding confidence is low (< 0.5), MedGemma enters an **agentic retry loop**, asking three reasoning questions:
1. Is this a valid medical criterion (or should it be skipped)?
2. Is this a derived entity mapping to a more standard concept?
3. Can this entity be rephrased for better terminology search?

This loop runs up to 3 attempts, with MedGemma reformulating queries and retrying grounding at each step. Entities that exhaust all attempts are routed to expert review.

**Gemini 2.5 Flash** handles PDF extraction (structured output from protocol documents) and structures MedGemma's free-form reasoning into validated Pydantic models.

**Why MedGemma over alternatives**: General-purpose LLMs lack biomedical domain knowledge needed to distinguish between similar medical concepts (e.g., differentiating NYHA Class III from ECOG Performance Status 3). MedGemma's biomedical training provides the domain expertise that makes accurate terminology grounding possible. Its open-weight design also enables local deployment with 4-bit quantization, preserving patient data privacy.

---

## Technical Details

### Pipeline Architecture

A **7-node LangGraph StateGraph** with PostgreSQL checkpointing:

`ingest` &rarr; `extract` &rarr; `parse` &rarr; `ground` &rarr; `persist` &rarr; `structure` &rarr; `ordinal_resolve`

Each node is checkpointed, enabling resume-from-failure. The ground node runs **dual grounding** (TerminologyRouter + OMOP mapper) in parallel per entity with semaphore-controlled concurrency.

### User-Facing Application

- **React/Vite frontend** with split-pane PDF viewer and criteria review interface
- **FastAPI backend** with auth, protocol management, batch review, and export endpoints
- **Three export formats**: OHDSI CIRCE JSON (cohort definition), FHIR R4 Group (interoperability), OMOP CDM SQL (direct database query)

### Deployment

- **Docker Compose** for full-stack local deployment (PostgreSQL, API, UI, MLflow)
- **Vertex AI** for production MedGemma inference
- **Local GPU** with 4-bit quantization for privacy-preserving deployment (8 GB VRAM)
- **MLflow** for experiment tracking and pipeline tracing

### Agentic Workflow Prize Justification

ElixirTrials is a textbook agentic workflow:
- **Autonomous multi-step processing**: 7 LangGraph nodes with conditional error routing
- **AI decision-making**: MedGemma autonomously evaluates and selects terminology matches
- **Tool use**: TerminologyRouter dispatches to 6 vocabulary APIs; OMOP mapper queries CDM concepts
- **Feedback loops**: 3-question reasoning retry with query reformulation
- **Human-in-the-loop**: Clinician review interface as the final safety gate
- **Error recovery**: Entity-level error accumulation, expert review escalation, checkpoint resume

### Impact Potential

- **Time savings**: 40+ hours manual &rarr; ~5 minutes automated per protocol
- **Scale**: 300,000+ active trials globally, with thousands of new protocols annually
- **Downstream value**: Standards-ready outputs (CIRCE, FHIR, OMOP SQL) plug directly into the OHDSI network serving 800+ data partners across 80+ countries
- **Privacy**: Local MedGemma deployment enables processing of sensitive protocol data without cloud dependencies

**Code repository**: [github.com/ElixirTrials/medgemma-hackathon](https://github.com/ElixirTrials/medgemma-hackathon)
