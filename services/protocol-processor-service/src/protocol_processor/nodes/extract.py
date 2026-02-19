"""Extract node: call Gemini with structured output for criteria extraction.

Thin orchestration node — delegates all LLM logic to the gemini_extractor tool.
Returns extraction_json as a JSON string to minimize LangGraph state size.
"""

from __future__ import annotations

import logging
from typing import Any

from protocol_processor.state import PipelineState
from protocol_processor.tools.gemini_extractor import extract_criteria_structured
from protocol_processor.tracing import pipeline_span

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

    protocol_id = state.get("protocol_id", "")
    with pipeline_span(
        "extract_node", span_type="LLM", protocol_id=protocol_id
    ) as span:
        span.set_inputs(
            {
                "protocol_id": state.get("protocol_id", ""),
                "title": state.get("title", ""),
                "pdf_bytes_len": len(state.get("pdf_bytes") or b""),
            }
        )

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
            span.set_outputs(
                {
                    "extraction_json_len": len(extraction_json)
                    if extraction_json
                    else 0,
                }
            )
            return {"extraction_json": extraction_json}

        except Exception as e:
            logger.exception(
                "Extraction failed for protocol %s: %s",
                state.get("protocol_id", "unknown"),
                e,
            )
            span.set_outputs({"error": str(e)})
            return {"error": f"Extraction failed: {e}"}
