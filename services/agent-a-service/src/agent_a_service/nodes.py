"""Placeholder node functions for the criteria extraction agent.

These will be replaced by proper node implementations in
services/agent-a-service/src/agent_a_service/nodes/ package
during Plan 03-02.
"""

import logging
from typing import Any

from .state import ExtractionState

logger = logging.getLogger(__name__)


async def extraction_node(state: ExtractionState) -> dict[str, Any]:
    """Placeholder extraction node.

    Will be replaced by ingest + extract nodes in Plan 03-02.

    Args:
        state: Current extraction state.

    Returns:
        Empty state updates.
    """
    logger.info("Running placeholder extraction node")
    return {}


async def validation_node(state: ExtractionState) -> dict[str, Any]:
    """Placeholder validation node.

    Will be replaced by parse + queue nodes in Plan 03-02.

    Args:
        state: Current extraction state.

    Returns:
        Empty state updates.
    """
    logger.info("Running placeholder validation node")
    return {}
