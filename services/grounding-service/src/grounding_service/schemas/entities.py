"""Pydantic models for Gemini/MedGemma structured output of entity extraction.

These models define the schema that ChatVertexAI.with_structured_output()
uses to constrain the LLM's JSON response. Every field includes a
Field(description=...) to guide the LLM's output generation.

Nesting is kept to max 2 levels to avoid serialization issues with
ChatVertexAI (per Phase 3 decision on structured output depth).
"""

from enum import Enum

from pydantic import BaseModel, Field


class EntityType(str, Enum):
    """Medical entity type classification.

    Covers the 6 required categories for clinical trial
    eligibility criteria entity extraction.
    """

    CONDITION = "Condition"
    MEDICATION = "Medication"
    PROCEDURE = "Procedure"
    LAB_VALUE = "Lab_Value"
    DEMOGRAPHIC = "Demographic"
    BIOMARKER = "Biomarker"


class ExtractedEntity(BaseModel):
    """A single medical entity extracted from criteria text.

    Represents one entity with its type, position in the source
    text (span), and surrounding context for disambiguation.
    """

    text: str = Field(
        description="The exact entity text as it appears in the criterion",
    )
    entity_type: EntityType = Field(
        description=(
            "Type of medical entity: Condition, Medication, "
            "Procedure, Lab_Value, Demographic, or Biomarker"
        ),
    )
    span_start: int = Field(
        description=(
            "Character offset where the entity starts in the criterion text (0-based)"
        ),
    )
    span_end: int = Field(
        description=(
            "Character offset where the entity ends in the criterion text (exclusive)"
        ),
    )
    context_window: str = Field(
        description=(
            "Surrounding text (up to 20 characters before and after) for disambiguation"
        ),
    )


class EntityExtractionResult(BaseModel):
    """All entities extracted from a single criterion.

    Groups extracted entities with the criterion ID they
    were extracted from, enabling per-criterion tracking.
    """

    entities: list[ExtractedEntity] = Field(
        description="All medical entities found in the criterion text",
    )
    criterion_id: str = Field(
        description="ID of the criterion this extraction is from",
    )


class BatchEntityExtractionResult(BaseModel):
    """Entities extracted from a batch of criteria.

    Top-level result containing extraction results for
    multiple criteria in a single batch.
    """

    results: list[EntityExtractionResult] = Field(
        description="Extraction results per criterion in the batch",
    )
