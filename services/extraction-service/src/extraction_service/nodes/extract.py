"""Extract node: call Gemini with structured output for criteria extraction.

This node invokes ChatVertexAI.with_structured_output(ExtractionResult)
using Jinja2-rendered system and user prompts. The output is a list of
criteria dicts ready for post-processing by the parse node.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, cast

from inference.factory import render_prompts
from langchain_google_vertexai import ChatVertexAI  # type: ignore[import-untyped]

from agent_a_service.schemas.criteria import ExtractionResult
from agent_a_service.state import ExtractionState

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


async def extract_node(state: ExtractionState) -> dict[str, Any]:
    """Extract structured criteria from protocol markdown using Gemini.

    Args:
        state: Current extraction state with markdown_content and title.

    Returns:
        Dict with raw_criteria list of dicts, or error dict on failure.
    """
    if state.get("error"):
        return {}

    try:
        model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
        llm = ChatVertexAI(model_name=model_name, temperature=0)
        structured_llm = llm.with_structured_output(ExtractionResult)

        system_prompt, user_prompt = render_prompts(
            prompts_dir=PROMPTS_DIR,
            system_template="system.jinja2",
            user_template="user.jinja2",
            prompt_vars={
                "title": state["title"],
                "markdown_content": state["markdown_content"],
            },
        )

        result = await structured_llm.ainvoke(
            [("system", system_prompt), ("user", user_prompt)]
        )

        # Handle both Pydantic model and dict responses
        if isinstance(result, dict):
            extraction_result = ExtractionResult(**result)
        else:
            extraction_result = cast(ExtractionResult, result)

        criteria_dicts = [c.model_dump() for c in extraction_result.criteria]

        logger.info(
            "Extracted %d criteria from protocol %s",
            len(criteria_dicts),
            state["protocol_id"],
        )
        return {"raw_criteria": criteria_dicts}

    except Exception as e:
        logger.exception(
            "Extraction failed for protocol %s: %s",
            state.get("protocol_id", "unknown"),
            e,
        )
        return {"error": f"Extraction failed: {e}"}
