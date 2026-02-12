"""Queue node: persist CriteriaBatch and Criteria records to database.

This node is the final step in the extraction graph. It creates a
CriteriaBatch with linked Criteria records from the refined raw_criteria,
publishes a CriteriaExtracted event via the outbox pattern, and updates
the protocol status to 'extracted'.

Architecture note: Graph nodes are integration glue and ARE allowed
to import from api-service for database access (e.g., api_service.storage.engine).
This cross-service import is intentional for workflow orchestration nodes,
unlike utility modules like pdf_parser.py which must stay self-contained.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from api_service.storage import engine
from events_py.models import DomainEventKind
from events_py.outbox import persist_with_outbox
from shared.models import Criteria, CriteriaBatch, Protocol
from sqlmodel import Session

from extraction_service.state import ExtractionState

logger = logging.getLogger(__name__)


async def queue_node(state: ExtractionState) -> dict[str, Any]:
    """Persist extraction results and publish CriteriaExtracted event.

    Creates a CriteriaBatch with status='pending_review', linked Criteria
    records for each extracted criterion, and publishes a CriteriaExtracted
    event via the transactional outbox pattern.

    Args:
        state: Current extraction state with raw_criteria from parse node.

    Returns:
        Dict with criteria_batch_id, or error dict on failure.
    """
    if state.get("error"):
        return {}

    try:
        extraction_model = os.getenv("GEMINI_MODEL_NAME", "gemini-3-flash-preview")

        with Session(engine) as session:
            # Create CriteriaBatch
            batch = CriteriaBatch(
                protocol_id=state["protocol_id"],
                status="pending_review",
                extraction_model=extraction_model,
            )
            session.add(batch)
            session.flush()  # Get batch.id

            # Create Criteria records
            criteria_ids: list[str] = []
            for raw in state.get("raw_criteria", []):
                criterion = Criteria(
                    batch_id=batch.id,
                    criteria_type=raw["criteria_type"],
                    category=raw.get("category"),
                    text=raw["text"],
                    temporal_constraint=raw.get("temporal_constraint"),
                    conditions=raw.get("conditions"),
                    numeric_thresholds=raw.get("numeric_thresholds"),
                    assertion_status=raw.get("assertion_status"),
                    confidence=raw.get("confidence", 1.0),
                    source_section=raw.get("source_section"),
                )
                session.add(criterion)
                session.flush()  # Get criterion.id
                criteria_ids.append(criterion.id)

            # Publish CriteriaExtracted event via outbox
            persist_with_outbox(
                session=session,
                entity=batch,
                event_type=DomainEventKind.CRITERIA_EXTRACTED,
                aggregate_type="criteria_batch",
                aggregate_id=batch.id,
                payload={
                    "batch_id": batch.id,
                    "protocol_id": state["protocol_id"],
                    "criteria_ids": criteria_ids,
                    "criteria_count": len(criteria_ids),
                },
            )

            # Update protocol status to 'extracted'
            protocol = session.get(Protocol, state["protocol_id"])
            if protocol:
                protocol.status = "extracted"
                session.add(protocol)

            session.commit()

            # Capture IDs before session closes (avoids DetachedInstanceError)
            batch_id = batch.id

        logger.info(
            "Queued CriteriaBatch %s with %d criteria for protocol %s",
            batch_id,
            len(criteria_ids),
            state["protocol_id"],
        )
        return {"criteria_batch_id": batch_id}

    except Exception as e:
        logger.exception(
            "Queue failed for protocol %s: %s",
            state.get("protocol_id", "unknown"),
            e,
        )
        return {"error": f"Queue failed: {e}"}
