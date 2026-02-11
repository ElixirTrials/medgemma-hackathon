"""Ground to UMLS node: link extracted entities to UMLS concepts.

Uses the UMLS MCP server via langchain-mcp-adapters for concept linking.
Falls back to direct UMLS client API calls if the MCP server is unavailable.
Never blocks the pipeline on failed grounding -- entities that cannot be
grounded are flagged for expert review.
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

    mcp_config = {
        "umls": {
            "command": "uv",
            "args": ["run", "python", "-m", "umls_mcp_server.server"],
            "transport": "stdio",
        }
    }

    grounded: list[dict[str, Any]] = []

    async with MultiServerMCPClient(mcp_config) as mcp_client:
        tools = mcp_client.get_tools()
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


async def _ground_via_direct_client(
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Ground entities using direct UMLS client API calls.

    Fallback mode when MCP server is unavailable. Uses the same
    tiered grounding strategy (exact -> word -> expert_review).

    Args:
        entities: List of raw entity dicts from extract_entities node.

    Returns:
        List of grounded entity dicts with UMLS fields added.
    """
    from umls_mcp_server.umls_api import get_umls_client

    client = get_umls_client()
    grounded: list[dict[str, Any]] = []

    for entity in entities:
        try:
            # Tier 1: Exact match
            exact_results = await client.search(
                entity["text"],
                sabs="SNOMEDCT_US",
                search_type="exact",
                max_results=1,
            )
            if exact_results:
                grounded.append(
                    {
                        **entity,
                        "umls_cui": exact_results[0]["cui"],
                        "preferred_term": exact_results[0]["name"],
                        "grounding_confidence": 0.95,
                        "grounding_method": "exact_match",
                    }
                )
                continue

            # Tier 2: Word search
            word_results = await client.search(
                entity["text"],
                sabs="SNOMEDCT_US",
                search_type="words",
                max_results=5,
            )
            if word_results:
                grounded.append(
                    {
                        **entity,
                        "umls_cui": word_results[0]["cui"],
                        "preferred_term": word_results[0]["name"],
                        "grounding_confidence": 0.75,
                        "grounding_method": "semantic_similarity",
                    }
                )
                continue

            # Tier 3: No match -- expert review
            grounded.append(
                {
                    **entity,
                    "umls_cui": None,
                    "preferred_term": None,
                    "grounding_confidence": 0.0,
                    "grounding_method": "expert_review",
                }
            )

        except Exception:
            logger.warning(
                "Direct grounding failed for entity '%s', "
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
    """Ground extracted entities to UMLS concepts.

    Attempts MCP server grounding first, falls back to direct client.
    Never blocks the pipeline -- failed entities get expert_review method.

    Args:
        state: Current grounding state with raw_entities.

    Returns:
        Dict with grounded_entities list, or error dict on total failure.
    """
    if state.get("error"):
        return {}

    raw_entities = state.get("raw_entities", [])
    if not raw_entities:
        return {"grounded_entities": []}

    try:
        # Try MCP server first
        try:
            grounded = await _ground_via_mcp(raw_entities)
            logger.info(
                "Grounded %d entities via MCP server for batch %s",
                len(grounded),
                state.get("batch_id"),
            )
            return {"grounded_entities": grounded}
        except Exception:
            logger.info(
                "MCP server unavailable, falling back to direct "
                "client for batch %s",
                state.get("batch_id"),
            )

        # Fallback: direct UMLS client
        grounded = await _ground_via_direct_client(raw_entities)
        logger.info(
            "Grounded %d entities via direct client for batch %s",
            len(grounded),
            state.get("batch_id"),
        )
        return {"grounded_entities": grounded}

    except Exception as e:
        logger.exception(
            "UMLS grounding failed for batch %s: %s",
            state.get("batch_id", "unknown"),
            e,
        )
        return {"error": f"UMLS grounding failed: {e}"}
