# HITL Flow

Human-in-the-loop review workflow from criteria extraction to final approval.

```mermaid
flowchart TB
    subgraph Pipeline["Automated Pipeline"]
        EX[Extract criteria<br/>from PDF] --> PA[Parse into<br/>DB records]
        PA --> GR[Ground entities<br/>to terminologies]
        GR --> PE[Persist to DB]
        PE --> ST[Build expression<br/>trees]
        ST --> OR[Resolve ordinal<br/>scales]
    end

    OR --> PR{Protocol status?}
    PR -->|pending_review| RQ[Review Queue]
    PR -->|grounding_failed| FAIL[Error state]
    FAIL -->|retry| EX

    subgraph Review["HITL Review"]
        RQ --> REV[Clinician reviews<br/>each criterion]
        REV -->|Approve| APP[Mark approved]
        REV -->|Reject| REJ[Mark rejected]
        REV -->|Modify| MOD[Edit + approve]
    end

    APP --> DONE{All reviewed?}
    REJ --> DONE
    MOD --> DONE
    DONE -->|Yes| COMP[Protocol complete]
    DONE -->|No| RQ

    COMP --> EXPORT[Export]
    EXPORT --> CIRCE[CIRCE JSON]
    EXPORT --> FHIR[FHIR R4 Group]
    EXPORT --> SQL[OMOP SQL]
```

## Review States

| State | Meaning |
|-------|---------|
| `null` (pending) | Not yet reviewed |
| `approved` | Clinician confirmed AI output |
| `rejected` | Clinician marked as incorrect |
| `modified` | Clinician provided corrections |

## Audit Trail

Every review action creates a `Review` record with:

- `before_value` — state before the action
- `after_value` — state after the action
- `reviewer_id` — who performed the action
- `comment` — optional notes

System-level events (grounding, status transitions) are logged to `AuditLog`.
