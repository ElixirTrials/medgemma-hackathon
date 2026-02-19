"""Pydantic schemas for terminology grounding results and API candidates.

These schemas define the machine-readable format for agent-to-agent communication
between TerminologyRouter and MedGemma during the grounding phase.

Per user decision: "Agent-to-agent communication must be machine-readable
(no superfluous commentary between agents)."
"""

from pydantic import BaseModel, Field


class GroundingCandidate(BaseModel):
    """A single candidate match from a terminology API.

    Attributes:
        source_api: Name of the API that produced this candidate.
        code: Terminology code (e.g. UMLS CUI "C0011847", RxNorm "6809").
        preferred_term: Canonical preferred name for the concept.
        semantic_type: UMLS semantic type. None for non-UMLS APIs.
        score: Relevance score from the API (0.0-1.0). Higher is better.
    """

    source_api: str = Field(
        description="Name of the terminology API that produced this candidate"
    )
    code: str = Field(description="Terminology code (CUI, RxNorm, ICD-10, etc.)")
    preferred_term: str = Field(description="Canonical preferred name for the concept")
    semantic_type: str | None = Field(
        default=None,
        description=(
            "UMLS semantic type (e.g. 'Disease or Syndrome'). None for non-UMLS APIs."
        ),
    )
    score: float = Field(
        ge=0.0,
        le=1.0,
        description="Relevance score from the API (0.0-1.0). Higher is better.",
    )


class EntityGroundingResult(BaseModel):
    """Grounding result for a single entity after MedGemma evaluation.

    Contains the selected code, all candidates considered, and the reasoning
    used to make the selection. Provides full audit trail per user decision:
    "All agent exchanges persisted to database."

    Attributes:
        entity_text: Original entity text as extracted from the protocol.
        entity_type: Entity type (e.g. "Medication", "Condition").
        selected_code: The chosen terminology code. None if grounding failed.
        selected_system: The coding system for the selected code.
        preferred_term: Canonical name for the selected code.
        confidence: MedGemma's confidence in the selection (0.0-1.0).
        candidates: All candidates returned by terminology APIs.
        reasoning: MedGemma's explanation for selecting this code.
        field_mappings: Suggested AutoCriteria field mappings
            (Entity, Operator, Value, Unit, Time). None if not yet generated.
    """

    entity_text: str = Field(description="Original entity text from the protocol")
    entity_type: str = Field(description="Entity type (e.g. 'Medication', 'Condition')")
    selected_code: str | None = Field(
        default=None,
        description="The chosen terminology code. None if grounding failed.",
    )
    selected_system: str | None = Field(
        default=None,
        description="The coding system for the selected code (e.g. 'UMLS').",
    )
    preferred_term: str | None = Field(
        default=None,
        description="Canonical name for the selected code.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="MedGemma's confidence in the selection (0.0-1.0).",
    )
    candidates: list[GroundingCandidate] = Field(
        default_factory=list,
        description="All candidates returned by terminology APIs.",
    )
    reasoning: str = Field(
        default="",
        description="MedGemma's explanation for selecting this code.",
    )
    field_mappings: list[dict] | None = Field(
        default=None,
        description=(
            "Suggested AutoCriteria field mappings "
            "(Entity, Operator, Value, Unit, Time)."
        ),
    )


class GroundingBatchResult(BaseModel):
    """Batch grounding result for all entities in a criteria batch.

    Implements the error accumulation pattern — partial failures are preserved
    alongside successes. Per user decision: "Errors accumulate — process all
    entities, collect errors alongside successes (partial results are useful)."

    Attributes:
        results: Successfully grounded entity results.
        errors: Error messages for entities that failed grounding.
    """

    results: list[EntityGroundingResult] = Field(
        default_factory=list,
        description="Successfully grounded entity results.",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Error messages for entities that failed grounding.",
    )
