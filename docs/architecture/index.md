# Architecture

This section documents the system architecture of the Clinical Trial Criteria Extraction System.

## Documentation

- **[System Architecture](system-architecture.md)** -- C4 Container diagram showing system structure, technology stack, and service communication patterns (REST, transactional outbox, SDK calls)
- **[Data Models](data-models.md)** -- Database schema (ER diagram) and LangGraph agent state documentation *(coming in Phase 9 Plan 02)*

## Key Architectural Decisions

| Decision | Rationale |
|----------|-----------|
| Microservices (api, extraction, grounding) | Natural mapping to pipeline stages; independent scaling |
| LangGraph for agent workflows | TypedDict state management, conditional routing, node-based processing |
| Transactional outbox for events | Atomic DB + event writes, guaranteed delivery, no dual-write problem |
| FastMCP for UMLS integration | Tool-based interface for concept search/linking, protocol-standard |
| PostgreSQL with SQLModel ORM | Pydantic integration, type-safe queries, Alembic migrations |
| React + Vite for HITL UI | Fast dev builds, TanStack Query for server state, Zustand for client state |
