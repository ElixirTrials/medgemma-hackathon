"""Map to SNOMED node: look up SNOMED-CT codes for grounded entities.

For each entity with a UMLS CUI, queries the UMLS REST API
for the corresponding SNOMED-CT code. Missing SNOMED mappings are not
errors -- entities proceed with snomed_code=None.

This node does NOT use conditional error routing -- it always proceeds
to validate_confidence (same pattern as parse -> queue in agent-a).
"""

from __future__ import annotations

import logging
from typing import Any

from agent_b_service.state import GroundingState
from agent_b_service.umls_client import get_snomed_code_for_cui

logger = logging.getLogger(__name__)


async def map_to_snomed_node(state: GroundingState) -> dict[str, Any]:
    """Add SNOMED-CT codes to grounded entities.

    For each entity with a umls_cui, looks up the SNOMED-CT code.
    If no SNOMED mapping is found, leaves snomed_code as None
    (this is not an error condition).

    Args:
        state: Current grounding state with grounded_entities.

    Returns:
        Dict with updated grounded_entities including snomed_code.
    """
    if state.get("error"):
        return {}

    grounded_entities = state.get("grounded_entities", [])
    if not grounded_entities:
        return {"grounded_entities": []}

    updated: list[dict[str, Any]] = []
    snomed_count = 0

    for entity in grounded_entities:
        cui = entity.get("umls_cui")
        if cui:
            snomed_code = await get_snomed_code_for_cui(cui)
            entity["snomed_code"] = snomed_code
            if snomed_code:
                snomed_count += 1
        else:
            entity["snomed_code"] = None
        updated.append(entity)

    logger.info(
        "Mapped %d/%d entities to SNOMED-CT for batch %s",
        snomed_count,
        len(updated),
        state.get("batch_id"),
    )
    return {"grounded_entities": updated}
