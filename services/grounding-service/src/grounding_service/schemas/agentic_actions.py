"""Pydantic models for MedGemma agentic JSON responses.

These models define the structured output schema that MedGemma returns
in the agentic grounding loop. Since MedGemma (Model Garden endpoint)
doesn't support native tool calling, we parse its raw text output
as JSON conforming to these schemas.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ExtractedEntityAction(BaseModel):
    """An entity extracted by MedGemma with a suggested UMLS search term."""

    text: str = Field(description="Exact text from criterion")
    entity_type: str = Field(
        description=(
            "One of: Condition, Medication, Procedure, "
            "Lab_Value, Demographic, Biomarker"
        ),
    )
    search_term: str = Field(
        description="UMLS search term (standard medical term, may differ from text)"
    )
    criterion_id: str = Field(
        default="",
        description="ID of the criterion this entity was extracted from",
    )
    span_start: int = Field(
        default=0, description="Character offset start in criterion text"
    )
    span_end: int = Field(
        default=0, description="Character offset end in criterion text"
    )
    context_window: str = Field(
        default="", description="Surrounding context for disambiguation"
    )


class GroundingSelection(BaseModel):
    """MedGemma's selection of the best UMLS match for an entity."""

    entity_text: str = Field(description="Original entity text")
    entity_type: str = Field(description="Entity type classification")
    selected_cui: str | None = Field(default=None, description="Selected UMLS CUI")
    preferred_term: str | None = Field(default=None, description="UMLS preferred term")
    snomed_code: str | None = Field(default=None, description="SNOMED CT code")
    confidence: float = Field(default=0.0, description="Confidence score 0.0-1.0")
    reasoning: str = Field(default="", description="Why this match was selected")


class AgenticAction(BaseModel):
    """MedGemma's structured response in the agentic loop."""

    action_type: Literal["extract", "evaluate", "refine"] = Field(
        description="Type of action: extract, evaluate, or refine"
    )
    entities: list[ExtractedEntityAction] = Field(
        default_factory=list,
        description="Populated for extract and refine actions",
    )
    selections: list[GroundingSelection] = Field(
        default_factory=list,
        description="Populated for evaluate actions",
    )
