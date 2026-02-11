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

logger = logging.getLogger(__name__)


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
        from agent_b_service.graph import get_graph

        graph = get_graph()
        asyncio.run(graph.ainvoke(initial_state))

        logger.info(
            "Grounding workflow completed for batch %s",
            batch_id,
        )

    except Exception:
        logger.exception(
            "Grounding workflow failed for batch %s",
            batch_id,
        )
        raise
