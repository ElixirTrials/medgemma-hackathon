---
title: System Architecture
date_verified: 2026-02-12
status: current
---

# System Architecture

This document provides the C4 Container (Level 2) view of the Clinical Trial Criteria Extraction System. It shows the system's high-level structure, technology stack choices, and how services communicate with each other and external systems.

## Container Diagram

The following diagram shows the major deployable containers in the system, their technologies, and their relationships.

```mermaid
C4Container
    title Container Diagram: Clinical Trial Criteria Extraction System

    Person(researcher, "Clinical Researcher", "Reviews extracted criteria and approves/rejects them")

    System_Boundary(system, "Criteria Extraction System") {
        Container(ui, "HITL Review UI", "React, TypeScript, Vite", "Web interface for protocol upload and criteria review")
        Container(api, "API Service", "FastAPI, Python", "REST API orchestrating workflows and serving frontend")
        Container(extract, "Extraction Service", "LangGraph, Python", "Agent extracting criteria from PDFs via Gemini")
        Container(ground, "Grounding Service", "LangGraph, Python", "Agent grounding entities to UMLS/SNOMED via MCP")
        ContainerDb(db, "Database", "PostgreSQL", "Stores protocols, criteria, entities, audit logs")
    }

    Container_Ext(gcs, "GCS Bucket", "Google Cloud Storage", "PDF storage")
    Container_Ext(gemini, "Gemini API", "Google AI", "Criteria extraction LLM")
    Container_Ext(medgemma, "MedGemma", "Vertex AI", "Medical entity extraction")
    Container_Ext(umls_mcp, "UMLS MCP Server", "FastMCP, Python", "UMLS concept search and linking")
    Container_Ext(umls_api, "UMLS REST API", "NIH NLM", "UMLS concept validation")

    Rel(researcher, ui, "Uses", "HTTPS")
    Rel(ui, api, "API calls", "REST/JSON")
    Rel(api, db, "Reads/writes", "SQLAlchemy")
    Rel(api, extract, "Triggers via outbox events", "Transactional outbox")
    Rel(api, ground, "Triggers via outbox events", "Transactional outbox")
    Rel(api, gcs, "Signed URLs", "GCS client")
    Rel(extract, gemini, "LLM calls", "Google AI SDK")
    Rel(ground, medgemma, "Entity extraction", "Vertex AI SDK")
    Rel(ground, umls_mcp, "Tool calls", "MCP protocol")
    Rel(umls_mcp, umls_api, "Validates concepts", "REST/JSON")
```

## Service Communication Patterns

The system uses three distinct communication patterns for different interaction types.

### Frontend <-> Backend: REST over HTTPS

The HITL Review UI communicates with the API Service via synchronous REST calls using JSON payloads.

**Key characteristics:**

- Synchronous request/response via JSON payloads
- All endpoints documented in OpenAPI spec (accessible via `/docs`)
- Authentication via Google OAuth session cookies + JWT
- Pagination for large result sets (protocol lists, criteria batches)
- Error responses follow standard HTTP status codes

This pattern is appropriate for user-facing operations where immediate feedback is expected.

### Backend <-> Agents: Transactional Outbox Pattern

The API Service triggers agent workflows (Extraction Service, Grounding Service) asynchronously via the **transactional outbox pattern** to ensure reliable event delivery without the dual-write problem.

**Pattern flow:**

1. API Service commits database transaction (e.g., create Protocol record)
2. Within the same transaction, insert OutboxEvent record with event type (e.g., `ProtocolUploaded`)
3. OutboxProcessor polls pending events (every 5s)
4. Processor invokes agent trigger handler (e.g., `handle_protocol_uploaded` in extraction-service)
5. On success, mark OutboxEvent as `published`; on failure, increment `retry_count` with exponential backoff

**Benefits:**

- **No dual-write problem:** Database write and event publish are atomic within a single transaction
- **Guaranteed delivery:** Events are persisted durably and retried until successful
- **Idempotency:** Each event has an `idempotency_key` to prevent duplicate processing

**Event types:**

| Event Type | Trigger | Target Service | Outcome |
|------------|---------|----------------|---------|
| `ProtocolUploaded` | Protocol created | extraction-service | Extracts criteria from PDF |
| `CriteriaExtracted` | CriteriaBatch created | grounding-service | Grounds entities to UMLS/SNOMED |
| `EntitiesGrounded` | Entity linking complete | API Service | Updates protocol status to `pending_review` |
| `ReviewCompleted` | Review approved | Future analytics | Triggers downstream analytics (future phase) |

**Note:** This shows the happy path. See Production Hardening documentation for error handling, dead letter queues, and circuit breaker patterns.

### Agents <-> External Services: SDK Calls

Agents communicate with external services via their respective SDKs:

- **Gemini API:** `google.generativeai` SDK for LLM-based criteria extraction from protocol PDFs
- **MedGemma (Vertex AI):** `vertexai` SDK for medical entity extraction from criteria text
- **UMLS MCP Server:** `mcp` client protocol for concept search and linking tool calls
- **UMLS REST API:** `httpx` for UMLS concept validation (called through MCP server)

**Reliability characteristics:**

- All external calls include 30-second timeout configuration
- Exponential backoff retry logic (via `tenacity` library, max 3 retries)
- Circuit breaker patterns to prevent cascading failures during extended outages

**Note:** This shows happy path behavior. See Production Hardening for timeout handling, fallback strategies, and degraded mode operations.
