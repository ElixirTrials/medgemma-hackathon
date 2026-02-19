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
from pathlib import Path
from typing import Literal, cast

from jinja2 import Environment, FileSystemLoader
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


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


def _render_decompose_prompt(criterion_text: str, category: str | None) -> str:
    """Render the entity decomposition Jinja2 prompt template.

    Args:
        criterion_text: Full criterion sentence to decompose.
        category: Optional category hint from extraction (e.g. "lab_values").

    Returns:
        Rendered prompt string for Gemini.
    """
    env = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)), autoescape=False)
    template = env.get_template("entity_decompose.jinja2")
    return template.render(criterion_text=criterion_text, category=category or "")


async def decompose_entities_from_criterion(
    criterion_text: str,
    category: str | None,
) -> list[dict]:
    """Extract discrete medical entities from a criterion sentence.

    Uses Gemini with structured output to decompose a criterion sentence
    into individual medical terms with correct entity types. Falls back
    to empty list on failure -- caller handles fallback to full-text entity.

    Args:
        criterion_text: The full criterion sentence to decompose.
        category: Optional category hint from extraction.

    Returns:
        List of dicts with "text" and "entity_type" keys, or empty list on failure.
    """
    try:
        gemini = ChatGoogleGenerativeAI(
            model=os.getenv("GEMINI_MODEL_NAME", "gemini-2.0-flash"),
            google_api_key=os.getenv("GOOGLE_API_KEY"),
        )
        structured = gemini.with_structured_output(DecomposedEntityList)
        prompt = _render_decompose_prompt(criterion_text, category)
        result = await structured.ainvoke(prompt)
        if isinstance(result, dict):
            result = DecomposedEntityList.model_validate(result)
        decomposed = cast(DecomposedEntityList, result)
        return [e.model_dump() for e in decomposed.entities]
    except Exception as e:
        logger.error(
            "Entity decomposition failed for criterion '%s': %s",
            criterion_text[:80],
            e,
        )
        return []  # Caller falls back to full-text entity
