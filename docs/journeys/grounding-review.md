---
title: "Grounding & HITL Review Journey"
date_verified: 2026-02-12
status: current
---

# Grounding & HITL Review Journey

## User Story

**Who:** Clinical researcher reviewing extracted criteria

**Goal:** Verify that extracted criteria have accurate UMLS/SNOMED codes assigned and approve them for downstream use

**Why it matters:** Automated grounding reduces manual medical coding from hours to minutes by leveraging MedGemma for entity extraction and MCP-based UMLS/SNOMED linking. Human review ensures accuracy for patient safety—a single incorrectly grounded criterion could exclude eligible patients or include ineligible ones, directly impacting trial success and participant wellbeing.

## Runtime Flow

```mermaid
sequenceDiagram
    participant Outbox as Outbox<br/>Processor
    participant Ground as Grounding<br/>Service
    participant MedGemma as MedGemma<br/>(Vertex AI)
    participant MCP as UMLS<br/>MCP Server
    participant UMLS as UMLS<br/>REST API
    participant DB as PostgreSQL
    participant API as API<br/>Service
    participant UI as HITL<br/>Review UI
    participant Reviewer as Clinical<br/>Researcher

    Note over Outbox,Reviewer: GROUNDING & HITL REVIEW JOURNEY (HAPPY PATH)

    Note over Outbox: CriteriaExtracted event published
    Outbox->>DB: Poll pending events
    DB-->>Outbox: CriteriaExtracted event
    Outbox->>Ground: Trigger handle_criteria_extracted

    Ground->>DB: Fetch CriteriaBatch + Criteria
    DB-->>Ground: Criteria text
    Ground->>MedGemma: Extract medical entities
    Note over Ground,MedGemma: Identify entity spans<br/>with types
    MedGemma-->>Ground: Entity spans + types

    loop For each entity
        Ground->>MCP: Tool call: concept_search(entity_text)
        MCP->>UMLS: Search concepts by text
        UMLS-->>MCP: UMLS CUI candidates with scores
        MCP-->>Ground: Grounded CUI + confidence

        Ground->>MCP: Tool call: get_snomed_code(CUI)
        MCP->>UMLS: Validate CUI and retrieve SNOMED
        UMLS-->>MCP: SNOMED code
        MCP-->>Ground: SNOMED code
    end

    Ground->>DB: Store Entity records with codes
    Ground->>DB: Store OutboxEvent (EntitiesGrounded)
    Ground-->>Outbox: Processing complete
    Outbox->>DB: Mark event published

    Note over UI,Reviewer: Human-in-the-Loop Review

    Reviewer->>UI: Open review queue
    UI->>API: GET /criteria/batches?status=pending_review
    API->>DB: Query pending batches
    DB-->>API: CriteriaBatch + Criteria + Entities
    API-->>UI: Review data + PDF signed URL
    UI-->>Reviewer: Display split-screen view

    Note over Reviewer,UI: PDF left, criteria + entities right

    Reviewer->>UI: Review criterion (approve/modify/reject)
    UI->>API: POST /reviews
    API->>DB: Store Review + AuditLog (before/after)
    API-->>UI: Review recorded

    Note over DB: Audit trail complete

    %% Styling
    style Ground fill:#ffe5cc,stroke:#fd7e14,stroke-width:2px
    style MedGemma fill:#ffe5cc,stroke:#fd7e14,stroke-width:2px
    style MCP fill:#ffe5cc,stroke:#fd7e14,stroke-width:2px
    style UMLS fill:#fff3cd,stroke:#ffc107,stroke-width:2px
    style Outbox fill:#d4f1d4,stroke:#28a745,stroke-width:2px
    style DB fill:#fff3cd,stroke:#ffc107,stroke-width:2px
    style API fill:#d4f1d4,stroke:#28a745,stroke-width:2px
    style UI fill:#e1f5ff,stroke:#007acc,stroke-width:2px
    style Reviewer fill:#f9f9f9,stroke:#333,stroke-width:2px
```

## Narrative Explanation

### Setup: From Extraction to Grounding

When the Extraction Service completes its work (see [Upload & Extraction Journey](./upload-extraction.md)), it publishes a **CriteriaExtracted** event containing the protocol ID and batch ID. This event enters the transactional outbox queue, where the **Outbox Processor** picks it up and triggers the Grounding Service.

The **Grounding Service's mission** is to identify medical entities (diseases, medications, procedures, lab values, demographics, biomarkers) within the extracted criteria text and assign them standardized **UMLS CUIs** (Concept Unique Identifiers) and **SNOMED CT codes**. This grounding process is critical for downstream matching: patient records use SNOMED codes for conditions and medications, so criteria must speak the same language to enable automated eligibility checking.

Without grounding, a criterion like "Patients with chronic kidney disease" would be just plain text—useless for matching against a patient's EHR where CKD might be coded as `SNOMED:709044004`. With grounding, the system can confidently match `UMLS:C1561643` (Chronic Kidney Diseases) to `SNOMED:709044004`, enabling automated eligibility determination.

### Action: Entity Recognition and Code Assignment

The grounding workflow operates in two distinct phases:

**Phase 1: Entity Extraction with MedGemma**

The Grounding Service sends the criteria text to **MedGemma** (Google's medical-domain language model running on Vertex AI) with a prompt requesting entity extraction. MedGemma returns structured JSON containing:

- **Entity spans**: Character offsets in the original text (e.g., "chronic kidney disease" at positions 15-39)
- **Entity types**: One of six categories:
  - `Condition` (diseases, disorders)
  - `Medication` (drugs, therapies)
  - `Procedure` (surgeries, interventions)
  - `Lab_Value` (test results, biomarkers)
  - `Demographic` (age, gender, ethnicity)
  - `Biomarker` (genetic markers, protein levels)

This entity typing guides the grounding strategy—different entity types benefit from different UMLS search approaches (e.g., medications use RxNorm subset, procedures use CPT-focused search).

**Phase 2: UMLS/SNOMED Grounding via MCP**

For each extracted entity, the Grounding Service uses the **UMLS MCP Server**—an Model Context Protocol server adapted from the gemma-hackathon repository. The MCP server pattern is crucial here: it allows the LangGraph agent running inside the Grounding Service to **dynamically decide which UMLS operations to invoke** based on intermediate results.

The typical grounding flow for a single entity involves two MCP tool calls:

1. **`concept_search(entity_text, entity_type)`**: Searches the UMLS REST API for matching concepts. Returns candidate CUIs with confidence scores using a **tiered strategy**:
   - **Exact match** (confidence 0.95): Entity text exactly matches a UMLS preferred term
   - **Word search** (confidence 0.75): Entity text matches a synonym or variant
   - **Fuzzy match** (confidence 0.50): Partial match requiring disambiguation
   - **No match** (confidence 0.0): Routes to expert review queue

2. **`get_snomed_code(CUI)`**: Validates the selected CUI and retrieves its corresponding SNOMED CT code via UMLS's concept mapping tables. If multiple SNOMED codes exist for one CUI (common for medications with multiple formulations), the MCP server applies domain-specific heuristics to select the most appropriate code.

The MCP server also implements **caching**: frequently seen entities (e.g., "diabetes mellitus type 2") are cached to avoid redundant API calls, reducing grounding latency from 2-3 seconds per entity to <100ms for cache hits.

### Resolution: Human Review and Audit Trail

Once all entities are grounded and stored in the database, the system publishes an **EntitiesGrounded** event. At this point, the criteria batch enters **HITL Review status: pending_review**.

**The Review Experience:**

The clinical researcher opens the HITL Review UI and navigates to their review queue. The UI fetches pending batches via `GET /criteria/batches?status=pending_review` and displays them in a **split-screen layout**:

- **Left pane**: The original protocol PDF, fetched from GCS via a signed URL. The PDF viewer highlights text segments corresponding to the extracted criteria (using character offsets stored during extraction).
- **Right pane**: A list of extracted criteria, each showing:
  - The criterion text
  - Its type (inclusion/exclusion) and category (demographic, medical history, etc.)
  - All extracted entities with their assigned UMLS CUIs and SNOMED codes
  - Confidence scores for each entity grounding

For each criterion, the reviewer can:

- **Approve**: Accept the extraction and grounding as-is
- **Modify**: Edit the criterion text or adjust entity codes (e.g., select a different SNOMED code from the candidate list)
- **Reject**: Mark the criterion as incorrectly extracted, triggering re-extraction or expert review

**Why Human Review Matters:**

Despite MedGemma's high accuracy (typically >90% precision on entity extraction in our testing), human validation is essential for three reasons:

1. **Patient safety**: A single incorrectly grounded criterion could exclude eligible patients or include ineligible ones
2. **AI confidence validation**: Low-confidence groundings (< 0.70) require expert judgment
3. **Edge cases**: Novel biomarkers, emerging therapies, or protocol-specific terminology may not exist in UMLS yet

**The Audit Trail:**

Every review action is logged to the **AuditLog table** with:

- `reviewer_id`: Who performed the action
- `timestamp`: When it occurred
- `action`: `approved`, `modified`, or `rejected`
- `before_value`: Original criterion text and entity codes
- `after_value`: Modified values (if applicable)
- `reasoning`: Optional free-text explanation

This audit trail satisfies regulatory requirements for clinical trial documentation (FDA 21 CFR Part 11, GDPR Article 30) and enables quality monitoring: if one reviewer consistently rejects AI groundings, it may indicate prompt tuning is needed.

Once all criteria in a batch are reviewed, the batch status updates to `reviewed`, and the criteria become available for downstream matching against patient records.

## What Could Go Wrong?

This diagram shows the **happy path only**. For error scenarios, see future component documentation:

- **Entity extraction failures** (MedGemma API errors, timeout, malformed responses): Grounding Service component docs (coming in Phase 11)
- **UMLS API unavailability** (rate limits, downtime, authentication issues): Grounding Service component docs (coming in Phase 11)
- **MCP server connection issues** (network failures, MCP protocol errors, tool call timeout): Grounding Service component docs (coming in Phase 11)
- **Review conflicts** (two reviewers modifying the same criterion simultaneously): API Service component docs (coming in Phase 11)

## Related Pages

- **[Upload & Extraction Journey](./upload-extraction.md)**: The preceding chapter—how protocols are uploaded and criteria extracted
- **[System Architecture](../architecture/system-architecture.md)**: High-level container diagram showing all services and their relationships
- **[Data Models](../architecture/data-models.md)**: Database schema for Entity, Review, and AuditLog tables
- **[HITL Flow Diagram](../diagrams/hitl-flow.md)**: Combined end-to-end sequence diagram covering both journeys
