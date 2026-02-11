# HITL Flow

```mermaid
sequenceDiagram
    participant Researcher as Clinical<br/>Researcher
    participant UI as HITL<br/>Review UI
    participant API as API<br/>Service
    participant Extract as Extraction<br/>Service
    participant Ground as Grounding<br/>Service
    participant DB as PostgreSQL

    Researcher->>UI: Upload Protocol PDF
    UI->>API: Create Protocol (GCS Signed URL)
    API->>DB: Store Protocol Record
    API->>Extract: ProtocolUploaded Event

    Extract->>Extract: Parse PDF (pymupdf4llm)
    Extract->>Extract: Extract Criteria (Gemini)
    Extract->>API: CriteriaExtracted Event
    API->>DB: Store CriteriaBatch

    API->>Ground: CriteriaExtracted Event
    Ground->>Ground: Extract Entities (MedGemma)
    Ground->>Ground: Ground to UMLS/SNOMED (MCP)
    Ground->>API: EntitiesGrounded Event
    API->>DB: Store Grounded Entities

    Researcher->>UI: Open Review Queue
    UI->>API: Fetch Pending Batches
    API->>Researcher: Criteria + Entities + PDF

    alt Researcher Approves
        Researcher->>UI: Approve Criterion
        UI->>API: POST Review Action
        API->>DB: Log Audit Event
    else Researcher Modifies
        Researcher->>UI: Edit + Approve
        UI->>API: POST Review Action (with changes)
        API->>DB: Log Before/After in Audit
    end

    Note over DB: Full audit trail with<br/>reviewer, timestamp, action

    %% Styling
    style Researcher fill:#f9f9f9,stroke:#333,stroke-width:2px
    style UI fill:#e1f5ff,stroke:#007acc,stroke-width:2px
    style API fill:#d4f1d4,stroke:#28a745,stroke-width:2px
    style Extract fill:#ffe5cc,stroke:#fd7e14,stroke-width:2px
    style Ground fill:#ffe5cc,stroke:#fd7e14,stroke-width:2px
    style DB fill:#fff3cd,stroke:#ffc107,stroke-width:2px
```
