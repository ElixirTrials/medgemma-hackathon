"""Ground to UMLS node: link extracted entities to UMLS concepts.

Uses the UMLS MCP server via langchain-mcp-adapters for concept linking.
Individual entities that fail grounding are flagged for expert review,
but MCP server connection failures propagate as errors.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_b_service.state import GroundingState

logger = logging.getLogger(__name__)


async def _ground_via_mcp(
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Ground entities using the UMLS MCP server via langchain-mcp-adapters.

    Args:
        entities: List of raw entity dicts from extract_entities node.

    Returns:
        List of grounded entity dicts with UMLS fields added.

    Raises:
        Exception: If MCP server connection or tool invocation fails.
    """
    from langchain_mcp_adapters.client import MultiServerMCPClient
    from langchain_mcp_adapters.sessions import StdioConnection

    mcp_config: dict[str, StdioConnection] = {
        "umls": StdioConnection(
            command="uv",
            args=["run", "python", "-m", "umls_mcp_server.server"],
            transport="stdio",
        )
    }

    grounded: list[dict[str, Any]] = []

    async with MultiServerMCPClient(mcp_config) as mcp_client:  # type: ignore[arg-type, misc]
        tools = await mcp_client.get_tools()
        concept_linking_tool = None
        for tool in tools:
            if tool.name == "concept_linking":
                concept_linking_tool = tool
                break

        if concept_linking_tool is None:
            raise RuntimeError("concept_linking tool not found on MCP server")

        for entity in entities:
            try:
                result = await concept_linking_tool.ainvoke(
                    {
                        "term": entity["text"],
                        "context": entity.get("context_window", ""),
                    }
                )
                # Parse MCP tool result
                if isinstance(result, dict):
                    grounded_entity = {
                        **entity,
                        "umls_cui": result.get("cui"),
                        "preferred_term": result.get("name"),
                        "grounding_confidence": result.get(
                            "confidence", 0.0
                        ),
                        "grounding_method": result.get(
                            "method", "expert_review"
                        ),
                    }
                else:
                    grounded_entity = {
                        **entity,
                        "umls_cui": None,
                        "preferred_term": None,
                        "grounding_confidence": 0.0,
                        "grounding_method": "expert_review",
                    }
                grounded.append(grounded_entity)
            except Exception:
                logger.warning(
                    "MCP grounding failed for entity '%s', "
                    "flagging for expert review",
                    entity["text"],
                )
                grounded.append(
                    {
                        **entity,
                        "umls_cui": None,
                        "preferred_term": None,
                        "grounding_confidence": 0.0,
                        "grounding_method": "expert_review",
                    }
                )

    return grounded


async def ground_to_umls_node(state: GroundingState) -> dict[str, Any]:
    """Ground extracted entities to UMLS concepts via MCP server.

    Uses the MCP server for concept linking. Individual entities that
    fail are flagged for expert review, but MCP connection failures
    propagate as errors.

    Args:
        state: Current grounding state with raw_entities.

    Returns:
        Dict with grounded_entities list.
    """
    if state.get("error"):
        return {}

    raw_entities = state.get("raw_entities", [])
    if not raw_entities:
        return {"grounded_entities": []}

    grounded = await _ground_via_mcp(raw_entities)
    logger.info(
        "Grounded %d entities via MCP server for batch %s",
        len(grounded),
        state.get("batch_id"),
    )
    return {"grounded_entities": grounded}
