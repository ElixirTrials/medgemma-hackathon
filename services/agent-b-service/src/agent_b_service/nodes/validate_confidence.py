"""Validate confidence node: CUI validation, Entity persistence, event publishing.

This is the final node in the grounding pipeline. It validates CUI codes
against the UMLS REST API, creates Entity records in the database,
updates the CriteriaBatch status, and publishes an EntitiesGrounded event
via the transactional outbox pattern.

Failed CUI validation does not block the pipeline -- entities are
downgraded to expert_review method with confidence 0.0.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_b_service.state import GroundingState
from agent_b_service.umls_client import validate_cui

logger = logging.getLogger(__name__)


async def _validate_cui_codes(
    grounded_entities: list[dict[str, Any]],
) -> None:
    """Validate CUI codes and downgrade invalid ones to expert_review.

    Modifies entities in-place. If a CUI fails validation, its grounding
    fields are cleared and method set to expert_review.

    Args:
        grounded_entities: List of grounded entity dicts to validate.
    """
    for entity in grounded_entities:
        cui = entity.get("umls_cui")
        if not cui:
            continue
        is_valid = await validate_cui(cui)
        if not is_valid:
            logger.warning(
                "CUI %s failed validation, downgrading "
                "entity '%s' to expert_review",
                cui,
                entity.get("text"),
            )
            entity["umls_cui"] = None
            entity["snomed_code"] = None
            entity["grounding_method"] = "expert_review"
            entity["grounding_confidence"] = 0.0


def _create_entity_record(ge: dict[str, Any]) -> Any:
    """Create an Entity DB model from a grounded entity dict.

    Args:
        ge: Grounded entity dict with all fields.

    Returns:
        Entity SQLModel instance (not yet added to session).
    """
    from shared.models import Entity

    review_status = (
        "pending"
        if ge.get("grounding_method") == "expert_review"
        else None
    )

    # Map context_window: store as dict if string
    context_window = ge.get("context_window")
    if isinstance(context_window, str):
        context_window = {"text": context_window}

    return Entity(
        criteria_id=ge["criteria_id"],
        entity_type=ge["entity_type"],
        text=ge["text"],
        span_start=ge.get("span_start"),
        span_end=ge.get("span_end"),
        umls_cui=ge.get("umls_cui"),
        snomed_code=ge.get("snomed_code"),
        preferred_term=ge.get("preferred_term"),
        grounding_confidence=ge.get("grounding_confidence"),
        grounding_method=ge.get("grounding_method"),
        review_status=review_status,
        context_window=context_window,
    )


async def validate_confidence_node(
    state: GroundingState,
) -> dict[str, Any]:
    """Validate CUI codes, persist Entity records, publish event.

    For each grounded entity with a umls_cui:
    1. Validates the CUI exists in UMLS
    2. Downgrades to expert_review if validation fails
    3. Creates Entity DB records
    4. Updates CriteriaBatch status to 'entities_grounded'
    5. Publishes EntitiesGrounded event via outbox

    Args:
        state: Current grounding state with grounded_entities.

    Returns:
        Dict with entity_ids list, or error dict on failure.
    """
    if state.get("error"):
        return {}

    grounded_entities = state.get("grounded_entities", [])
    if not grounded_entities:
        return {"entity_ids": []}

    try:
        from api_service.storage import engine
        from events_py.models import DomainEventKind
        from events_py.outbox import persist_with_outbox
        from shared.models import CriteriaBatch
        from sqlmodel import Session

        # Step 1: Validate CUI codes
        await _validate_cui_codes(grounded_entities)

        # Step 2: Persist Entity records
        entity_ids: list[str] = []
        expert_review_count = 0

        with Session(engine) as session:
            for ge in grounded_entities:
                db_entity = _create_entity_record(ge)
                if db_entity.review_status == "pending":
                    expert_review_count += 1
                session.add(db_entity)
                session.flush()
                entity_ids.append(db_entity.id)

            # Step 3: Update CriteriaBatch status
            batch = session.get(CriteriaBatch, state["batch_id"])
            if batch:
                batch.status = "entities_grounded"
                session.add(batch)

                # Step 4: Publish EntitiesGrounded event
                persist_with_outbox(
                    session=session,
                    entity=batch,
                    event_type=DomainEventKind.ENTITIES_GROUNDED,
                    aggregate_type="criteria_batch",
                    aggregate_id=state["batch_id"],
                    payload={
                        "batch_id": state["batch_id"],
                        "protocol_id": state["protocol_id"],
                        "entity_ids": entity_ids,
                        "entity_count": len(entity_ids),
                        "expert_review_count": expert_review_count,
                    },
                )

            session.commit()

        logger.info(
            "Validated and persisted %d entities (%d for expert review) "
            "for batch %s",
            len(entity_ids),
            expert_review_count,
            state.get("batch_id"),
        )
        return {"entity_ids": entity_ids}

    except Exception as e:
        logger.exception(
            "Validation/persistence failed for batch %s: %s",
            state.get("batch_id", "unknown"),
            e,
        )
        return {"error": f"Validation failed: {e}"}
