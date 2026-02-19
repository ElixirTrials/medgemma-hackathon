"""Persist node: commit grounding results and update protocol status.

This is the final node in the protocol processing pipeline:
ingest -> extract -> parse -> ground -> persist

Per user decisions:
- Partial success: some entities succeeded + some failed -> pending_review
- Total failure: ALL entities failed -> grounding_failed
- Field mappings stored in Criteria.conditions JSONB under 'field_mappings' key
- Protocol status updated to 'pending_review' on success (final state)

Architecture note: Graph nodes ARE allowed to import from api-service for DB.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from api_service.protocols import _apply_review_inheritance
from api_service.storage import engine
from shared.models import AuditLog, Criteria, CriteriaBatch, Entity, Protocol
from sqlmodel import Session

from protocol_processor.state import PipelineState

logger = logging.getLogger(__name__)


def _create_entity_record(grounding_result: dict[str, Any]) -> Entity:
    """Create an Entity DB record from a grounding result dict.

    Args:
        grounding_result: EntityGroundingResult model_dump() dict.

    Returns:
        Entity SQLModel instance (not yet added to session).
    """
    entity_text = grounding_result.get("entity_text", "")
    entity_type = grounding_result.get("entity_type", "")
    confidence = grounding_result.get("confidence", 0.0)
    selected_code = grounding_result.get("selected_code")
    selected_system = grounding_result.get("selected_system")

    # Determine grounding method
    if selected_code and confidence >= 0.7:
        grounding_method = "terminology_router_medgemma"
    elif selected_code:
        grounding_method = "terminology_router_medgemma_low_conf"
    else:
        grounding_method = "expert_review"

    # Review pending for entities without confirmed grounding
    review_status = "pending" if not selected_code or confidence < 0.5 else None

    # Map code to the correct Entity field based on source terminology system
    umls_cui = None
    snomed_code = None
    rxnorm_code = None
    icd10_code = None
    loinc_code = None
    hpo_code = None

    system_field_map = {
        "umls": "umls_cui",
        "snomed": "snomed_code",
        "rxnorm": "rxnorm_code",
        "icd10": "icd10_code",
        "loinc": "loinc_code",
        "hpo": "hpo_code",
    }

    if selected_system and selected_code:
        field = system_field_map.get(selected_system)
        if field == "umls_cui":
            umls_cui = selected_code
        elif field == "snomed_code":
            snomed_code = selected_code
        elif field == "rxnorm_code":
            rxnorm_code = selected_code
        elif field == "icd10_code":
            icd10_code = selected_code
        elif field == "loinc_code":
            loinc_code = selected_code
        elif field == "hpo_code":
            hpo_code = selected_code

    return Entity(
        entity_type=entity_type,
        text=entity_text,
        umls_cui=umls_cui,
        snomed_code=snomed_code,
        rxnorm_code=rxnorm_code,
        icd10_code=icd10_code,
        loinc_code=loinc_code,
        hpo_code=hpo_code,
        grounding_system=selected_system,
        preferred_term=grounding_result.get("preferred_term"),
        grounding_confidence=confidence,
        grounding_method=grounding_method,
        review_status=review_status,
    )


def _find_criterion_and_update_mappings(
    session: Session,
    batch_id: str,
    entity_text: str,
    field_mappings: list[dict] | None,
) -> str | None:
    """Find the Criteria record for this entity and update field_mappings.

    Matches the entity text against criteria in the batch using a substring
    search (best-effort). Updates conditions JSONB with field_mappings if any.

    Args:
        session: Active SQLModel session.
        batch_id: CriteriaBatch ID to search within.
        entity_text: Entity text to search for in criteria.
        field_mappings: Field mapping list from grounding, or None.

    Returns:
        Criteria ID if found, None otherwise.
    """
    from sqlmodel import select

    stmt = (
        select(Criteria)
        .where(Criteria.batch_id == batch_id)
        .where(Criteria.text.contains(entity_text[:50]))  # type: ignore[attr-defined]
    )
    criteria_records = session.exec(stmt).all()
    if not criteria_records:
        return None

    criterion = criteria_records[0]

    if field_mappings:
        existing = criterion.conditions or {}
        if not isinstance(existing, dict):
            existing = {"original_conditions": existing}
        criterion.conditions = {**existing, "field_mappings": field_mappings}
        session.add(criterion)

    return criterion.id


def _get_fallback_criterion_id(
    session: Session, batch_id: str, entity_text: str
) -> str | None:
    """Find any criteria in the batch as a fallback criterion_id.

    Args:
        session: Active SQLModel session.
        batch_id: CriteriaBatch ID to search within.
        entity_text: Entity text for logging.

    Returns:
        First criteria ID found, or None.
    """
    from sqlmodel import select

    first_criterion = session.exec(
        select(Criteria).where(Criteria.batch_id == batch_id)
    ).first()
    if first_criterion:
        return first_criterion.id
    logger.warning(
        "No criteria found in batch %s for entity '%s' — skipping",
        batch_id,
        entity_text[:50],
    )
    return None


def _update_batch_and_protocol(
    session: Session,
    batch_id: str | None,
    protocol_id: str,
    all_failed: bool,
    result_count: int,
    error_count: int,
) -> None:
    """Update CriteriaBatch and Protocol status after entity persistence.

    Args:
        session: Active SQLModel session.
        batch_id: CriteriaBatch ID to update (or None).
        protocol_id: Protocol ID to update.
        all_failed: True if all entities failed grounding.
        result_count: Total number of grounding results.
        error_count: Number of accumulated errors.
    """
    if batch_id:
        batch = session.get(CriteriaBatch, batch_id)
        if batch:
            batch.status = "entities_grounded"
            session.add(batch)

    protocol = session.get(Protocol, protocol_id)
    if protocol:
        old_status = protocol.status  # always "grounding" at this point
        if all_failed:
            protocol.status = "grounding_failed"
            protocol.error_reason = (
                f"All {result_count} entities failed grounding. Errors: {error_count}"
            )
        else:
            protocol.status = "pending_review"
            protocol.error_reason = None
        session.add(protocol)

        # Emit protocol_status_change audit log for both outcomes
        audit_log = AuditLog(
            event_type="protocol_status_change",
            actor_id="system:pipeline",
            target_type="protocol",
            target_id=protocol_id,
            details={
                "old_status": old_status,
                "new_status": protocol.status,
                "protocol_title": protocol.title,
            },
        )
        session.add(audit_log)


def _persist_entities(
    session: Session,
    grounding_results: list[dict[str, Any]],
    batch_id: str | None,
) -> list[str]:
    """Persist Entity records and update field_mappings on Criteria.

    Args:
        session: Active SQLModel session.
        grounding_results: List of EntityGroundingResult model_dump() dicts.
        batch_id: CriteriaBatch ID for criteria lookup.

    Returns:
        List of persisted entity IDs.
    """
    entity_ids: list[str] = []

    for result in grounding_results:
        entity_text = result.get("entity_text", "")
        field_mappings = result.get("field_mappings")
        criterion_id = None

        if batch_id:
            criterion_id = _find_criterion_and_update_mappings(
                session, batch_id, entity_text, field_mappings
            )
            if not criterion_id:
                criterion_id = _get_fallback_criterion_id(
                    session, batch_id, entity_text
                )

        if not criterion_id:
            logger.warning(
                "No criterion_id available for entity '%s' — skipping",
                entity_text[:50],
            )
            continue

        entity = _create_entity_record(result)
        entity.criteria_id = criterion_id
        session.add(entity)
        session.flush()
        entity_ids.append(entity.id)

    return entity_ids


async def persist_node(state: PipelineState) -> dict[str, Any]:
    """Persist grounding results to DB and update protocol status.

    Creates Entity records from grounded_entities_json. Updates Criteria
    records with field_mappings (in conditions JSONB). Updates protocol
    status to 'pending_review' (success) or 'grounding_failed' (total fail).

    Partial success: errors accumulated in state but some entities succeeded
    -> still marks as pending_review. Only marks grounding_failed if ALL failed.

    Args:
        state: Current pipeline state with grounded_entities_json, batch_id,
            protocol_id, and errors.

    Returns:
        Dict with status='completed' or status='failed' on total failure.
    """
    from protocol_processor.tracing import pipeline_span

    if state.get("error"):
        return {}

    protocol_id = state.get("protocol_id", "")
    with pipeline_span("persist_node", protocol_id=protocol_id) as span:
        span.set_inputs({"protocol_id": state.get("protocol_id", "")})

        try:
            grounded_json = state.get("grounded_entities_json")
            if not grounded_json:
                logger.warning(
                    "No grounded_entities_json in state for protocol %s",
                    state.get("protocol_id"),
                )
                span.set_outputs(
                    {
                        "status": "completed",
                        "note": "no grounded entities",
                    }
                )
                return {"status": "completed"}

            grounding_results: list[dict[str, Any]] = json.loads(grounded_json)
            protocol_id = state["protocol_id"]
            batch_id = state.get("batch_id")
            accumulated_errors = state.get("errors") or []

            logger.info(
                "Persisting %d grounding results for protocol %s (batch %s)",
                len(grounding_results),
                protocol_id,
                batch_id[:12] if batch_id else "none",
            )

            # Total failure: zero successes AND errors accumulated
            successful = [r for r in grounding_results if r.get("selected_code")]
            all_failed = (
                len(grounding_results) > 0
                and len(successful) == 0
                and len(accumulated_errors) > 0
            )

            with Session(engine) as session:
                entity_ids = _persist_entities(session, grounding_results, batch_id)
                _update_batch_and_protocol(
                    session,
                    batch_id,
                    protocol_id,
                    all_failed,
                    len(grounding_results),
                    len(accumulated_errors),
                )
                session.commit()

            # Apply review inheritance if this is a re-extraction run
            archived_reviewed = state.get("archived_reviewed_criteria")
            if archived_reviewed and protocol_id:
                try:
                    with Session(engine) as inheritance_session:
                        _apply_review_inheritance(
                            inheritance_session,
                            protocol_id,
                            archived_reviewed,
                        )
                    logger.info(
                        "Applied review inheritance for protocol %s"
                        " (%d archived criteria)",
                        protocol_id,
                        len(archived_reviewed),
                    )
                except Exception as e:
                    # Review inheritance failure should not block
                    logger.warning(
                        "Review inheritance failed for protocol %s: %s",
                        protocol_id,
                        e,
                    )

            final_status = "grounding_failed" if all_failed else "pending_review"
            logger.info(
                "Persist node complete for protocol %s: %d entities persisted,"
                " status=%s (accumulated_errors=%d)",
                protocol_id,
                len(entity_ids),
                final_status,
                len(accumulated_errors),
            )

            span.set_outputs(
                {
                    "entities_persisted": len(entity_ids),
                    "status": final_status,
                    "error_count": len(accumulated_errors),
                }
            )

            if all_failed:
                return {"status": "failed", "error": "All entities failed grounding"}
            return {"status": "completed"}

        except Exception as e:
            logger.exception(
                "Persist node failed for protocol %s: %s",
                state.get("protocol_id", "unknown"),
                e,
            )
            span.set_outputs({"error": str(e)})
            # On persist failure, try to mark protocol as grounding_failed
            try:
                protocol_id = state.get("protocol_id")
                if protocol_id:
                    with Session(engine) as session:
                        protocol = session.get(Protocol, protocol_id)
                        if protocol:
                            protocol.status = "grounding_failed"
                            protocol.error_reason = (
                                f"Persist failed: {type(e).__name__}"
                            )
                            session.add(protocol)
                            session.commit()
            except Exception:
                logger.exception(
                    "Failed to update protocol status after persist failure"
                )

            return {"error": f"Persist node failed: {e}"}
