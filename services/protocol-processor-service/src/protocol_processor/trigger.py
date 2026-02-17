"""Unified outbox event handler for ProtocolUploaded events.

Replaces the two-service trigger pattern (extraction_service + grounding_service)
with a single consolidated handler that invokes the full 5-node pipeline:
ingest -> extract -> parse -> ground -> persist

Per user decision (v2.0): "Remove criteria_extracted outbox, retain protocol_uploaded"

The handler is synchronous (called by OutboxProcessor.poll_and_process) and
bridges to the async graph via asyncio.run(). This works without event loop
conflicts because the outbox processor runs handlers in a thread executor
via run_in_executor, so there is no existing event loop in the current thread.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from api_service.storage import engine
from shared.models import Protocol
from sqlmodel import Session

logger = logging.getLogger(__name__)


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
    """Update protocol status to pipeline_failed with error metadata.

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


def handle_protocol_uploaded(payload: dict[str, Any]) -> None:
    """Handle a ProtocolUploaded event by running the full pipeline.

    Constructs the initial PipelineState from the event payload and
    invokes the consolidated 5-node LangGraph workflow via asyncio.run().

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
        initial_state: dict[str, Any] = {
            "protocol_id": payload["protocol_id"],
            "file_uri": payload["file_uri"],
            "title": payload["title"],
            "batch_id": None,
            "pdf_bytes": None,
            "extraction_json": None,
            "entities_json": None,
            "grounded_entities_json": None,
            "status": "processing",
            "error": None,
            "errors": [],
        }

        # Lazy import to avoid circular imports at module load time
        from protocol_processor.graph import get_graph

        graph = get_graph()

        if _ensure_mlflow():
            import mlflow

            with mlflow.start_span(
                name="protocol_pipeline",
                span_type="CHAIN",
            ) as span:
                span.set_inputs(
                    {
                        "protocol_id": protocol_id,
                        "title": payload.get("title", ""),
                        "file_uri": payload.get("file_uri", ""),
                    }
                )
                result = asyncio.run(graph.ainvoke(initial_state))
                span.set_outputs(
                    {
                        "status": result.get("status"),
                        "error": result.get("error"),
                        "error_count": len(result.get("errors", [])),
                    }
                )
        else:
            asyncio.run(graph.ainvoke(initial_state))

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
