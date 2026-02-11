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
from typing import Any

logger = logging.getLogger(__name__)


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
            "markdown_content": "",
            "raw_criteria": [],
            "criteria_batch_id": "",
            "error": None,
        }

        # Lazy import to avoid circular imports at module load time
        from extraction_service.graph import get_graph

        graph = get_graph()
        asyncio.run(graph.ainvoke(initial_state))

        logger.info(
            "Extraction workflow completed for protocol %s",
            protocol_id,
        )

    except Exception:
        logger.exception(
            "Extraction workflow failed for protocol %s",
            protocol_id,
        )
        raise
