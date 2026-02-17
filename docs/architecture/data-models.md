---
title: Data Models
date_verified: 2026-02-12
status: current
---

# Data Models

This page documents both the **database schema** (relational model for persistent storage) and the **LangGraph agent state structures** (TypedDict workflow state for agent execution).

## Database Schema

### Entity-Relationship Diagram

```mermaid
erDiagram
    Protocol ||--o{ CriteriaBatch : "has many"
    CriteriaBatch ||--o{ Criteria : "contains"
    Criteria ||--o{ Entity : "has extracted"
    Protocol ||--o{ Review : "reviewed for"
    Criteria ||--o{ Review : "reviewed for"
    Entity ||--o{ Review : "reviewed for"

    Protocol {
        string id PK
        string title
        string file_uri
        string status "enum: uploaded, extracting, grounding, pending_review, complete"
        int page_count
        float quality_score
        string error_reason
        json metadata_
        timestamp created_at
        timestamp updated_at
    }

    CriteriaBatch {
        string id PK
        string protocol_id FK
        string status "enum: pending_review, approved, rejected"
        string extraction_model "e.g., gemini-1.5-pro"
        timestamp created_at
        timestamp updated_at
    }

    Criteria {
        string id PK
        string batch_id FK
        string criteria_type "inclusion or exclusion"
        string category
        text text "criterion full text"
        json temporal_constraint
        json conditions
        json numeric_thresholds
        string assertion_status "PRESENT, ABSENT, HYPOTHETICAL, etc."
        float confidence "0.0 to 1.0"
        string source_section
        string review_status
        timestamp created_at
        timestamp updated_at
    }

    Entity {
        string id PK
        string criteria_id FK
        string entity_type "Condition, Medication, Procedure, etc."
        string text "entity surface form"
        int span_start
        int span_end
        string umls_cui "UMLS Concept Unique Identifier"
        string snomed_code
        string preferred_term
        float grounding_confidence
        string grounding_method "exact_match, semantic, expert_review"
        string review_status
        json context_window
        timestamp created_at
        timestamp updated_at
    }

    Review {
        string id PK
        string reviewer_id FK
        string target_type "Protocol, Criteria, or Entity"
        string target_id FK
        string action "approve, reject, modify"
        json before_value
        json after_value
        string comment
        timestamp created_at
    }

    AuditLog {
        string id PK
        string event_type
        string actor_id
        string target_type
        string target_id
        json details
        timestamp created_at
    }

    OutboxEvent {
        string id PK
        string event_type
        string aggregate_type
        string aggregate_id
        json payload
        string idempotency_key UK "unique constraint"
        string status "pending, published, failed"
        int retry_count
        timestamp published_at
        timestamp created_at
    }
```

### Table Descriptions

**Protocol**: Represents an uploaded clinical trial protocol PDF. Tracks extraction pipeline status from upload through criteria extraction, entity grounding, and review completion.

**CriteriaBatch**: Groups criteria extracted from a single extraction run. Enables versioning (re-extraction with different models) and batch-level approval workflow.

**Criteria**: Individual inclusion/exclusion criterion extracted from a protocol. Contains structured fields (temporal constraints, numeric thresholds) parsed from natural language text.

**Entity**: Medical entity (condition, medication, procedure, etc.) extracted from criteria text and grounded to standardized vocabularies (UMLS CUI, SNOMED code).

**Review**: Records individual review actions (approve/reject/modify) by clinical researchers. Immutable audit trail with before/after values for data lineage.

**AuditLog**: Immutable event log for all system actions (extraction, grounding, review). Enables compliance reporting and debugging.

**OutboxEvent**: Transactional outbox for reliable async event delivery to agent services. Ensures atomic database + event writes without dual-write problem.

**Note:** All tables use UUID primary keys. Protocol, CriteriaBatch, Criteria, and Entity have created_at/updated_at timestamps. Review and AuditLog are immutable (created_at only).

## LangGraph State Schemas

### PipelineState (Unified Protocol Processing Pipeline)

The `protocol-processor-service` uses `PipelineState` TypedDict to carry data through all 5 graph nodes in the unified pipeline.

```mermaid
classDiagram
    class PipelineState {
        +str protocol_id
        +str file_uri
        +str title
        +str markdown_content
        +str criteria_json
        +str entities_json
        +str grounded_entities_json
        +str criteria_batch_id
        +list~str~ errors
        +str|None error
    }

    note for PipelineState "State flow:\n1. ingest: populates markdown_content from PDF\n2. extract: populates criteria_json from Gemini\n3. parse: populates entities_json from MedGemma\n4. ground: populates grounded_entities_json via ToolUniverse + MedGemma\n5. persist: saves all to DB, populates criteria_batch_id"
```

**Field descriptions:**

| Field | Type | Populated By | Purpose |
|-------|------|--------------|---------|
| `protocol_id` | `str` | Trigger handler | UUID of protocol being processed |
| `file_uri` | `str` | Trigger handler | GCS URI (gs://) or local path (local://) of PDF |
| `title` | `str` | Trigger handler | Protocol title from upload metadata |
| `markdown_content` | `str` | `ingest` node | Parsed PDF content via pymupdf4llm |
| `criteria_json` | `str` | `extract` node | JSON-serialized criteria extracted by Gemini |
| `entities_json` | `str` | `parse` node | JSON-serialized entities extracted by MedGemma |
| `grounded_entities_json` | `str` | `ground` node | JSON-serialized entities with terminology codes |
| `criteria_batch_id` | `str` | `persist` node | ID of persisted CriteriaBatch record |
| `errors` | `list[str]` | Any node | Accumulated non-fatal errors (error accumulation pattern) |
| `error` | `str \| None` | Any node | Fatal error message; enables conditional routing to END |

**Data flow:**

```
Trigger -> ingest (parses PDF) -> extract (Gemini criteria) -> parse (MedGemma entities) -> ground (ToolUniverse + MedGemma) -> persist (DB) -> END
```

### State Design Principles

- **TypedDict over Pydantic for graph state**: Lighter weight, LangGraph native integration
- **Every state has an `error: str | None` field**: Enables conditional routing to END on failure without raising exceptions
- **Fields are populated progressively**: Each node writes its output fields; downstream nodes read them
- **Trigger handlers initialize input fields**: IDs and URIs are set at workflow start; graph nodes populate derived fields
- **State is scoped to a single workflow run**: Not shared across runs; fresh state for each protocol or batch
