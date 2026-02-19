"""Ordinal resolve node: identify and update unrecognized ordinal scales.

7th pipeline node that runs after structure. Queries AtomicCriterion records
where unit_concept_id IS NULL, value_numeric IS NOT NULL, and unit_text IS NULL
(strong signal for unrecognized ordinal scales). Sends candidates to Gemini
for identification, updates confirmed ordinals with unit_concept_id=8527,
and writes AuditLog proposals for human review.

Error handling: same accumulation pattern as structure node. LLM failures
don't block the pipeline — records stay with unit_concept_id=None.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from api_service.storage import engine
from shared.models import AtomicCriterion, AuditLog, Criteria
from sqlmodel import Session, select

from protocol_processor.state import PipelineState
from protocol_processor.tools.ordinal_resolver import (
    resolve_ordinal_candidates,
)

# Use table columns for SQL expressions so mypy sees ColumnElement, not Python types
_atomic = AtomicCriterion.__table__.c
_criteria = Criteria.__table__.c

logger = logging.getLogger(__name__)


def _extract_entity_text(rec: AtomicCriterion) -> str | None:
    """Extract entity name from an AtomicCriterion record.

    Parses original_text before the relation_operator to get the entity.
    E.g. "Child-Pugh score <= 6 (class A)" -> "Child-Pugh score".

    Args:
        rec: AtomicCriterion record.

    Returns:
        Entity text string, or None if not extractable.
    """
    if rec.original_text and rec.relation_operator:
        parts = rec.original_text.split(rec.relation_operator, 1)
        if parts:
            return str(parts[0].strip())
    return str(rec.original_text.strip()) if rec.original_text else None


def _query_candidates(
    session: Session,
    batch_id: str,
) -> list[AtomicCriterion]:
    """Query AtomicCriterion records that are ordinal candidates.

    Candidates have: unit_concept_id IS NULL, value_numeric IS NOT NULL,
    and unit_text IS NULL. Filtered to the given batch.

    Args:
        session: Active SQLModel session.
        batch_id: Batch to filter by.

    Returns:
        List of matching AtomicCriterion records.
    """
    stmt = (
        select(AtomicCriterion)
        .join(Criteria, _atomic.criterion_id == _criteria.id)
        .where(
            _criteria.batch_id == batch_id,
            _atomic.unit_concept_id.is_(None),
            _atomic.value_numeric.isnot(None),
            _atomic.unit_text.is_(None),
        )
    )
    return list(session.exec(stmt).all())


def _deduplicate_candidates(
    records: list[AtomicCriterion],
) -> list[dict[str, Any]]:
    """Deduplicate candidate records by entity text.

    Args:
        records: AtomicCriterion records.

    Returns:
        Deduplicated list of candidate dicts for the LLM.
    """
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for rec in records:
        entity_text = _extract_entity_text(rec)
        if entity_text and entity_text not in seen:
            seen.add(entity_text)
            unique.append(
                {
                    "entity_text": entity_text,
                    "value_numeric": rec.value_numeric,
                    "relation_operator": rec.relation_operator,
                }
            )
    return unique


async def ordinal_resolve_node(
    state: PipelineState,
) -> dict[str, Any]:
    """Identify unrecognized ordinal scales and update unit_concept_id.

    Args:
        state: Current pipeline state with batch_id and protocol_id.

    Returns:
        State update dict with status, errors, and proposals.
    """
    from protocol_processor.tracing import pipeline_span

    if state.get("error"):
        return {}

    protocol_id = state.get("protocol_id", "")
    with pipeline_span(
        "ordinal_resolve_node",
        protocol_id=protocol_id,
    ) as span:
        span.set_inputs({"protocol_id": protocol_id})

        try:
            batch_id = state.get("batch_id")
            if not batch_id:
                logger.warning(
                    "No batch_id in state for protocol %s — skipping ordinal resolve",
                    protocol_id,
                )
                span.set_outputs(
                    {
                        "status": "completed",
                        "note": "no batch_id",
                    }
                )
                return {"status": "completed"}

            accumulated_errors: list[str] = list(
                state.get("errors") or [],
            )

            with Session(engine) as session:
                result = await _process_batch(
                    session,
                    batch_id,
                    protocol_id,
                )

            span.set_outputs(
                {
                    "status": "completed",
                    **result["metrics"],
                }
            )

            return {
                "status": "completed",
                "errors": accumulated_errors,
                "ordinal_proposals_json": result["proposals_json"],
            }

        except Exception as e:
            logger.exception(
                "Ordinal resolve node failed for protocol %s: %s",
                protocol_id,
                e,
            )
            span.set_outputs({"error": str(e)})
            return {
                "status": "completed",
                "errors": (state.get("errors") or [])
                + [f"Ordinal resolve node failed: {e}"],
            }


async def _process_batch(
    session: Session,
    batch_id: str,
    protocol_id: str,
) -> dict[str, Any]:
    """Process a batch for ordinal resolution.

    Args:
        session: Active SQLModel session.
        batch_id: Batch to process.
        protocol_id: Protocol ID for logging.

    Returns:
        Dict with 'proposals_json' and 'metrics' keys.
    """
    candidate_records = _query_candidates(session, batch_id)

    if not candidate_records:
        logger.info(
            "No ordinal candidates found for protocol %s",
            protocol_id,
        )
        return {
            "proposals_json": None,
            "metrics": {"candidates": 0},
        }

    unique_candidates = _deduplicate_candidates(candidate_records)

    logger.info(
        "Ordinal resolve: %d candidates (%d unique) for protocol %s",
        len(candidate_records),
        len(unique_candidates),
        protocol_id,
    )

    resolution = await resolve_ordinal_candidates(unique_candidates)

    proposals_data: list[dict[str, Any]] = []
    updated_count = 0

    if resolution and resolution.proposals:
        confirmed_entities: set[str] = set()
        for proposal in resolution.proposals:
            confirmed_entities.add(proposal.entity_text)
            proposals_data.append(proposal.model_dump())

        for rec in candidate_records:
            entity_text = _extract_entity_text(rec)
            if entity_text in confirmed_entities:
                rec.unit_concept_id = 8527
                session.add(rec)
                updated_count += 1

    audit = AuditLog(
        event_type="ordinal_scale_proposed",
        actor_id="system:pipeline",
        target_type="criteriabatch",
        target_id=batch_id,
        details={
            "protocol_id": protocol_id,
            "candidates_found": len(candidate_records),
            "unique_entities": len(unique_candidates),
            "proposals": proposals_data,
            "updated_count": updated_count,
        },
    )
    session.add(audit)
    session.commit()

    logger.info(
        "Ordinal resolve complete for protocol %s: "
        "%d candidates, %d updated, %d proposals",
        protocol_id,
        len(candidate_records),
        updated_count,
        len(proposals_data),
    )

    proposals_json = json.dumps(proposals_data) if proposals_data else None

    return {
        "proposals_json": proposals_json,
        "metrics": {
            "candidates": len(candidate_records),
            "updated": updated_count,
            "proposals": len(proposals_data),
        },
    }
