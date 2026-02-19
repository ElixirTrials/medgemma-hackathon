"""Field mapping generation tool for grounded entities.

Per user decision: "Generate suggested field_mappings during grounding (ground node)"
Per CONTEXT.md: "Criteria should be decomposed per AutoCriteria pattern: separate
Entity, Operator, Value, Unit, Time"
Per user decision: "MedGemma and Gemini collaborate: Gemini uses MedGemma as
medical expert"

Uses Gemini to generate suggested field mappings for the grounded entity +
criterion text. These are best-effort suggestions — reviewer can edit in UI.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from pydantic import BaseModel, Field

from protocol_processor.schemas.grounding import EntityGroundingResult

logger = logging.getLogger(__name__)


class FieldMappingItem(BaseModel):
    """A single AutoCriteria field mapping decomposition.

    Per the AutoCriteria pattern, each criterion is decomposed into
    separate Entity, Operator, Value, Unit, and Time components.
    """

    entity: str = Field(description="The medical entity name (e.g. 'HbA1c')")
    relation: str = Field(
        description="The logical operator/relation (e.g. '<', '>', '=', 'has', 'is')"
    )
    value: str = Field(
        description=(
            "The specific value or threshold (e.g. '7%', 'positive', 'confirmed')"
        )
    )
    unit: str | None = Field(
        default=None,
        description="Optional unit of measurement (e.g. '%', 'mg/dL', 'years')",
    )


class FieldMappingResponse(BaseModel):
    """Gemini structured output for field mappings."""

    mappings: list[FieldMappingItem] = Field(
        default_factory=list,
        description="List of AutoCriteria field mapping decompositions",
    )


async def generate_field_mappings(
    entity: EntityGroundingResult,
    criterion_text: str,
) -> list[dict[str, Any]]:
    """Generate suggested field mappings for a grounded entity.

    Uses Gemini to decompose the criterion text into AutoCriteria field mappings:
    Entity, Operator, Value, Unit, Time components for each discrete condition.

    This is a best-effort suggestion — reviewer can edit in the UI. Errors
    are logged and an empty list returned (not propagated as failures).

    Args:
        entity: Grounded EntityGroundingResult with code and preferred term.
        criterion_text: Full criterion text for context.

    Returns:
        List of field mapping dicts with keys: entity, relation, value, unit.
        Empty list if generation fails.
    """
    if not criterion_text:
        return []

    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key:
        logger.warning(
            "GOOGLE_API_KEY not set — skipping field mapping generation for '%s'",
            entity.entity_text[:50],
        )
        return []

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI

        gemini_model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
        gemini = ChatGoogleGenerativeAI(
            model=gemini_model_name,
            google_api_key=google_api_key,
        )
        structured_llm = gemini.with_structured_output(FieldMappingResponse)

        # Build a context-rich prompt for field mapping generation
        grounded_term = entity.preferred_term or entity.entity_text
        code_context = ""
        if entity.selected_code and entity.selected_system:
            system = entity.selected_system.upper()
            code_context = f"(grounded to {system} code: {entity.selected_code})"

        prompt = (
            "You are a clinical trial protocol analyst. Decompose the"
            " following criterion into structured AutoCriteria field"
            " mappings using the Entity-Relation-Value-Unit pattern.\n\n"
            f"Medical entity: {grounded_term} {code_context}\n"
            f"Criterion text: {criterion_text}\n\n"
            "Instructions:\n"
            "- Extract each discrete measurement, threshold, or condition"
            " as a separate mapping\n"
            "- entity: the specific measurement or concept"
            " (e.g. 'HbA1c', 'Age', 'eGFR')\n"
            "- relation: the logical operator"
            " (<, >, >=, <=, =, has, is, within, not)\n"
            "- value: the specific threshold or value"
            " (e.g. '7', 'positive', 'confirmed')\n"
            "- unit: the unit if applicable (e.g. '%', 'mg/dL', 'years')"
            " or null\n"
            "- Create one mapping per discrete condition in the criterion\n"
            "- If no clear measurement exists, create one mapping with"
            " relation='has', value='confirmed'"
        )

        result = structured_llm.invoke(prompt)
        if isinstance(result, dict):
            response = FieldMappingResponse.model_validate(result)
        else:
            response = result  # type: ignore[assignment]

        mappings = [
            {
                "entity": m.entity,
                "relation": m.relation,
                "value": m.value,
                "unit": m.unit,
                "entity_concept_id": entity.selected_code,
                "entity_concept_system": entity.selected_system,
                "omop_concept_id": entity.omop_concept_id,
            }
            for m in response.mappings
        ]

        logger.info(
            "Generated %d field mapping(s) for entity '%s'",
            len(mappings),
            entity.entity_text[:50],
        )
        return mappings

    except Exception as e:
        logger.warning(
            "Field mapping generation failed for entity '%s': %s",
            entity.entity_text[:50],
            e,
            exc_info=True,
        )
        # Best-effort: return empty list on failure
        return []
