"""Unified outbox event handler for ProtocolUploaded events.

Replaces the two-service trigger pattern (extraction_service + grounding_service)
with a single consolidated handler that invokes the full 5-node pipeline:
ingest -> extract -> parse -> ground -> persist

Per user decision (v2.0): "Remove criteria_extracted outbox, retain protocol_uploaded"

The handler is synchronous (called by OutboxProcessor.poll_and_process) and
bridges to the async graph via asyncio.run(). This works without event loop
conflicts because the outbox processor runs handlers in a thread executor
via run_in_executor, so there is no existing event loop in the current thread.

Checkpointing: Each invocation generates a unique thread_id (protocol_id:uuid4)
and stores it in protocol.metadata_ so that retry_from_checkpoint can look it up.
This prevents checkpoint collision when re-extracting the same protocol.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any
from uuid import uuid4

from api_service.storage import engine
from shared.models import Protocol
from sqlmodel import Session

logger = logging.getLogger(__name__)


def _cleanup_orphan_traces() -> None:
    """Close stale IN_PROGRESS MLflow traces from previous crashed runs.

    Runs once at module import (service startup). Idempotent -- safe to
    call multiple times. Only closes traces older than 1 hour to avoid
    closing currently-running pipelines.
    """
    import time as _time

    tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
    if not tracking_uri:
        return
    try:
        import mlflow

        client = mlflow.MlflowClient()
        cutoff_ms = int((_time.time() - 3600) * 1000)  # 1 hour ago

        # MLflow 3.x: search for traces with IN_PROGRESS status
        try:
            traces = client.search_traces(
                experiment_ids=["0"],  # Default experiment
                filter_string="status = 'IN_PROGRESS'",
                max_results=50,
            )
        except (AttributeError, TypeError):
            # search_traces may not exist or have different signature
            logger.debug("MLflow search_traces API not available for orphan cleanup")
            return

        closed = 0
        for trace in traces:
            trace_ts = getattr(trace.info, "timestamp_ms", None) or 0
            if trace_ts < cutoff_ms:
                try:
                    client.end_trace(
                        request_id=trace.info.request_id,
                        status="ERROR",
                    )
                    closed += 1
                except Exception:
                    pass  # Trace may have already been closed
        if closed:
            logger.info(
                "Startup orphan cleanup: closed %d stale IN_PROGRESS trace(s)",
                closed,
            )
    except Exception:
        logger.debug("Orphan trace cleanup skipped (non-fatal)", exc_info=True)


# Run once at startup to clean up orphaned traces from previous crashes
_cleanup_orphan_traces()


def _ensure_mlflow() -> bool:
    """Ensure MLflow tracking is configured in the current thread.

    Returns True if MLflow tracing is available and configured.
    """
    try:
        import mlflow

        tracking_uri = os.getenv("MLFLOW_TRACKING_URI")
        if tracking_uri:
            mlflow.set_tracking_uri(tracking_uri)
            mlflow.set_experiment("protocol-processing")
            return True
    except ImportError:
        pass
    return False


def _categorize_pipeline_error(e: Exception) -> str:
    """Convert exception to human-readable pipeline error reason.

    Combines extraction and grounding error categorization from both
    the old extraction_service and grounding_service triggers.

    Args:
        e: The exception that occurred during pipeline execution.

    Returns:
        Human-readable error message for the user.
    """
    error_str = str(e).lower()

    # PDF / extraction errors
    if "pdf" in error_str or "pymupdf" in error_str:
        return "PDF text quality too low or file corrupted"
    if "gcs" in error_str or "storage" in error_str or "bucket" in error_str:
        return "File storage service unavailable"

    # Auth / credential errors
    if "credential" in error_str or "auth" in error_str:
        return "Service authentication failed"

    # UMLS / grounding errors
    if "mcp" in error_str or "subprocess" in error_str:
        return "UMLS grounding service unavailable"
    if "concept_linking" in error_str or "concept_search" in error_str:
        return "UMLS terminology service unavailable"

    # Generic transient errors
    if "circuit" in error_str:
        return "AI service temporarily unavailable"
    if "timeout" in error_str or "timed out" in error_str:
        return "Processing timed out"
    if "parse" in error_str:
        return "Protocol parsing failed"

    return f"Pipeline failed: {type(e).__name__}"


def _update_protocol_failed(
    protocol_id: str,
    reason: str,
    error_category: str,
    exception_type: str,
) -> None:
    """Update protocol status to extraction_failed with error metadata.

    Args:
        protocol_id: Protocol ID to update.
        reason: Human-readable error reason.
        error_category: Short category string for the error type.
        exception_type: Python exception class name.
    """
    try:
        with Session(engine) as session:
            protocol = session.get(Protocol, protocol_id)
            if protocol:
                protocol.status = "extraction_failed"
                protocol.error_reason = reason
                protocol.metadata_ = {
                    **protocol.metadata_,
                    "error": {
                        "category": error_category,
                        "reason": reason,
                        "exception_type": exception_type,
                    },
                }
                session.add(protocol)
                session.commit()
    except Exception:
        logger.exception(
            "Failed to update protocol %s status to extraction_failed",
            protocol_id,
        )


# KNOWN LIMITATION: MLflow ContextVar async boundary (Issue #8)
#
# MLflow's trace context uses Python ContextVars which do NOT propagate
# across asyncio task boundaries created by asyncio.create_task() or
# asyncio.gather(). This means:
#   - The parent trace in trigger.py correctly wraps the full pipeline run
#   - Child spans created inside LangGraph nodes are attached to the parent
#     trace because LangGraph uses `await` (not create_task) for node calls
#   - However, if future code uses asyncio.gather() for parallel node
#     execution, child spans may detach from the parent trace
#   - Workaround: Pass trace context explicitly via PipelineState if parallel
#     node execution is added
#
# This is a known MLflow limitation, not a bug in our code.


async def _run_pipeline(
    initial_state: dict[str, Any],
    config: dict[str, Any],
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Run the pipeline graph with MLflow tracing inside the async context.

    MLflow ContextVars must be created in the same async context as the
    LangGraph invocation. asyncio.run() creates an isolated context, so
    we initialize MLflow tracing HERE (inside asyncio.run) rather than
    in the sync caller.
    """
    from protocol_processor.graph import get_graph

    graph = await get_graph()

    if _ensure_mlflow():
        import mlflow

        mlflow.langchain.autolog(run_tracer_inline=True)

        with mlflow.start_span(
            name="protocol_pipeline",
            span_type="CHAIN",
        ) as span:
            # Capture trace_id immediately so finally block can force-close
            # orphaned traces on process-kill or unexpected exception.
            trace_id = mlflow.get_active_trace_id()
            span.set_inputs(
                {
                    "protocol_id": payload.get("protocol_id", ""),
                    "title": payload.get("title", ""),
                    "file_uri": payload.get("file_uri", ""),
                }
            )
            succeeded = False
            try:
                result = await graph.ainvoke(initial_state, config)
                span.set_outputs(
                    {
                        "status": result.get("status"),
                        "error": result.get("error"),
                        "error_count": len(result.get("errors", [])),
                    }
                )
                succeeded = True
                return result
            finally:
                # Only force-close as ERROR on failure — let the context
                # manager's __exit__ handle successful traces naturally.
                if trace_id and not succeeded:
                    logger.warning(
                        "Force-closing MLflow trace %s as ERROR (pipeline failed)",
                        trace_id,
                    )
                    try:
                        mlflow.MlflowClient().end_trace(trace_id, status="ERROR")
                    except Exception:
                        logger.warning(
                            "Could not force-close MLflow trace %s"
                            " — already closed or unavailable",
                            trace_id,
                        )

    return await graph.ainvoke(initial_state, config)


def handle_protocol_uploaded(payload: dict[str, Any]) -> None:
    """Handle a ProtocolUploaded event by running the full pipeline.

    Constructs the initial PipelineState from the event payload and
    invokes the consolidated 5-node LangGraph workflow via asyncio.run().

    Uses protocol_id as the LangGraph thread_id so that retry_from_checkpoint
    can locate the saved checkpoint by protocol_id alone.

    Replaces both extraction_service.trigger.handle_protocol_uploaded and
    grounding_service.trigger.handle_criteria_extracted from the v1.x
    two-service architecture.

    Args:
        payload: Event payload dict containing protocol_id, file_uri, and title.

    Raises:
        Exception: Re-raised after logging to let the outbox processor
            mark the event as failed for retry.
    """
    protocol_id = payload.get("protocol_id", "unknown")
    logger.info(
        "Handling ProtocolUploaded event for protocol %s (consolidated pipeline)",
        protocol_id,
    )

    try:
        # Generate unique thread_id per pipeline run to prevent checkpoint collision
        # on re-extraction (same protocol_id would resume old completed checkpoint)
        thread_id = f"{protocol_id}:{uuid4()}"

        initial_state: dict[str, Any] = {
            "protocol_id": payload["protocol_id"],
            "file_uri": payload["file_uri"],
            "title": payload["title"],
            "batch_id": None,
            "pdf_bytes": None,
            "extraction_json": None,
            "entities_json": None,
            "grounded_entities_json": None,
            "archived_reviewed_criteria": payload.get("archived_reviewed_criteria"),
            "status": "processing",
            "error": None,
            "errors": [],
        }

        # Store thread_id in protocol metadata for retry_from_checkpoint lookup
        try:
            with Session(engine) as session:
                protocol = session.get(Protocol, protocol_id)
                if protocol:
                    meta = protocol.metadata_ or {}
                    protocol.metadata_ = {
                        **meta,
                        "pipeline_thread_id": thread_id,
                    }
                    session.add(protocol)
                    session.commit()
        except Exception:
            logger.warning(
                "Failed to store pipeline_thread_id for protocol %s",
                protocol_id,
            )

        config = {"configurable": {"thread_id": thread_id}}

        asyncio.run(_run_pipeline(initial_state, config, payload))

        logger.info(
            "Protocol pipeline completed for protocol %s",
            protocol_id,
        )

    except Exception as e:
        logger.exception(
            "Protocol pipeline failed for protocol %s",
            protocol_id,
        )
        reason = _categorize_pipeline_error(e)
        _update_protocol_failed(
            protocol_id,
            reason,
            "pipeline_failed",
            type(e).__name__,
        )
        raise


async def retry_from_checkpoint(protocol_id: str) -> dict[str, Any]:
    """Resume pipeline from last checkpoint for a failed protocol.

    Passes None as the input state to graph.ainvoke, which tells LangGraph
    to resume from the last saved checkpoint for the given thread_id instead
    of starting from scratch. Reads thread_id from protocol.metadata_ where
    it was stored during the original pipeline invocation.

    Args:
        protocol_id: Protocol ID — used to look up thread_id from metadata.

    Returns:
        Final pipeline state dict after resuming from checkpoint.
    """
    with Session(engine) as session:
        protocol = session.get(Protocol, protocol_id)
        if not protocol:
            raise ValueError(f"Protocol {protocol_id} not found")
        thread_id = (protocol.metadata_ or {}).get("pipeline_thread_id", protocol_id)

    from protocol_processor.graph import get_graph

    graph = await get_graph()
    config = {"configurable": {"thread_id": thread_id}}
    # Pass None as input — LangGraph resumes from last checkpoint
    result = await graph.ainvoke(None, config)
    return result
