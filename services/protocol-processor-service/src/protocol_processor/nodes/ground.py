"""Ground node: route entities via TerminologyRouter and select with MedGemma.

This node is the fourth in the protocol processing pipeline:
ingest→extract→parse→ground→persist
It implements the delegation pattern: thin orchestration that calls tools.

Per user decisions:
- Error accumulation: entity failures are logged and accumulated, not fatal
- Audit trail: all grounding decisions logged to AuditLog
- TerminologyRouter handles entity-type-aware API routing
- MedGemma selects the best match from candidates
- Field mappings generated per entity for AutoCriteria decomposition
- Demographics skipped explicitly (logged at INFO per GRND-06 pattern)

Architecture note: Graph nodes ARE allowed to import from api-service for DB access.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from api_service.storage import engine
from shared.models import AuditLog
from sqlmodel import Session

from protocol_processor.state import PipelineState
from protocol_processor.tools.field_mapper import generate_field_mappings
from protocol_processor.tools.medgemma_decider import medgemma_decide
from protocol_processor.tools.terminology_router import TerminologyRouter

logger = logging.getLogger(__name__)

# Singleton router instance (loads YAML config once)
_router: TerminologyRouter | None = None


def _get_router() -> TerminologyRouter:
    """Get or create the singleton TerminologyRouter."""
    global _router  # noqa: PLW0603
    if _router is None:
        _router = TerminologyRouter()
    return _router


def _log_grounding_audit(
    session: Session,
    protocol_id: str,
    criterion_id: str,
    entity: dict[str, Any],
    candidates: list[Any],
    result: Any,
) -> None:
    """Create an AuditLog entry for a grounding decision.

    Records full details: entity, all candidates considered, selected code,
    reasoning, and confidence. Provides the audit trail per user decision:
    "All agent exchanges (MedGemma decisions, API calls, routing) are logged."

    Args:
        session: Active SQLModel session.
        protocol_id: Protocol ID for context.
        criterion_id: Criterion ID this entity belongs to.
        entity: Entity dict from entities_json.
        candidates: GroundingCandidate objects from TerminologyRouter.
        result: EntityGroundingResult from medgemma_decide.
    """
    audit = AuditLog(
        event_type="entity_grounded",
        target_type="criteria",
        target_id=criterion_id,
        details={
            "protocol_id": protocol_id,
            "entity_text": result.entity_text,
            "entity_type": result.entity_type,
            "candidate_count": len(candidates),
            "candidates": [
                {
                    "source_api": c.source_api,
                    "code": c.code,
                    "preferred_term": c.preferred_term,
                    "score": c.score,
                }
                for c in candidates
            ],
            "selected_code": result.selected_code,
            "selected_system": result.selected_system,
            "preferred_term": result.preferred_term,
            "confidence": result.confidence,
            "reasoning": result.reasoning,
        },
    )
    session.add(audit)


async def ground_node(state: PipelineState) -> dict[str, Any]:
    """Ground entities via TerminologyRouter + MedGemma.

    Parses entities_json from state, routes each entity through TerminologyRouter
    to get terminology candidates, then passes candidates to medgemma_decide for
    best-match selection. Generates field mappings for each successfully grounded
    entity.

    Error accumulation: individual entity failures are logged and collected in
    errors list. Processing continues with remaining entities. Only a total
    failure to parse entities_json triggers a fatal error.

    Args:
        state: Current pipeline state with entities_json and protocol_id.

    Returns:
        Dict with grounded_entities_json and accumulated errors list,
        or fatal error dict if entities_json cannot be parsed.
    """
    if state.get("error"):
        return {}

    try:
        entities_json = state.get("entities_json")
        if not entities_json:
            return {"error": "No entities_json in state — parse node may have failed"}

        entity_items: list[dict[str, Any]] = json.loads(entities_json)
        protocol_id = state["protocol_id"]

        logger.info(
            "Starting grounding for protocol %s: %d entities",
            protocol_id,
            len(entity_items),
        )

        router = _get_router()
        accumulated_errors: list[str] = list(state.get("errors") or [])
        grounding_results: list[dict[str, Any]] = []

        for idx, entity in enumerate(entity_items, 1):
            entity_text = entity.get("text", "")
            entity_type = entity.get("entity_type", "")
            criterion_id = entity.get("criterion_id", "")
            criterion_text = entity.get("text", "")  # Use criterion text as context

            logger.info(
                "Grounding entity %d/%d: '%s' (type=%s, criterion=%s)",
                idx,
                len(entity_items),
                entity_text[:50],
                entity_type,
                criterion_id[:12] if criterion_id else "unknown",
            )

            try:
                # Step 1: Route entity through TerminologyRouter to get candidates
                candidates = await router.route_entity(entity_text, entity_type)

                # Log explicitly when TerminologyRouter returns empty (GRND-06)
                if not candidates:
                    apis = router.get_apis_for_entity(entity_type)
                    if entity_type == "Demographic" or not apis:
                        logger.info(
                            "Entity '%s' (type=%s) skipped by TerminologyRouter"
                            " — no APIs configured for this type",
                            entity_text[:50],
                            entity_type,
                        )
                    else:
                        logger.info(
                            "Entity '%s' (type=%s) returned zero candidates"
                            " from all APIs",
                            entity_text[:50],
                            entity_type,
                        )

                # Step 2: Pass candidates to MedGemma for best-match selection
                result = await medgemma_decide(entity, candidates, criterion_text)

                # Step 3: Generate field mappings for this entity
                field_mappings = await generate_field_mappings(result, criterion_text)
                result.field_mappings = field_mappings if field_mappings else None

                # Step 4: Log grounding decision to AuditLog
                try:
                    with Session(engine) as session:
                        _log_grounding_audit(
                            session,
                            protocol_id,
                            criterion_id,
                            entity,
                            candidates,
                            result,
                        )
                        session.commit()
                except Exception as audit_error:
                    # Audit log failures should not block grounding
                    logger.warning(
                        "Failed to write AuditLog for entity '%s': %s",
                        entity_text[:50],
                        audit_error,
                    )

                # Collect result
                grounding_results.append(result.model_dump())

                logger.info(
                    "Grounded entity '%s': code=%s, conf=%.2f",
                    entity_text[:50],
                    result.selected_code,
                    result.confidence,
                )

            except Exception as e:
                cid_short = criterion_id[:12] if criterion_id else "unknown"
                error_msg = (
                    f"Entity grounding failed for '{entity_text[:50]}'"
                    f" (criterion={cid_short}): {e}"
                )
                logger.error(error_msg, exc_info=True)
                accumulated_errors.append(error_msg)
                # Continue with remaining entities (error accumulation)
                continue

        logger.info(
            "Ground node complete for protocol %s: %d grounded, %d errors",
            protocol_id,
            len(grounding_results),
            len(accumulated_errors),
        )

        return {
            "grounded_entities_json": json.dumps(grounding_results),
            "errors": accumulated_errors,
        }

    except Exception as e:
        logger.exception(
            "Ground node fatal error for protocol %s: %s",
            state.get("protocol_id", "unknown"),
            e,
        )
        return {"error": f"Ground node failed: {e}"}
