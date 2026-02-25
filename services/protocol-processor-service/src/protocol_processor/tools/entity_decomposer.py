"""Entity decomposition: extract discrete medical entities from criteria.

Criterion sentences like "eGFR >= 30 mL/min/1.73m2 or sCr <= 2.0 mg/dL" contain
multiple groundable medical concepts. This tool decomposes them into discrete
entities with correct types for TerminologyRouter dispatch.

Uses the two-model architecture pattern: Gemini for structured output via
LangChain's with_structured_output, matching the medgemma_decider.py pattern.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Literal, cast

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from protocol_processor.prompts import render_template

logger = logging.getLogger(__name__)

# Unicode math symbols that Gemini/PDF extraction may produce.
# Normalize to ASCII equivalents so the LLM template handles them cleanly.
_UNICODE_OPERATORS: dict[str, str] = {
    "\u2265": ">=",  # ≥
    "\u2264": "<=",  # ≤
    "\u2260": "!=",  # ≠
    "\u00b1": "+-",  # ±
    "\u2013": "-",  # en-dash
    "\u2014": "-",  # em-dash
}


def _normalize_criterion_text(text: str) -> str:
    """Replace unicode math/comparison symbols with ASCII equivalents."""
    for char, repl in _UNICODE_OPERATORS.items():
        text = text.replace(char, repl)
    return text


class DecomposedEntity(BaseModel):
    """A single medical entity extracted from a criterion sentence.

    Attributes:
        text: The specific medical term to ground (e.g. "eGFR", not the full sentence).
        entity_type: Entity type matching routing.yaml keys exactly.
    """

    text: str = Field(description="The specific medical term to ground")
    entity_type: Literal[
        "Condition", "Medication", "Lab_Value", "Procedure", "Demographic", "Other"
    ] = Field(description="Entity type for terminology routing")


class DecomposedEntityList(BaseModel):
    """List of decomposed entities from a single criterion sentence."""

    entities: list[DecomposedEntity] = Field(default_factory=list)


def _rephrase_for_retry(text: str, attempt: int) -> str:
    """Apply small wording changes for retry attempts.

    Each attempt surfaces the same medical content with slightly
    different phrasing so the LLM gets a fresh chance to extract entities.
    """
    if attempt == 1:
        return f"Eligibility criterion: {text}. Identify every medical concept."
    # attempt == 2
    return f"Clinical trial requirement — {text}. What medical entities are mentioned?"


async def _invoke_decompose(
    structured: Any,
    prompt: str,
    label: str,
    model_name: str,
) -> DecomposedEntityList:
    """Single invocation of the structured LLM with tracing."""
    from protocol_processor.tracing import llm_span

    with llm_span(label, model_name) as llm:
        llm.set_request(prompt)
        result = await structured.ainvoke(prompt)
        llm.set_response(str(result))

    if isinstance(result, dict):
        result = DecomposedEntityList.model_validate(result)
    return cast(DecomposedEntityList, result)


async def decompose_entities_from_criterion(
    criterion_text: str,
    category: str | None,
    *,
    max_retries: int = 2,
) -> list[dict[str, Any]]:
    """Extract discrete medical entities from a criterion sentence.

    Uses Gemini with structured output to decompose a criterion sentence
    into individual medical terms with correct entity types. If the first
    attempt returns zero entities, retries up to *max_retries* times with
    small wording changes before returning an empty list.

    Args:
        criterion_text: The full criterion sentence to decompose.
        category: Optional category hint from extraction.
        max_retries: Number of retry attempts with rephrased wording (default 2).

    Returns:
        List of dicts with "text" and "entity_type" keys, or empty list on failure.
    """
    # Normalize unicode operators (≥, ≤, etc.) to ASCII before LLM call
    normalized_text = _normalize_criterion_text(criterion_text)

    try:
        gemini = ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash"),
            google_api_key=os.getenv("GOOGLE_API_KEY"),
        )
        model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
        structured = gemini.with_structured_output(DecomposedEntityList)

        # Attempt 0: original prompt
        prompt = render_template(
            "entity_decompose.jinja2",
            criterion_text=normalized_text,
            category=category or "",
        )
        decomposed = await _invoke_decompose(
            structured,
            prompt,
            "gemini_entity_decompose",
            model_name,
        )

        # Retry with rephrased wording if we got 0 entities
        for attempt in range(1, max_retries + 1):
            if decomposed.entities:
                break
            rephrased = _rephrase_for_retry(normalized_text, attempt)
            retry_prompt = render_template(
                "entity_decompose.jinja2",
                criterion_text=rephrased,
                category=category or "",
            )
            logger.info(
                "Entity decomposition retry %d/%d for '%s'",
                attempt,
                max_retries,
                normalized_text[:60],
            )
            decomposed = await _invoke_decompose(
                structured,
                retry_prompt,
                f"gemini_entity_decompose_retry{attempt}",
                model_name,
            )

        if not decomposed.entities:
            logger.warning(
                "Entity decomposition returned 0 entities after %d retries for '%s'",
                max_retries,
                normalized_text[:80],
            )

        return [e.model_dump() for e in decomposed.entities]
    except Exception as e:
        logger.error(
            "Entity decomposition failed for criterion '%s': %s",
            normalized_text[:80],
            e,
            exc_info=True,
        )
        return []


async def medgemma_decompose_entities(
    criterion_text: str,
) -> list[dict[str, Any]]:
    """Fallback: ask MedGemma to identify medical entities when Gemini fails.

    Uses MedGemma (medical expert) to extract entity names, then Gemini to
    structure the output into typed entities. Called by parse_node when
    Gemini decomposition returns empty even after retries.

    Args:
        criterion_text: The criterion sentence to decompose.

    Returns:
        List of dicts with "text" and "entity_type" keys, or empty list on failure.
    """
    normalized_text = _normalize_criterion_text(criterion_text)

    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        from protocol_processor.tools.medgemma_decider import _get_medgemma_model
        from protocol_processor.tracing import llm_span

        model = _get_medgemma_model()
        model_name = getattr(model, "model_name", "") or getattr(model, "model", "")

        messages = [
            SystemMessage(content=render_template("medgemma_decompose_system.jinja2")),
            HumanMessage(
                content=render_template(
                    "medgemma_decompose_user.jinja2",
                    criterion_text=normalized_text,
                )
            ),
        ]

        with llm_span("medgemma_entity_decompose", str(model_name)) as llm:
            llm.set_request(str(messages))
            raw_response = await model.ainvoke(messages)
            raw_text = raw_response.content
            llm.set_response(str(raw_text))

        # Use Gemini to structure MedGemma's free-text into typed entities
        gemini = ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash"),
            google_api_key=os.getenv("GOOGLE_API_KEY"),
        )
        structured = gemini.with_structured_output(DecomposedEntityList)

        structure_prompt = render_template(
            "structure_entities.jinja2", raw_text=raw_text
        )
        gemini_model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")

        with llm_span("gemini_structure_medgemma_decompose", gemini_model_name) as llm:
            llm.set_request(structure_prompt)
            result = await structured.ainvoke(structure_prompt)
            llm.set_response(str(result))

        if isinstance(result, dict):
            result = DecomposedEntityList.model_validate(result)
        decomposed = cast(DecomposedEntityList, result)

        if decomposed.entities:
            logger.info(
                "MedGemma decomposition found %d entities for '%s'",
                len(decomposed.entities),
                normalized_text[:60],
            )
        else:
            logger.warning(
                "MedGemma decomposition also returned 0 entities for '%s'",
                normalized_text[:80],
            )

        return [e.model_dump() for e in decomposed.entities]

    except Exception as e:
        logger.error(
            "MedGemma entity decomposition failed for '%s': %s",
            criterion_text[:80],
            e,
            exc_info=True,
        )
        return []
