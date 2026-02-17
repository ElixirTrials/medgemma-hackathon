---
phase: 32-entity-model-ground-node-multi-code-display
plan: "02"
subsystem: protocol-processor-service, api-service
tags:
  - langgraph
  - checkpointing
  - retry
  - fault-tolerance
  - postgresql

dependency_graph:
  requires:
    - "31-03: 5-node pipeline (graph.py, trigger.py, all nodes)"
  provides:
    - "PostgresSaver checkpointer singleton in graph.py"
    - "retry_from_checkpoint function in trigger.py"
    - "async retry endpoint resuming from checkpoint in protocols.py"
  affects:
    - "services/protocol-processor-service (checkpointing)"
    - "services/api-service (retry endpoint behavior)"

tech_stack:
  added:
    - "langgraph-checkpoint-postgres>=2.0 — PostgreSQL checkpointer"
    - "psycopg[binary]>=3.1 — PostgreSQL adapter for checkpointer"
  patterns:
    - "Singleton checkpointer — created once at module level, reused across all invocations"
    - "thread_id=protocol_id — deterministic checkpoint lookup on retry"
    - "graph.ainvoke(None, config) — LangGraph resume from checkpoint pattern"
    - "async def FastAPI endpoint — required for await inside handler"

key_files:
  modified:
    - path: "services/protocol-processor-service/pyproject.toml"
      change: "Added langgraph-checkpoint-postgres>=2.0 and psycopg[binary]>=3.1"
    - path: "services/protocol-processor-service/src/protocol_processor/graph.py"
      change: "create_graph() accepts checkpointer arg; _get_checkpointer() singleton; get_graph() uses PostgresSaver"
    - path: "services/protocol-processor-service/src/protocol_processor/trigger.py"
      change: "handle_protocol_uploaded passes thread_id config; added retry_from_checkpoint async function"
    - path: "services/api-service/src/api_service/protocols.py"
      change: "retry_protocol is async def, uses await retry_from_checkpoint, no outbox event on retry"

decisions:
  - "PostgresSaver singleton (not per-invocation) — per Pitfall 1 from research to avoid connection pool exhaustion"
  - "Fallback to no checkpointer if DATABASE_URL not set — allows unit tests to work without a database"
  - "retry_from_checkpoint raises exceptions for caller to handle — API endpoint catches and stores error_reason"
  - "Status transition: failed -> processing -> (checkpoint resume) -> completed/failed (protocol status updated before and after resume)"

metrics:
  duration: "4 min"
  completed_date: "2026-02-17"
  tasks_completed: 2
  files_modified: 4
---

# Phase 32 Plan 02: LangGraph PostgreSQL Checkpointing Summary

**One-liner:** PostgresSaver checkpointer singleton with thread_id=protocol_id enables retry-from-checkpoint via async FastAPI endpoint that passes None to graph.ainvoke.

## What Was Built

### Task 1: PostgreSQL checkpointer in graph.py and trigger.py

**graph.py changes:**
- `create_graph(checkpointer=None)` — accepts optional checkpointer, compiled into graph
- `_get_checkpointer()` — singleton that creates `PostgresSaver.from_conn_string(DATABASE_URL)` and calls `setup()` on first use
- `get_graph()` — uses `_get_checkpointer()` if `DATABASE_URL` is set, falls back to `None` for unit tests

**trigger.py changes:**
- `handle_protocol_uploaded` passes `config = {"configurable": {"thread_id": protocol_id}}` to `graph.ainvoke` — both MLflow and non-MLflow code paths updated
- Added `async def retry_from_checkpoint(protocol_id)` — calls `graph.ainvoke(None, config)` to resume from checkpoint

**pyproject.toml:** Added `langgraph-checkpoint-postgres>=2.0` and `psycopg[binary]>=3.1`

### Task 2: Retry endpoint checkpoint resume in protocols.py

**Before (removed):**
- `def retry_protocol` (sync) created a new outbox event, reset status to "uploaded", pipeline restarted from scratch

**After (implemented):**
- `async def retry_protocol` awaits `retry_from_checkpoint(protocol_id)` — no outbox event
- Status transitions: `failed -> processing`, then after checkpoint resume: pipeline updates status itself
- Error capture: exception stored in `protocol.error_reason[:500]` and committed

## Key Design Decisions

**Singleton checkpointer:** Per Pitfall 1 from research — `PostgresSaver.from_conn_string()` creates a connection pool. Creating it per-invocation would exhaust the pool. Created once at module level and reused.

**DATABASE_URL fallback:** `get_graph()` catches `KeyError` and any exception from `_get_checkpointer()`. If `DATABASE_URL` is not set (unit tests), falls back to compiling without a checkpointer. This maintains testability without mocking the database.

**async def retry endpoint:** FastAPI runs within an active asyncio event loop. Using `asyncio.run()` inside an async handler raises `RuntimeError: This event loop is already running`. The endpoint must be `async def` and use `await` directly.

**No outbox event on retry:** Initial runs use the outbox trigger pattern (handle_protocol_uploaded via OutboxProcessor). Retry bypasses the outbox entirely — goes directly to the graph. This avoids duplicate processing and preserves checkpoint state.

**thread_id = protocol_id:** Deterministic mapping from protocol ID to LangGraph thread ID. On retry, the API endpoint needs only the protocol_id to find the checkpoint — no separate thread_id tracking needed.

## Verification Results

- `ruff check services/protocol-processor-service/src/ services/api-service/src/api_service/protocols.py` — All checks passed
- `from protocol_processor.graph import create_graph` — import ok
- `from protocol_processor.trigger import retry_from_checkpoint` — import ok
- `from api_service.protocols import router` — import ok
- `grep asyncio.run services/api-service/src/api_service/protocols.py` — only appears in comment, not code
- `grep PostgresSaver graph.py` — present at lines 109, 112 (import and usage)
- `grep thread_id trigger.py` — present at line 175 (initial run) and 238 (retry)

## Deviations from Plan

None — plan executed exactly as written.

The `pdf_bytes: bytes | None` field noted as a potential serialization concern in the plan is handled implicitly: `parse_node` clears `pdf_bytes = None` before `ground_node` runs (per PIPE-03 decision from Phase 31 Plan 03). The checkpoint is saved after parse (when pdf_bytes is already None), so bytes serialization is not an issue in practice.

## Self-Check

Files created/modified:
- [x] `.planning/phases/32-entity-model-ground-node-multi-code-display/32-02-SUMMARY.md` — this file
- [x] `services/protocol-processor-service/src/protocol_processor/graph.py` — modified
- [x] `services/protocol-processor-service/src/protocol_processor/trigger.py` — modified
- [x] `services/protocol-processor-service/pyproject.toml` — modified
- [x] `services/api-service/src/api_service/protocols.py` — modified

Commits:
- [x] `928133d` — feat(32-02): add PostgreSQL checkpointer to graph and trigger
- [x] `fe75a2e` — feat(32-02): update retry endpoint to resume from LangGraph checkpoint

## Self-Check: PASSED
