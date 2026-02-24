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
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from protocol_processor.schemas.grounding import EntityGroundingResult
from protocol_processor.tools.gemini_utils import (
    create_structured_llm,
    parse_structured_output,
)

logger = logging.getLogger(__name__)

# Mapping from legacy/LLM relation operators to the frontend's RelationOperator set
_RELATION_MAP: dict[str, str] = {
    "has": "contains",
    "is": "=",
    "not": "not_contains",
    "==": "=",
    "range": "within",
}


def _normalize_relation(rel: str) -> str:
    """Normalize a relation operator to the frontend's accepted set.

    Maps legacy operators (has, is, not, ==, range) to the standard set:
    =, !=, >, >=, <, <=, within, not_in_last, contains, not_contains.
    """
    return _RELATION_MAP.get(rel, rel)


class FieldMappingValue(BaseModel):
    """Typed value object for field mappings with type discriminator.

    Supports three value shapes:
    - standard: single value + unit (e.g. HbA1c < 7%)
    - range: min/max + unit (e.g. Age 18-65 years)
    - temporal: duration + unit (e.g. within 6 months)
    """

    type: Literal["standard", "range", "temporal"] = Field(
        description="Value type discriminator"
    )
    value: str | None = Field(
        default=None, description="Value for standard type (e.g. '7')"
    )
    unit: str | None = Field(
        default=None, description="Unit of measurement (e.g. '%', 'mg/dL', 'months')"
    )
    min: str | None = Field(default=None, description="Minimum value for range type")
    max: str | None = Field(default=None, description="Maximum value for range type")
    duration: str | None = Field(
        default=None, description="Duration value for temporal type"
    )

    @model_validator(mode="after")
    def truncate_long_strings(self) -> "FieldMappingValue":
        """Guard against LLM repetition loops producing absurdly long values."""
        _max = 200
        for attr in ("value", "unit", "min", "max", "duration"):
            val = getattr(self, attr)
            if isinstance(val, str) and len(val) > _max:
                setattr(self, attr, val[:_max])
        return self


# The set of valid relation operators accepted by the frontend
RelationOperator = Literal[
    "=", "!=", ">", ">=", "<", "<=", "within", "not_in_last", "contains", "not_contains"
]


class FieldMappingItem(BaseModel):
    """A single AutoCriteria field mapping decomposition.

    Per the AutoCriteria pattern, each criterion is decomposed into
    separate Entity, Operator, Value, Unit, and Time components.
    """

    entity: str = Field(description="The medical entity name (e.g. 'HbA1c')")
    relation: RelationOperator = Field(
        description="The logical operator/relation (e.g. '<', '>', '=', 'contains')"
    )
    value: FieldMappingValue = Field(
        description="Typed value object with type discriminator"
    )
    unit: str | None = Field(
        default=None,
        description="Optional unit of measurement (e.g. '%', 'mg/dL', 'years')",
    )
    value_concept_id: str | None = Field(
        default=None,
        description="OMOP concept ID for categorical values",
    )
    value_concept_system: str | None = Field(
        default=None,
        description="Terminology system for value_concept_id (e.g. 'SNOMED', 'OMOP')",
    )

    @field_validator("relation", mode="before")
    @classmethod
    def normalize_relation(cls, v: str) -> str:
        """Normalize LLM-generated relation operators before Literal validation."""
        if isinstance(v, str):
            return _normalize_relation(v)
        return v


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
        List of field mapping dicts with keys: entity, relation, value,
        entity_code, entity_system, omop_concept_id, entity_type.
        Empty list if generation fails.
    """
    if not criterion_text:
        return []

    structured_llm = create_structured_llm(FieldMappingResponse)
    if structured_llm is None:
        return []

    try:
        # Build a context-rich prompt for field mapping generation
        grounded_term = entity.preferred_term or entity.entity_text
        code_context = ""
        if entity.selected_code and entity.selected_system:
            system = entity.selected_system.upper()
            code_context = f"(grounded to {system} code: {entity.selected_code})"

        prompt = (
            "<role>Clinical trial protocol analyst. Decompose criterion"
            " into Entity-Relation-Value-Unit field mappings.</role>\n\n"
            "<entity_context>\n"
            f"Medical entity: {grounded_term} {code_context}\n"
            f"Criterion text: {criterion_text}\n"
            "</entity_context>\n\n"
            "<rules>\n"
            "- Extract each discrete measurement, threshold, or condition"
            " as a separate mapping\n"
            "- relation: one of =, !=, >, >=, <, <=, within,"
            " not_in_last, contains, not_contains\n"
            "- Boolean normalization: presence → relation='=', value='True';"
            " absence → relation='!=', value='True'."
            " Never use 'present'/'absent'/'confirmed' as values.\n"
            "- value types: standard {value, unit},"
            " range {min, max, unit}, temporal {duration, unit}\n"
            "- Temporal duration MUST be a plain number."
            ' "within 5 days" → duration="5", unit="days"\n'
            "- Default: if no measurement, use relation='=',"
            ' value={"type":"standard","value":"True","unit":null}\n'
            "</rules>\n\n"
            "<anti_patterns>\n"
            "BAD: value='present' → use value='True'\n"
            "BAD: duration='5-days-ago' → use duration='5', unit='days'\n"
            "</anti_patterns>"
        )

        from protocol_processor.tracing import llm_span

        with llm_span("gemini_field_mapping") as llm:
            llm.set_request(prompt)
            result = await structured_llm.ainvoke(prompt)
            llm.set_response(str(result))

        response = parse_structured_output(result, FieldMappingResponse)

        mappings = [
            {
                "entity": m.entity,
                "relation": m.relation,
                "value": m.value.model_dump(exclude_none=True),
                "entity_code": entity.selected_code,
                "entity_system": entity.selected_system,
                "omop_concept_id": entity.omop_concept_id,
                "entity_type": entity.entity_type,
                "value_concept_id": m.value_concept_id,
                "value_concept_system": m.value_concept_system,
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
