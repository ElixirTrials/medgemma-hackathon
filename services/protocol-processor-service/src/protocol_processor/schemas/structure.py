"""Pydantic schemas for expression tree logic detection and storage.

Phase 2: Structured expression trees that capture AND/OR/NOT logic from
criteria text. Two schema categories:

1. LLM output schemas (LogicNode, LogicDetectionResponse) — Gemini structured
   output for detecting logical structure in criterion text.
2. JSONB storage schemas (ExpressionNode, StructuredCriterionTree) — stored
   in Criteria.structured_criterion for UI rendering and CIRCE export.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LogicNode(BaseModel):
    """Tree node representing logical structure detected by Gemini.

    ATOMIC nodes reference a field_mapping by index. AND/OR/NOT nodes
    contain children. This schema is the Gemini structured output target.
    """

    node_type: str = Field(
        description=(
            "Logic operator: 'AND', 'OR', 'NOT', or 'ATOMIC'. "
            "ATOMIC nodes are leaves referencing a field_mapping."
        )
    )
    field_mapping_index: int | None = Field(
        default=None,
        description=(
            "Index into the field_mappings list (0-based). Only set for ATOMIC nodes."
        ),
    )
    children: list[LogicNode] | None = Field(
        default=None,
        description="Child nodes for AND/OR/NOT operators. None for ATOMIC.",
    )


class LogicDetectionResponse(BaseModel):
    """Gemini structured output for logic detection.

    Contains the root of the logic tree and the model's reasoning
    about why it chose this particular logical structure.
    """

    root: LogicNode = Field(description="Root node of the detected logic tree.")
    reasoning: str = Field(
        default="",
        description="Explanation of the detected logical structure.",
    )


class ExpressionNode(BaseModel):
    """Node in the stored expression tree (JSONB in criteria.structured_criterion).

    Leaf nodes carry atomic criterion details. Branch nodes carry the logic
    operator and children. This is the serialization format for DB storage
    and UI rendering.
    """

    type: str = Field(description="Node type: 'AND', 'OR', 'NOT', or 'ATOMIC'.")
    atomic_criterion_id: str | None = Field(
        default=None,
        description="FK to atomic_criteria.id. Set for ATOMIC nodes only.",
    )
    entity: str | None = Field(
        default=None,
        description="Entity name from field_mapping. Set for ATOMIC nodes.",
    )
    relation: str | None = Field(
        default=None,
        description="Relation operator from field_mapping. Set for ATOMIC nodes.",
    )
    value: str | None = Field(
        default=None,
        description="Value from field_mapping. Set for ATOMIC nodes.",
    )
    unit: str | None = Field(
        default=None,
        description="Unit from field_mapping. Set for ATOMIC nodes.",
    )
    omop_concept_id: str | None = Field(
        default=None,
        description="OMOP concept ID for this atom. Set for ATOMIC nodes.",
    )
    children: list[ExpressionNode] | None = Field(
        default=None,
        description="Child expression nodes. Set for AND/OR/NOT nodes.",
    )


class StructuredCriterionTree(BaseModel):
    """Top-level wrapper stored in Criteria.structured_criterion JSONB.

    Contains the expression tree root, confidence source (llm vs fallback),
    and the model name used for structure detection.
    """

    root: ExpressionNode = Field(description="Root node of the expression tree.")
    structure_confidence: str = Field(
        default="fallback",
        description="Source of structure: 'llm' or 'fallback'.",
    )
    structure_model: str | None = Field(
        default=None,
        description="Model name used for logic detection (e.g. 'gemini-2.0-flash').",
    )
