"""Extract node: call Gemini with structured output for criteria extraction.

This node invokes ChatGoogleGenerativeAI.with_structured_output(ExtractionResult)
using Jinja2-rendered system and user prompts. The output is a list of
criteria dicts ready for post-processing by the parse node.
"""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Any, cast

from inference.factory import render_prompts
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
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
    structured_llm: Any, messages: list[SystemMessage | HumanMessage]
) -> ExtractionResult:
    """Invoke Gemini with retry and circuit breaker.

    Args:
        structured_llm: LLM instance with structured output.
        messages: List of system and user messages (supports multimodal content).

    Returns:
        ExtractionResult from Gemini.
    """
    result = await structured_llm.ainvoke(messages)

    # Handle both Pydantic model and dict responses
    if isinstance(result, dict):
        return ExtractionResult(**result)
    return cast(ExtractionResult, result)


async def extract_node(state: ExtractionState) -> dict[str, Any]:
    """Extract structured criteria from PDF using Gemini multimodal input.

    Args:
        state: Current extraction state with pdf_bytes and title.

    Returns:
        Dict with raw_criteria list of dicts, or error dict on failure.
    """
    if state.get("error"):
        return {}

    try:
        # Encode PDF as base64
        pdf_base64 = base64.b64encode(state["pdf_bytes"]).decode("utf-8")
        pdf_data_uri = f"data:application/pdf;base64,{pdf_base64}"

        # Warn if approaching size limit
        encoded_size_mb = len(pdf_base64) / (1024 * 1024)
        if encoded_size_mb > 18:
            logger.warning(
                "PDF size after base64 encoding: %.2f MB (approaching 20MB limit)",
                encoded_size_mb,
            )

        model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-3-flash-preview")
        llm = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=0,
            vertexai=True,
            project=os.getenv("GCP_PROJECT_ID"),
            location=os.getenv("GCP_REGION", "us-central1"),
        )
        structured_llm = llm.with_structured_output(ExtractionResult)

        system_prompt, user_prompt = render_prompts(
            prompts_dir=PROMPTS_DIR,
            system_template="system.jinja2",
            user_template="user.jinja2",
            prompt_vars={
                "title": state["title"],
            },
        )

        # Construct multimodal messages
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(
                content=[
                    {"type": "text", "text": user_prompt},
                    {"type": "image_url", "image_url": {"url": pdf_data_uri}},
                ]
            ),
        ]

        extraction_result = await _invoke_gemini(structured_llm, messages)

        criteria_dicts = [c.model_dump() for c in extraction_result.criteria]

        logger.info(
            "Extracted %d criteria from protocol %s (PDF multimodal input)",
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
