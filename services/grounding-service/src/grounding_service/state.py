"""Grounding workflow state definition for the entity grounding agent."""

from typing import Any

from typing_extensions import TypedDict


class GroundingState(TypedDict):
    """State for the entity grounding workflow.

    Carries data between LangGraph nodes:
    extract_entities -> ground_to_umls -> map_to_snomed -> validate_confidence

    Attributes:
        batch_id: UUID of the CriteriaBatch being processed.
        protocol_id: UUID of the protocol these criteria belong to.
        criteria_ids: List of Criterion record IDs to process.
        criteria_texts: Loaded criteria with id, text, type, and category.
        raw_entities: Extracted entities with span positions and types.
        grounded_entities: Entities enriched with UMLS/SNOMED codes.
        entity_ids: Persisted Entity record IDs after storage.
        error: Error message if any node fails; enables conditional routing.
    """

    batch_id: str
    protocol_id: str
    criteria_ids: list[str]
    criteria_texts: list[dict[str, Any]]
    raw_entities: list[dict[str, Any]]
    grounded_entities: list[dict[str, Any]]
    entity_ids: list[str]
    error: str | None
