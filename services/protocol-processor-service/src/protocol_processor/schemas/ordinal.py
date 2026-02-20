"""Pydantic schemas for ordinal scale resolution via Gemini structured output.

Used by the ordinal_resolve node to identify unrecognized clinical ordinal
scoring systems (Child-Pugh, GCS, APACHE II, etc.) and propose YAML config
entries for human review.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class OrdinalValueProposal(BaseModel):
    """Proposed value mapping for a single grade within an ordinal scale."""

    grade: str = Field(
        description="The grade or score value, e.g. '5', 'A', 'B'.",
    )
    snomed_code: str | None = Field(
        default=None,
        description="SNOMED CT code for this grade, if known.",
    )
    loinc_answer: str | None = Field(
        default=None,
        description="LOINC answer code for this grade, if known.",
    )
    description: str | None = Field(
        default=None,
        description="Human-readable description of what this grade means.",
    )


class OrdinalScaleProposal(BaseModel):
    """LLM proposal for a single entity that may be an ordinal scale."""

    entity_text: str = Field(
        description="Original entity text from AtomicCriterion.",
    )
    is_ordinal_scale: bool = Field(
        description="Whether this entity is a clinical ordinal scoring system.",
    )
    confidence: float = Field(
        description="Confidence score from 0.0 to 1.0.",
    )
    scale_name: str | None = Field(
        default=None,
        description="Snake_case key for YAML config, e.g. 'child_pugh'.",
    )
    entity_aliases: list[str] = Field(
        default_factory=list,
        description="Alternative names for this scale.",
    )
    loinc_code: str | None = Field(
        default=None,
        description="LOINC code for this ordinal scale, if known.",
    )
    unit_concept_id: int = Field(
        default=8527,
        description="UCUM unit concept ID. Always 8527 ({score}) for ordinal scales.",
    )
    values: list[OrdinalValueProposal] = Field(
        default_factory=list,
        description="Proposed value mappings for grades within this scale.",
    )
    reasoning: str | None = Field(
        default=None,
        description="Explanation of why this entity is/isn't an ordinal scale.",
    )


class OrdinalResolutionResponse(BaseModel):
    """Top-level Gemini structured output for ordinal resolution."""

    proposals: list[OrdinalScaleProposal] = Field(
        description="One proposal per candidate entity.",
    )
