"""Ground to UMLS node: link extracted entities to UMLS concepts.

Uses the UMLS MCP server via langchain-mcp-adapters for concept linking.
Individual entities that fail grounding are flagged for expert review,
but MCP server connection failures propagate as errors.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from shared.resilience import umls_breaker
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from grounding_service.state import GroundingState

logger = logging.getLogger(__name__)

# Fields expected in a concept_linking tool result
_REQUIRED_RESULT_FIELDS = ("cui", "name", "method", "confidence")


def _parse_content_blocks(blocks: list[Any]) -> dict[str, Any]:
    """Extract JSON dict from a list of MCP content blocks.

    langchain-mcp-adapters 0.2.x returns content as a list of
    ``{"type": "text", "text": "<json>"}`` blocks.

    Args:
        blocks: List of content block dicts.

    Returns:
        Parsed dict from the first text block, or empty dict.
    """
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            text_val = block.get("text", "")
            if isinstance(text_val, str):
                return json.loads(text_val)  # type: ignore[no-any-return]
    return {}


def _normalize_tool_result(raw_result: object) -> dict[str, Any]:
    """Normalize MCP tool result to a dict regardless of wrapper type.

    langchain-mcp-adapters 0.2.x may return:
    - A list of content blocks (most common in 0.2.x)
    - A JSON string
    - A ToolMessage with a .content attribute containing a JSON string or list
    - A dict (direct passthrough in some adapter versions)

    Args:
        raw_result: The raw return value from concept_linking_tool.ainvoke().

    Returns:
        Parsed dict with concept_linking result fields.
    """
    if isinstance(raw_result, dict):
        return raw_result

    if isinstance(raw_result, str):
        return json.loads(raw_result)  # type: ignore[no-any-return]

    # langchain-mcp-adapters 0.2.x returns a list of content blocks directly
    if isinstance(raw_result, list):
        return _parse_content_blocks(raw_result)

    # ToolMessage wrapper from langchain-mcp-adapters
    if hasattr(raw_result, "content"):
        content = raw_result.content  # type: ignore[union-attr]
        if isinstance(content, str):
            return json.loads(content)  # type: ignore[no-any-return]
        if isinstance(content, dict):
            return content
        if isinstance(content, list):
            return _parse_content_blocks(content)

    logger.warning(
        "Unexpected tool result type: %s (value: %r)",
        type(raw_result).__name__,
        raw_result,
    )
    return {}


@umls_breaker
@retry(
    retry=retry_if_exception_type((RuntimeError, ConnectionError, OSError)),
    stop=stop_after_attempt(3),
    wait=wait_random_exponential(multiplier=1, min=4, max=10),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def _ground_via_mcp(
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Ground entities using the UMLS MCP server via langchain-mcp-adapters.

    Args:
        entities: List of raw entity dicts from extract_entities node.

    Returns:
        List of grounded entity dicts with UMLS fields added.

    Raises:
        RuntimeError: If MCP server connection or tool discovery fails.
        ConnectionError: If MCP server subprocess fails to start.
        OSError: If subprocess I/O fails.
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

    # MCP client setup — errors here propagate (not per-entity)
    mcp_client = MultiServerMCPClient(mcp_config)  # type: ignore[arg-type]
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
            raw_result = await concept_linking_tool.ainvoke(
                {
                    "term": entity["text"],
                    "context": entity.get("context_window", ""),
                }
            )

            # Normalize tool result to dict (handles str, ToolMessage, dict)
            parsed = _normalize_tool_result(raw_result)

            # Validate expected fields are present
            missing = [f for f in _REQUIRED_RESULT_FIELDS if f not in parsed]
            if missing:
                logger.warning(
                    "Tool result missing fields %s for entity '%s': %r",
                    missing,
                    entity["text"],
                    parsed,
                )

            grounded_entity = {
                **entity,
                "umls_cui": parsed.get("cui"),
                "preferred_term": parsed.get("name"),
                "grounding_confidence": parsed.get("confidence", 0.0),
                "grounding_method": parsed.get("method", "expert_review"),
            }
            grounded.append(grounded_entity)

        except json.JSONDecodeError as e:
            # JSON parse failure is a data issue — log and continue
            logger.warning(
                "JSON parse error for entity '%s': %s: %s",
                entity["text"],
                type(e).__name__,
                str(e),
                exc_info=True,
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
        except Exception as e:
            logger.warning(
                "MCP grounding failed for entity '%s': %s: %s",
                entity["text"],
                type(e).__name__,
                str(e),
                exc_info=True,
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
