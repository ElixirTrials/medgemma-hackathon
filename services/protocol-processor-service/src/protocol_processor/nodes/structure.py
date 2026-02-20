"""Structure node: build expression trees from persisted criteria.

Phase 2 pipeline node that runs after persist. Reads criteria from DB,
detects AND/OR/NOT logic via Gemini, creates normalized atomic_criteria/
composite_criteria records, and stores the expression tree JSONB.

Error handling: same accumulation pattern as ground node. Individual
criterion failures don't block others. Uses asyncio.Semaphore(4) for
parallel LLM calls.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from api_service.storage import engine
from shared.models import AuditLog, Criteria
from sqlmodel import Session, select

from protocol_processor.state import PipelineState
from protocol_processor.tools.structure_builder import build_expression_tree

logger = logging.getLogger(__name__)


async def _process_criterion(
    criterion: Criteria,
    protocol_id: str,
    session: Session,
    semaphore: asyncio.Semaphore,
) -> str | None:
    """Process a single criterion: build expression tree and store it.

    Args:
        criterion: Criteria record with non-empty field_mappings.
        protocol_id: Protocol ID for the AtomicCriterion records.
        session: Active SQLModel session.
        semaphore: Concurrency limiter for LLM calls.

    Returns:
        None on success, error message string on failure.
    """
    async with semaphore:
        try:
            conditions = criterion.conditions or {}
            field_mappings = conditions.get("field_mappings", [])

            if not field_mappings:
                return None

            inclusion_exclusion = getattr(criterion, "criteria_type", "inclusion")

            tree = await build_expression_tree(
                criterion_text=criterion.text,
                field_mappings=field_mappings,
                criterion_id=criterion.id,
                protocol_id=protocol_id,
                inclusion_exclusion=inclusion_exclusion,
                session=session,
            )

            criterion.structured_criterion = tree.model_dump()
            session.add(criterion)

            logger.info(
                "Built expression tree for criterion %s (confidence=%s, atoms=%d)",
                criterion.id[:12],
                tree.structure_confidence,
                len(field_mappings),
            )
            return None

        except Exception as e:
            error_msg = f"Structure build failed for criterion {criterion.id[:12]}: {e}"
            logger.error(error_msg, exc_info=True)
            return error_msg


async def structure_node(state: PipelineState) -> dict[str, Any]:
    """Build expression trees for all criteria in the batch.

    Reads persisted criteria from DB (written by persist node), detects
    logic structure, creates normalized table records, and stores the
    expression tree JSONB on each criterion.

    Args:
        state: Current pipeline state with batch_id and protocol_id.

    Returns:
        Dict with status='completed' and accumulated errors list.
    """
    from protocol_processor.tracing import pipeline_span

    if state.get("error"):
        return {}

    protocol_id = state.get("protocol_id", "")
    with pipeline_span("structure_node", protocol_id=protocol_id) as span:
        span.set_inputs({"protocol_id": protocol_id})

        try:
            batch_id = state.get("batch_id")
            if not batch_id:
                logger.warning(
                    "No batch_id in state for protocol %s — skipping structure",
                    protocol_id,
                )
                span.set_outputs({"status": "completed", "note": "no batch_id"})
                return {"status": "completed"}

            accumulated_errors: list[str] = list(state.get("errors") or [])

            with Session(engine) as session:
                # Query criteria with non-empty field_mappings
                stmt = select(Criteria).where(Criteria.batch_id == batch_id)
                all_criteria = session.exec(stmt).all()

                # Filter to criteria with field_mappings in conditions
                qualifying = [
                    c
                    for c in all_criteria
                    if c.conditions
                    and isinstance(c.conditions, dict)
                    and c.conditions.get("field_mappings")
                ]

                logger.info(
                    "Structure node: %d/%d criteria qualify for"
                    " expression tree building (protocol %s)",
                    len(qualifying),
                    len(all_criteria),
                    protocol_id,
                )

                if not qualifying:
                    span.set_outputs(
                        {
                            "status": "completed",
                            "note": "no qualifying criteria",
                        }
                    )
                    return {"status": "completed"}

                # Process criteria with semaphore for LLM concurrency
                semaphore = asyncio.Semaphore(4)
                tasks = [
                    _process_criterion(c, protocol_id, session, semaphore)
                    for c in qualifying
                ]
                results = await asyncio.gather(*tasks)

                # Collect errors
                new_errors = [e for e in results if e is not None]
                accumulated_errors.extend(new_errors)
                error_count = len(new_errors)

                # Write audit log
                audit = AuditLog(
                    event_type="structure_trees_built",
                    actor_id="system:pipeline",
                    target_type="criteriabatch",
                    target_id=batch_id,
                    details={
                        "protocol_id": protocol_id,
                        "criteria_processed": len(qualifying),
                        "errors": error_count,
                    },
                )
                session.add(audit)
                session.commit()

            logger.info(
                "Structure node complete for protocol %s:"
                " %d criteria processed, %d errors",
                protocol_id,
                len(qualifying),
                error_count,
            )

            span.set_outputs(
                {
                    "criteria_processed": len(qualifying),
                    "errors": error_count,
                    "status": "completed",
                }
            )

            return {
                "status": "completed",
                "errors": accumulated_errors,
            }

        except Exception as e:
            logger.exception(
                "Structure node failed for protocol %s: %s",
                protocol_id,
                e,
            )
            span.set_outputs({"error": str(e)})
            return {
                "status": "completed",
                "errors": (state.get("errors") or []) + [f"Structure node failed: {e}"],
            }
