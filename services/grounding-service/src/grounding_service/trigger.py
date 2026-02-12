"""Event handler bridging CriteriaExtracted to graph invocation.

This module is registered with the OutboxProcessor to handle
CriteriaExtracted events. When criteria extraction completes, it
constructs the initial GroundingState and invokes the LangGraph
entity grounding workflow.

The handler is synchronous (called by OutboxProcessor.poll_and_process)
and bridges to the async graph via asyncio.run(). This works without
event loop conflicts because the outbox processor runs handlers in a
thread executor via run_in_executor, so there is no existing event
loop in the current thread.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from api_service.storage import engine
from shared.models import Protocol
from sqlmodel import Session

logger = logging.getLogger(__name__)


def _categorize_grounding_error(e: Exception) -> str:
    """Convert exception to human-readable error reason.

    Args:
        e: The exception that occurred during grounding.

    Returns:
        Human-readable error message for the user.
    """
    error_str = str(e).lower()
    if "mcp" in error_str or "subprocess" in error_str:
        return "UMLS grounding service unavailable"
    if "circuit" in error_str:
        return "UMLS service temporarily unavailable"
    if "timeout" in error_str:
        return "Grounding timed out"
    if "concept_linking" in error_str:
        return "UMLS concept linking tool unavailable"
    return f"Grounding failed: {type(e).__name__}"


def handle_criteria_extracted(payload: dict[str, Any]) -> None:
    """Handle a CriteriaExtracted event by running the grounding workflow.

    Constructs the initial GroundingState from the event payload and
    invokes the LangGraph grounding workflow. Uses asyncio.run() to
    bridge the synchronous outbox handler to the async graph.

    Args:
        payload: Event payload dict containing batch_id, protocol_id,
            and criteria_ids.

    Raises:
        Exception: Re-raised after logging to let the outbox processor
            mark the event as failed for retry.
    """
    batch_id = payload.get("batch_id", "unknown")
    logger.info(
        "Handling CriteriaExtracted event for batch %s",
        batch_id,
    )

    try:
        initial_state: dict[str, Any] = {
            "batch_id": payload["batch_id"],
            "protocol_id": payload["protocol_id"],
            "criteria_ids": payload["criteria_ids"],
            "criteria_texts": [],
            "raw_entities": [],
            "grounded_entities": [],
            "entity_ids": [],
            "error": None,
        }

        # Lazy import to avoid circular imports at module load time
        from grounding_service.graph import get_graph

        graph = get_graph()
        asyncio.run(graph.ainvoke(initial_state))

        logger.info(
            "Grounding workflow completed for batch %s",
            batch_id,
        )

    except Exception as e:
        logger.exception(
            "Grounding workflow failed for batch %s",
            batch_id,
        )
        # Update protocol status with failure category
        protocol_id = payload.get("protocol_id")
        if protocol_id:
            try:
                with Session(engine) as session:
                    protocol = session.get(Protocol, protocol_id)
                    if protocol:
                        protocol.status = "grounding_failed"
                        protocol.error_reason = _categorize_grounding_error(e)
                        protocol.metadata_ = {
                            **protocol.metadata_,
                            "error": {
                                "category": "grounding_failed",
                                "reason": protocol.error_reason,
                                "exception_type": type(e).__name__,
                            },
                        }
                        session.add(protocol)
                        session.commit()
            except Exception:
                logger.exception("Failed to update protocol status for %s", protocol_id)
        raise
