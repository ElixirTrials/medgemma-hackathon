---
title: "Upload & Extraction Journey"
date_verified: 2026-02-12
status: current
---

# Upload & Extraction Journey

## User Story

**Who:** Clinical researcher with a protocol PDF

**Goal:** Get structured inclusion/exclusion criteria extracted automatically without manual data entry

**Why it matters:** Manual criteria extraction takes 2-4 hours per protocol. This workflow automates it, reducing time to approximately 5 minutes and ensuring consistent structure for downstream grounding and review.

## Runtime Flow

```mermaid
sequenceDiagram
    participant Researcher as Clinical<br/>Researcher
    participant UI as HITL<br/>Review UI
    participant API as API<br/>Service
    participant GCS as GCS<br/>Bucket
    participant Outbox as Outbox<br/>Processor
    participant Extract as Extraction<br/>Service
    participant Gemini as Gemini<br/>API
    participant DB as PostgreSQL

    Note over Researcher,DB: UPLOAD & EXTRACTION JOURNEY (HAPPY PATH)

    Researcher->>UI: Upload Protocol PDF
    UI->>API: POST /protocols (request signed URL)
    API->>GCS: Generate signed upload URL
    GCS-->>API: Signed URL
    API-->>UI: Signed URL
    UI->>GCS: Upload PDF via signed URL
    GCS-->>UI: Upload complete

    UI->>API: POST /protocols (confirm upload)
    API->>DB: Store Protocol (status=uploaded)
    API->>DB: Store OutboxEvent (ProtocolUploaded)
    API-->>UI: Protocol created

    Note over API,Extract: Asynchronous Event Processing

    Outbox->>DB: Poll pending events
    DB-->>Outbox: ProtocolUploaded event
    Outbox->>Extract: Trigger handle_protocol_uploaded

    Extract->>GCS: Download PDF
    GCS-->>Extract: PDF content
    Extract->>Extract: Parse PDF (pymupdf4llm)
    Extract->>Gemini: Extract criteria with prompt
    Gemini-->>Extract: Structured criteria JSON

    Extract->>DB: Store CriteriaBatch
    Extract->>DB: Store OutboxEvent (CriteriaExtracted)
    Extract-->>Outbox: Processing complete
    Outbox->>DB: Mark event published

    Note over DB: Extraction complete,<br/>ready for grounding

    %% Styling
    style Researcher fill:#f9f9f9,stroke:#333,stroke-width:2px
    style UI fill:#e1f5ff,stroke:#007acc,stroke-width:2px
    style API fill:#d4f1d4,stroke:#28a745,stroke-width:2px
    style Extract fill:#ffe5cc,stroke:#fd7e14,stroke-width:2px
    style Gemini fill:#ffe5cc,stroke:#fd7e14,stroke-width:2px
    style GCS fill:#fff3cd,stroke:#ffc107,stroke-width:2px
    style Outbox fill:#d4f1d4,stroke:#28a745,stroke-width:2px
    style DB fill:#fff3cd,stroke:#ffc107,stroke-width:2px
```

## Narrative Explanation

### Setup: The Upload Experience

When a clinical researcher uploads a protocol PDF, they're initiating an end-to-end automated pipeline that will extract structured criteria ready for human review and grounding.

The upload happens client-side using Google Cloud Storage signed URLs. This design decision means large PDFs (50+ MB) never pass through our API servers, avoiding memory issues and keeping upload latency low. The HITL UI requests a signed URL from the API Service, then uploads the file directly to GCS—no sensitive protocol data traverses our backend during the upload phase.

Once the upload completes, the API Service stores a Protocol record with metadata: page count, file size, and a file URI pointing to the GCS location. This metadata will be used in downstream stages to optimize processing (e.g., skipping OCR for text-native PDFs).

### Action: Asynchronous Extraction

The real work happens asynchronously via the **transactional outbox pattern**. The API Service inserts an OutboxEvent record (`ProtocolUploaded`) in the same database transaction as the Protocol, guaranteeing the event won't be lost even if the service crashes immediately after.

Within 5 seconds, the **Outbox Processor** polls pending events from the database and triggers the Extraction Service by calling its `handle_protocol_uploaded` function. This decoupling means the frontend gets an instant response ("Protocol uploaded successfully!") while extraction runs in the background.

The **Extraction Service** follows a four-stage workflow:

1. **Download**: Fetch the PDF from GCS using the `file_uri` stored in the Protocol record
2. **Parse**: Use **pymupdf4llm** to extract text, preserving tables and multi-column layouts. This tool is specifically designed for LLM input preparation and handles complex protocol formatting (e.g., nested inclusion/exclusion lists, tabular criteria) better than generic PDF parsers
3. **Extract**: Send parsed text to **Gemini** with a specialized prompt that requests structured JSON output containing inclusion/exclusion criteria
4. **Store**: Write a `CriteriaBatch` record (representing the full set of extracted criteria) and individual `Criteria` records to PostgreSQL

Each criterion includes:

- **Type**: `inclusion` or `exclusion`
- **Category**: `demographic`, `medical_history`, `biomarker`, `medication`, `procedure`, or `other`
- **Text**: The criterion as extracted from the protocol
- **Temporal constraints**: If present (e.g., "within 30 days of enrollment")
- **Numeric thresholds**: If present (e.g., "eGFR >= 60 mL/min")
- **Confidence score**: 0.0 to 1.0, indicating Gemini's confidence in the extraction accuracy

The structured output from Gemini uses **JSON schema validation** to ensure criteria conform to the expected structure before being stored in the database.

### Resolution: Ready for Grounding

Once all criteria are stored, the Extraction Service publishes a **CriteriaExtracted** event via the outbox. This triggers the next phase: entity grounding (see [Grounding & HITL Review Journey](./grounding-review.md)).

From the researcher's perspective, they can now see the protocol in their queue with status **"extracting"**. Once extraction completes (typically 2-3 minutes for a 50-page protocol), the status updates to **"grounding"** and eventually **"pending_review"** when ready for human validation.

The transactional outbox pattern guarantees **at-least-once delivery**: if the Extraction Service crashes mid-processing, the Outbox Processor will retry the event. The Extraction Service implements idempotency checks to avoid duplicate CriteriaBatch records on retries.

## What Could Go Wrong?

This diagram shows the **happy path only**. For error scenarios, see future component documentation:

- **PDF quality issues** (corrupted files, scanned images without OCR): API Service component docs (coming in Phase 11)
- **Gemini extraction failures** (rate limits, malformed responses, low confidence scores): Extraction Service component docs (coming in Phase 11)
- **Timeout and retry logic** (long-running extractions, transient failures): Extraction Service component docs (coming in Phase 11)
- **Dead letter queue** (events that fail after max retries): See [System Architecture](../architecture/system-architecture.md) Production Hardening section

## Next Steps

- **For users:** After extraction completes, protocols enter the grounding phase where medical entities (diseases, drugs, biomarkers) are identified and linked to UMLS/SNOMED codes. See [Grounding & HITL Review Journey](./grounding-review.md)
- **For engineers:** To understand the extraction LangGraph workflow internals, see Extraction Service component docs (coming in Phase 11)
