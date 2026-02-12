---
title: "Upload & Extraction Journey"
date_verified: 2026-02-12
status: current
---

# Upload & Extraction Journey

## User Story

**Who:** Clinical researcher with a protocol PDF

**Goal:** Get structured inclusion/exclusion criteria extracted automatically without manual data entry

**Why it matters:** Manual criteria extraction takes 2-4 hours per protocol. This workflow automates the entire process, reducing time to approximately 5 minutes and ensuring consistent structured output for downstream grounding and review.

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

When a clinical researcher uploads a protocol PDF, they're initiating an end-to-end automated pipeline that will extract structured eligibility criteria ready for human review. The upload mechanism is designed for reliability and performance at scale.

The upload happens client-side using Google Cloud Storage signed URLs. This architectural decision means large PDFs (50+ MB) never pass through our API servers, avoiding memory pressure and keeping upload latency low regardless of file size. The HITL UI first requests a signed URL from the API Service, then uploads the PDF directly to GCS using that time-limited URL.

Once the upload completes, the API Service stores a Protocol record in PostgreSQL with key metadata: original filename, file size, page count (estimated from PDF metadata), and a unique file URI pointing to the GCS object. The status field is set to "uploaded", beginning the protocol's state progression through the pipeline.

Critically, the API Service also creates an OutboxEvent record with type "ProtocolUploaded" in the same database transaction as the Protocol record. This transactional outbox pattern guarantees that the event won't be lost even if the API service crashes immediately after the Protocol is created—the event is durably persisted in the database, waiting to be processed.

### Action: Asynchronous Extraction

The real extraction work happens asynchronously, decoupled from the upload request-response cycle. This means the researcher gets instant feedback ("Protocol uploaded successfully!") while extraction runs in the background without blocking the UI.

Within 5-10 seconds, the Outbox Processor service polls the database for pending OutboxEvent records and finds the ProtocolUploaded event. It triggers the Extraction Service's `handle_protocol_uploaded` function, passing the protocol ID and file URI as parameters.

The Extraction Service follows a four-stage workflow powered by LangGraph:

1. **Download**: Fetch the PDF from GCS using the file_uri. For large files, this uses streaming download to avoid loading the entire PDF into memory.

2. **Parse**: Use pymupdf4llm to extract text while preserving document structure. This library is specifically chosen because it maintains tables, multi-column layouts, and formatting context that Gemini needs for accurate extraction. For a typical 50-page protocol, this step takes 10-15 seconds.

3. **Extract**: Send the parsed text to Gemini API with a specialized prompt that requests structured JSON output. The prompt instructs Gemini to identify:
   - **Type**: Inclusion or exclusion criterion
   - **Category**: Demographic, medical history, biomarker, medication, procedure, etc.
   - **Temporal constraints**: Time windows like "within 30 days of enrollment" or "at least 6 months prior"
   - **Numeric thresholds**: Quantitative limits like "eGFR >= 60 mL/min" or "age 18-65 years"
   - **Confidence score**: A 0.0-1.0 value indicating Gemini's certainty in the extraction

   Gemini returns a JSON array of criteria, each with these structured fields. For a protocol with 20-30 criteria, this extraction typically takes 30-60 seconds depending on Gemini API latency.

4. **Store**: Write a CriteriaBatch record to PostgreSQL containing metadata about the extraction (model version, extraction timestamp, quality metrics), then insert individual Criteria records linked to the batch. Each criterion includes the extracted structured data plus the original text span from the protocol for human verification.

### Resolution: Ready for Grounding

Once all criteria are stored, the Extraction Service publishes a CriteriaExtracted event via the transactional outbox, triggering the next phase: entity grounding with UMLS and SNOMED CT codes (see [Grounding & HITL Review](./grounding-review.md)).

From the researcher's perspective, they can check the protocol's status in the review queue. The status progresses through a visible state machine:
- **uploading** → **extracting** → **grounding** → **pending_review**

Once extraction completes (typically 2-3 minutes total for a 50-page protocol), the status updates to "grounding" and the extraction summary shows the number of criteria extracted. The researcher doesn't need to monitor this—they can navigate away and return later when the protocol reaches "pending_review" status.

The asynchronous, event-driven architecture means researchers can upload multiple protocols in parallel without waiting for each extraction to complete. The system processes them concurrently, with each protocol progressing through the pipeline independently.

## What Could Go Wrong?

This diagram shows the happy path only. For error scenarios and recovery mechanisms, see:

- **PDF quality issues** (scanned images, corrupted files, password-protected PDFs): [API Service: PDF Quality Validation](../components/api-service.md#pdf-quality)
- **Gemini extraction failures** (rate limits, timeouts, malformed responses): [Extraction Service: Error Handling](../components/extraction-service.md#error-handling)
- **Timeout and retry logic** (transient failures, circuit breaker patterns): [Extraction Service: Retry Patterns](../components/extraction-service.md#retry-patterns)
- **Dead letter queue** (permanently failed events after max retries): [System Architecture: Dead Letter Handling](../architecture/system-architecture.md#dead-letter-handling)

## Next Steps

- **For users**: After extraction completes, protocols enter the grounding phase where medical entities are mapped to standardized UMLS and SNOMED codes. See [Grounding & HITL Review Journey](./grounding-review.md)

- **For engineers**: To understand the extraction LangGraph workflow internals, state machine transitions, and prompt engineering details, see [Extraction Service Deep Dive](../components/extraction-service.md)
