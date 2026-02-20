# Agent Flow

Agentic grounding pattern used when initial entity grounding has low confidence.

```mermaid
flowchart TB
    ENT[Entity from parse node] --> DUAL[Dual grounding]

    subgraph Dual["Parallel Grounding"]
        DUAL --> TR[TerminologyRouter<br/>UMLS search]
        DUAL --> OM[OMOP Mapper<br/>concept lookup]
    end

    TR --> REC[Reconcile results]
    OM --> REC

    REC --> CONF{Confidence >= 0.5?}
    CONF -->|Yes| DONE[Accept grounding]
    CONF -->|No| AGENT[Agentic retry loop]

    subgraph Retry["MedGemma Reasoning (max 3)"]
        AGENT --> Q1[Is entity valid<br/>for coding?]
        Q1 -->|Yes| Q2[Derive broader<br/>concept?]
        Q1 -->|No| SKIP[Skip entity]
        Q2 --> Q3[Rephrase for<br/>better match?]
        Q3 --> RETRY[Retry grounding<br/>with improved input]
    end

    RETRY --> CONF2{Improved?}
    CONF2 -->|Yes| DONE
    CONF2 -->|No, attempts left| AGENT
    CONF2 -->|No, exhausted| EXPERT[Route to<br/>expert review]

    style DONE fill:#22c55e,color:#fff
    style EXPERT fill:#f59e0b,color:#fff
    style SKIP fill:#ef4444,color:#fff
```

## Grounding Pipeline Details

### TerminologyRouter

Routes entities to the best UMLS source vocabulary based on entity type:

| Entity type | Primary vocabulary | Fallback |
|-------------|-------------------|----------|
| condition | SNOMED CT | ICD-10 |
| measurement | LOINC | SNOMED CT |
| drug | RxNorm | SNOMED CT |
| procedure | SNOMED CT | CPT |

### OMOP Mapper

Resolves entities to OMOP CDM concept IDs using the OMOP vocabulary tables. Enables direct joins against CDM data warehouses.

### Reconciliation

`_reconcile_dual_grounding()` merges results from both paths:

- Prefers OMOP concept ID when available (needed for exports)
- Falls back to source terminology codes
- Combines confidence scores from both paths

**File**: `services/protocol-processor-service/src/protocol_processor/nodes/ground.py`
