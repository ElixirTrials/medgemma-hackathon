"""Extract node: call Gemini with structured output for criteria extraction.

Thin orchestration node — delegates all LLM logic to the gemini_extractor tool.
Returns extraction_json as a JSON string to minimize LangGraph state size.
"""

from __future__ import annotations

import logging
from typing import Any

from protocol_processor.state import PipelineState
from protocol_processor.tools.gemini_extractor import extract_criteria_structured

logger = logging.getLogger(__name__)


async def extract_node(state: PipelineState) -> dict[str, Any]:
    """Extract structured criteria from PDF using Gemini File API.

    Delegates to extract_criteria_structured tool. Returns a JSON string
    (not dict) to minimize LangGraph state overhead.

    Args:
        state: Current pipeline state with pdf_bytes, protocol_id, and title.

    Returns:
        Dict with extraction_json (JSON string), or error dict on failure.
    """
    if state.get("error"):
        return {}

    try:
        extraction_json = await extract_criteria_structured(
            pdf_bytes=state["pdf_bytes"],  # type: ignore[arg-type]
            protocol_id=state["protocol_id"],
            title=state["title"],
        )

        logger.info(
            "Extraction complete for protocol %s",
            state["protocol_id"],
        )
        return {"extraction_json": extraction_json}

    except Exception as e:
        logger.exception(
            "Extraction failed for protocol %s: %s",
            state.get("protocol_id", "unknown"),
            e,
        )
        return {"error": f"Extraction failed: {e}"}
