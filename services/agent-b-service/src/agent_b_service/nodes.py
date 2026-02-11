"""Placeholder node functions for the grounding agent.

These will be replaced with real nodes (extract_entities, ground_to_umls,
map_to_snomed, validate_confidence) in Plan 05-03.
"""

import logging
from typing import Any

from .state import GroundingState

logger = logging.getLogger(__name__)


async def process_node(state: GroundingState) -> dict[str, Any]:
    """Placeholder process node.

    Args:
        state: Current grounding state.

    Returns:
        Empty state updates (no-op placeholder).
    """
    logger.info("Running placeholder process node for batch %s", state.get("batch_id"))
    return {}


async def finalize_node(state: GroundingState) -> dict[str, Any]:
    """Placeholder finalize node.

    Args:
        state: Current grounding state.

    Returns:
        Empty state updates (no-op placeholder).
    """
    logger.info("Running placeholder finalize node for batch %s", state.get("batch_id"))
    return {}
