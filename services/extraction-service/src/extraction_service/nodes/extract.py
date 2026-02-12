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
from shared.resilience import gemini_breaker
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from extraction_service.schemas.criteria import ExtractionResult
from extraction_service.state import ExtractionState

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


@gemini_breaker
@retry(
    retry=retry_if_exception_type(Exception),
    stop=stop_after_attempt(3),
    wait=wait_random_exponential(multiplier=1, min=2, max=10),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def _invoke_gemini(
    structured_llm: Any, system_prompt: str, user_prompt: str
) -> ExtractionResult:
    """Invoke Gemini with retry and circuit breaker.

    Args:
        structured_llm: LLM instance with structured output.
        system_prompt: System message content.
        user_prompt: User message content.

    Returns:
        ExtractionResult from Gemini.
    """
    result = await structured_llm.ainvoke(
        [("system", system_prompt), ("user", user_prompt)]
    )

    # Handle both Pydantic model and dict responses
    if isinstance(result, dict):
        return ExtractionResult(**result)
    return cast(ExtractionResult, result)


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

        extraction_result = await _invoke_gemini(
            structured_llm, system_prompt, user_prompt
        )

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
