"""Extract entities node: call Gemini/MedGemma for structured entity extraction.

This node loads criteria from the database, renders Jinja2 prompts, and
invokes ChatVertexAI.with_structured_output(BatchEntityExtractionResult) to
extract medical entities with span positions. Includes post-extraction span
validation to correct any LLM misalignments.

Architecture note: Graph nodes are integration glue and ARE allowed
to import from api-service for database access (e.g., api_service.storage.engine).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, cast

from inference.factory import render_prompts
from langchain_google_vertexai import ChatVertexAI  # type: ignore[import-untyped]

from grounding_service.schemas.entities import (
    BatchEntityExtractionResult,
    ExtractedEntity,
)
from grounding_service.state import GroundingState

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def _load_criteria_texts(criteria_ids: list[str]) -> list[dict[str, Any]]:
    """Load criteria records from the database.

    Args:
        criteria_ids: List of Criteria record IDs to load.

    Returns:
        List of criteria dicts with id, text, criteria_type, category.
    """
    from api_service.storage import engine
    from shared.models import Criteria
    from sqlmodel import Session

    criteria_texts: list[dict[str, Any]] = []
    with Session(engine) as session:
        for cid in criteria_ids:
            criterion = session.get(Criteria, cid)
            if criterion:
                criteria_texts.append(
                    {
                        "id": criterion.id,
                        "text": criterion.text,
                        "criteria_type": criterion.criteria_type,
                        "category": criterion.category,
                    }
                )
    return criteria_texts


def _get_model_name() -> str:
    """Determine the LLM model name from environment variables.

    Returns:
        Model name string for ChatVertexAI.
    """
    model_choice = os.getenv("ENTITY_EXTRACTION_MODEL", "gemini")
    if model_choice == "medgemma":
        return os.getenv("MEDGEMMA_ENDPOINT", "medgemma-1.5-4b-it")
    return "gemini-2.5-flash"


def _validate_span(entity: ExtractedEntity, criterion_text: str) -> tuple[int, int]:
    """Validate and correct entity span positions against source text.

    Args:
        entity: Extracted entity with span_start and span_end.
        criterion_text: Source criterion text to validate against.

    Returns:
        Tuple of (corrected_start, corrected_end).
    """
    span_start = entity.span_start
    span_end = entity.span_end

    if not criterion_text:
        return span_start, span_end

    extracted_span = criterion_text[span_start:span_end]
    if extracted_span == entity.text:
        return span_start, span_end

    # Attempt to find correct position
    corrected_pos = criterion_text.find(entity.text)
    if corrected_pos >= 0:
        logger.info(
            "Corrected span for '%s': [%d:%d] -> [%d:%d]",
            entity.text,
            span_start,
            span_end,
            corrected_pos,
            corrected_pos + len(entity.text),
        )
        return corrected_pos, corrected_pos + len(entity.text)

    logger.warning(
        "Could not find '%s' in criterion text, keeping original spans",
        entity.text,
    )
    return span_start, span_end


async def extract_entities_node(state: GroundingState) -> dict[str, Any]:
    """Extract medical entities from criteria using structured LLM output.

    Loads criteria texts from the database, renders prompts via Jinja2,
    calls ChatVertexAI with structured output, and validates span positions.

    Args:
        state: Current grounding state with criteria_ids.

    Returns:
        Dict with criteria_texts and raw_entities, or error dict on failure.
    """
    if state.get("error"):
        return {}

    try:
        criteria_texts = _load_criteria_texts(state["criteria_ids"])

        if not criteria_texts:
            logger.warning("No criteria found for batch %s", state.get("batch_id"))
            return {"criteria_texts": [], "raw_entities": []}

        # Render prompts
        system_prompt, user_prompt = render_prompts(
            prompts_dir=PROMPTS_DIR,
            system_template="system.jinja2",
            user_template="user.jinja2",
            prompt_vars={"criteria": criteria_texts},
        )

        # Create LLM with structured output
        model_name = _get_model_name()
        llm = ChatVertexAI(model_name=model_name, temperature=0)
        structured_llm = llm.with_structured_output(BatchEntityExtractionResult)

        result = await structured_llm.ainvoke(
            [("system", system_prompt), ("user", user_prompt)]
        )

        # Handle both Pydantic model and dict responses
        if isinstance(result, dict):
            extraction_result = BatchEntityExtractionResult(**result)
        else:
            extraction_result = cast(BatchEntityExtractionResult, result)

        # Build raw_entities with span validation (Pitfall 4)
        raw_entities: list[dict[str, Any]] = []
        criteria_text_map = {ct["id"]: ct["text"] for ct in criteria_texts}

        for per_criterion in extraction_result.results:
            criterion_text = criteria_text_map.get(per_criterion.criterion_id, "")
            for entity in per_criterion.entities:
                start, end = _validate_span(entity, criterion_text)
                raw_entities.append(
                    {
                        "criteria_id": per_criterion.criterion_id,
                        "text": entity.text,
                        "entity_type": entity.entity_type.value,
                        "span_start": start,
                        "span_end": end,
                        "context_window": entity.context_window,
                    }
                )

        logger.info(
            "Extracted %d entities from %d criteria for batch %s",
            len(raw_entities),
            len(criteria_texts),
            state.get("batch_id"),
        )
        return {"criteria_texts": criteria_texts, "raw_entities": raw_entities}

    except Exception as e:
        logger.exception(
            "Entity extraction failed for batch %s: %s",
            state.get("batch_id", "unknown"),
            e,
        )
        return {"error": f"Entity extraction failed: {e}"}
