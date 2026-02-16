"""Event handler bridging ProtocolUploaded to graph invocation.

This module is registered with the OutboxProcessor to handle
ProtocolUploaded events. When a protocol is uploaded, it constructs
the initial ExtractionState and invokes the LangGraph workflow.

The handler is synchronous (called by OutboxProcessor.poll_and_process)
and bridges to the async graph via asyncio.run().
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


def _categorize_extraction_error(e: Exception) -> str:
    """Convert exception to human-readable error reason.

    Args:
        e: The exception that occurred during extraction.

    Returns:
        Human-readable error message for the user.
    """
    error_str = str(e).lower()
    if "pdf" in error_str or "parse" in error_str or "pymupdf" in error_str:
        return "PDF text quality too low or file corrupted"
    if "circuit" in error_str:
        return "AI service temporarily unavailable"
    if "timeout" in error_str or "timed out" in error_str:
        return "Processing timed out"
    if "credential" in error_str or "auth" in error_str:
        return "Service authentication failed"
    if "gcs" in error_str or "storage" in error_str or "bucket" in error_str:
        return "File storage service unavailable"
    return f"Extraction failed: {type(e).__name__}"


def handle_protocol_uploaded(payload: dict[str, Any]) -> None:
    """Handle a ProtocolUploaded event by running the extraction workflow.

    Constructs the initial ExtractionState from the event payload and
    invokes the LangGraph extraction workflow. Uses asyncio.run() to
    bridge the synchronous outbox handler to the async graph.

    This works without event loop conflicts because the outbox processor
    runs handlers in a thread executor via run_in_executor, so there is
    no existing event loop in the current thread.

    Args:
        payload: Event payload dict containing protocol_id, file_uri, and title.

    Raises:
        Exception: Re-raised after logging to let the outbox processor
            mark the event as failed for retry.
    """
    protocol_id = payload.get("protocol_id", "unknown")
    logger.info(
        "Handling ProtocolUploaded event for protocol %s",
        protocol_id,
    )

    try:
        initial_state: dict[str, Any] = {
            "protocol_id": payload["protocol_id"],
            "file_uri": payload["file_uri"],
            "title": payload["title"],
            "pdf_bytes": b"",
            "raw_criteria": [],
            "criteria_batch_id": "",
            "error": None,
        }

        # Lazy import to avoid circular imports at module load time
        from extraction_service.graph import get_graph

        graph = get_graph()

        # Create an MLflow trace wrapping the entire extraction workflow.
        # _ensure_mlflow() re-sets tracking URI in this background thread.
        if _ensure_mlflow():
            import mlflow

            with mlflow.start_span(
                name="extraction_workflow",
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
                criteria_count = len(result.get("raw_criteria", []))
                span.set_outputs(
                    {
                        "criteria_count": criteria_count,
                        "error": result.get("error"),
                    }
                )
        else:
            asyncio.run(graph.ainvoke(initial_state))

        logger.info(
            "Extraction workflow completed for protocol %s",
            protocol_id,
        )

    except Exception as e:
        logger.exception(
            "Extraction workflow failed for protocol %s",
            protocol_id,
        )
        # Update protocol status with failure category
        try:
            with Session(engine) as session:
                protocol = session.get(Protocol, protocol_id)
                if protocol:
                    protocol.status = "extraction_failed"
                    protocol.error_reason = _categorize_extraction_error(e)
                    protocol.metadata_ = {
                        **protocol.metadata_,
                        "error": {
                            "category": "extraction_failed",
                            "reason": protocol.error_reason,
                            "exception_type": type(e).__name__,
                        },
                    }
                    session.add(protocol)
                    session.commit()
        except Exception:
            logger.exception("Failed to update protocol status for %s", protocol_id)
        raise
