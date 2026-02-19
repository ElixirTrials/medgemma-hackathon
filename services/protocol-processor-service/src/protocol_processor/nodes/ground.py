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
- Consent entities skipped explicitly (not groundable to medical codes)
- Demographics routed normally via umls/snomed (age/gender agentic reasoning)
- Agentic retry loop: max 3 attempts, expert_review routing on exhaustion

Architecture note: Graph nodes ARE allowed to import from api-service for DB access.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from api_service.storage import engine
from shared.models import AuditLog
from sqlmodel import Session

from protocol_processor.schemas.grounding import EntityGroundingResult
from protocol_processor.state import PipelineState
from protocol_processor.tools.field_mapper import generate_field_mappings
from protocol_processor.tools.medgemma_decider import (
    agentic_reasoning_loop,
    medgemma_decide,
)
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


async def _ground_entity_with_retry(
    entity: dict[str, Any],
    router: TerminologyRouter,
    criterion_text: str,
) -> EntityGroundingResult:
    """Ground a single entity with agentic retry loop (max 3 attempts).

    Implements the MedGemma agentic reasoning loop:
    1. Initial grounding via TerminologyRouter + MedGemma
    2. If low confidence, ask MedGemma 3 questions (valid? derived? rephrase?)
    3. Retry with reformulated query (up to 2 more attempts, 3 total)
    4. After 3 failed attempts, mark for expert_review

    Args:
        entity: Entity dict with text, entity_type, criterion_id.
        router: TerminologyRouter singleton for API dispatch.
        criterion_text: Full criterion text for context.

    Returns:
        EntityGroundingResult. May have expert_review marker in reasoning.
    """
    entity_text = entity.get("text", "")
    entity_type = entity.get("entity_type", "")

    # Step 1: Route entity through TerminologyRouter to get candidates
    candidates = await router.route_entity(entity_text, entity_type)

    # Log when TerminologyRouter returns empty
    if not candidates:
        apis = router.get_apis_for_entity(entity_type)
        if not apis:
            logger.info(
                "Entity '%s' (type=%s) skipped by TerminologyRouter"
                " — no APIs configured for this type",
                entity_text[:50],
                entity_type,
            )
        else:
            logger.info(
                "Entity '%s' (type=%s) returned zero candidates from all APIs",
                entity_text[:50],
                entity_type,
            )

    # Step 2: MedGemma selects best match from candidates
    result = await medgemma_decide(entity, candidates, criterion_text)

    # Step 3: Agentic retry loop — max 3 attempts total
    attempt = 1
    current_query = entity_text
    while (
        result.selected_code is None
        and result.confidence < 0.5
        and attempt < 3
        and router.get_apis_for_entity(entity_type)
    ):
        attempt += 1
        reasoning_result = await agentic_reasoning_loop(
            entity={**entity, "_previous_query": current_query},
            criterion_context=criterion_text,
            router=router,
            attempt=attempt,
        )

        if reasoning_result.should_skip:
            logger.info(
                "Entity '%s' marked non-medical by agentic reasoning"
                " (attempt %d) — skipping",
                entity_text[:50],
                attempt,
            )
            return EntityGroundingResult(
                entity_text=entity_text,
                entity_type=entity_type,
                selected_code=None,
                selected_system=None,
                preferred_term=None,
                confidence=0.0,
                candidates=[],
                reasoning=(
                    f"Skipped by agentic reasoning (attempt {attempt}): "
                    f"{reasoning_result.reasoning}"
                ),
            )

        new_query = (
            reasoning_result.rephrased_query
            or reasoning_result.derived_term
            or reasoning_result.gemini_suggestion
            or current_query
        )
        current_query = new_query

        logger.info(
            "Agentic retry (attempt %d) for '%s' using query '%s'",
            attempt,
            entity_text[:50],
            new_query[:50],
        )

        new_candidates = await router.route_entity(new_query, entity_type)
        if new_candidates:
            retry_entity = {**entity, "text": new_query}
            result = await medgemma_decide(retry_entity, new_candidates, criterion_text)
            if result.selected_code and result.confidence >= 0.5:
                # Success — preserve original entity_text
                return EntityGroundingResult(
                    entity_text=entity_text,
                    entity_type=result.entity_type,
                    selected_code=result.selected_code,
                    selected_system=result.selected_system,
                    preferred_term=result.preferred_term,
                    confidence=result.confidence,
                    candidates=result.candidates,
                    reasoning=(
                        f"[Attempt {attempt}, query='{new_query}'] {result.reasoning}"
                    ),
                    field_mappings=result.field_mappings,
                )

    # Route to expert_review if all attempts exhausted without success
    if result.selected_code is None and attempt >= 2:
        logger.warning(
            "Entity '%s' (type=%s) routed to expert_review after"
            " %d failed grounding attempts",
            entity_text[:50],
            entity_type,
            attempt,
        )
        return EntityGroundingResult(
            entity_text=result.entity_text,
            entity_type=result.entity_type,
            selected_code=result.selected_code,
            selected_system=result.selected_system,
            preferred_term=result.preferred_term,
            confidence=result.confidence,
            candidates=result.candidates,
            reasoning=(
                f"[expert_review] Routed to expert review after "
                f"{attempt} failed grounding attempts. "
                f"Last reasoning: {result.reasoning}"
            ),
        )

    return result


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
    from protocol_processor.tracing import pipeline_span

    if state.get("error"):
        return {}

    with pipeline_span("ground_node", span_type="TOOL") as span:
        span.set_inputs({"protocol_id": state.get("protocol_id", "")})

        try:
            entities_json = state.get("entities_json")
            if not entities_json:
                span.set_outputs({"error": "No entities_json in state"})
                return {
                    "error": "No entities_json in state — parse node may have failed"
                }

            entity_items: list[dict[str, Any]] = json.loads(entities_json)
            protocol_id = state["protocol_id"]

            span.set_inputs(
                {
                    "protocol_id": protocol_id,
                    "entity_count": len(entity_items),
                }
            )

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
                criterion_text = entity.get("criterion_text") or entity.get("text", "")

                logger.info(
                    "Grounding entity %d/%d: '%s' (type=%s, criterion=%s)",
                    idx,
                    len(entity_items),
                    entity_text[:50],
                    entity_type,
                    criterion_id[:12] if criterion_id else "unknown",
                )

                try:
                    # Consent skip: consent/participation criteria are not groundable
                    if entity_type == "Consent":
                        logger.info(
                            "Entity '%s' (type=Consent) skipped — consent/participation"
                            " criteria are not groundable to terminology codes",
                            entity_text[:50],
                        )
                        result = EntityGroundingResult(
                            entity_text=entity_text,
                            entity_type=entity_type,
                            selected_code=None,
                            selected_system=None,
                            preferred_term=None,
                            confidence=0.0,
                            candidates=[],
                            reasoning=(
                                "Consent/participation criterion — not groundable"
                                " to medical terminology codes"
                            ),
                        )
                        grounding_results.append(result.model_dump())
                        continue

                    # Ground with agentic retry (3 attempts; expert_review on failure)
                    result = await _ground_entity_with_retry(
                        entity, router, criterion_text
                    )

                    # Generate field mappings for this entity
                    field_mappings = await generate_field_mappings(
                        result, criterion_text
                    )
                    result.field_mappings = field_mappings if field_mappings else None

                    # Log grounding decision to AuditLog
                    try:
                        with Session(engine) as session:
                            _log_grounding_audit(
                                session,
                                protocol_id,
                                criterion_id,
                                entity,
                                result.candidates,
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

            span.set_outputs(
                {
                    "grounded_count": len(grounding_results),
                    "error_count": len(accumulated_errors),
                }
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
            span.set_outputs({"error": str(e)})
            return {"error": f"Ground node failed: {e}"}
