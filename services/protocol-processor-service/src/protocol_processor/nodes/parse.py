"""Parse node: persist CriteriaBatch and Criteria records from extraction JSON.

This node:
1. Parses extraction_json into ExtractionResult Pydantic model
2. Creates CriteriaBatch and Criteria DB records
3. Builds entities_json for the ground node
4. Clears pdf_bytes from state (size optimization)

IMPORTANT: This node does NOT publish a CriteriaExtracted outbox event.
Per PIPE-03: criteria_extracted outbox removed. The pipeline continues
directly to the ground node in a single unified pass.

Architecture note: Graph nodes are integration glue and ARE allowed to import
from api-service for database access. Cross-service imports are intentional
for workflow orchestration nodes.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from api_service.storage import engine
from shared.models import Criteria, CriteriaBatch, Protocol
from sqlmodel import Session

from protocol_processor.schemas.extraction import ExtractionResult
from protocol_processor.state import PipelineState

logger = logging.getLogger(__name__)


async def parse_node(state: PipelineState) -> dict[str, Any]:
    """Persist extraction results to DB and prepare entities for grounding.

    Parses extraction_json, creates CriteriaBatch and Criteria records,
    then builds entities_json containing the data needed by the ground node.
    Clears pdf_bytes from state after extraction to reduce state size.

    Args:
        state: Current pipeline state with extraction_json and protocol_id.

    Returns:
        Dict with batch_id, entities_json, and pdf_bytes=None,
        or error dict on failure.
    """
    if state.get("error"):
        return {}

    try:
        extraction_json = state.get("extraction_json")
        if not extraction_json:
            return {
                "error": "No extraction_json in state — extract node may have failed"
            }

        # Parse extraction JSON into Pydantic model
        extraction_result = ExtractionResult.model_validate_json(extraction_json)

        extraction_model = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")

        with Session(engine) as session:
            # Create CriteriaBatch
            batch = CriteriaBatch(
                protocol_id=state["protocol_id"],
                status="pending_review",
                extraction_model=extraction_model,
            )
            session.add(batch)
            session.flush()  # Get batch.id

            # Create Criteria records and collect entity data
            entity_items: list[dict[str, Any]] = []
            for extracted in extraction_result.criteria:
                raw = extracted.model_dump()
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
                    page_number=raw.get("page_number"),
                )
                session.add(criterion)
                session.flush()  # Get criterion.id

                # Map category to entity_type for TerminologyRouter
                category = raw.get("category", "")
                known_types = {
                    "Medication", "Condition", "Lab_Value",
                    "Biomarker", "Procedure",
                }
                entity_type = (
                    category if category in known_types
                    else "Condition"
                )

                # Collect entity-relevant data for the ground node
                entity_items.append({
                    "criterion_id": criterion.id,
                    "text": raw["text"],
                    "criteria_type": raw["criteria_type"],
                    "category": raw.get("category"),
                    "entity_type": entity_type,
                })

            # Update protocol status to 'processing' (not 'extracted' — grounding
            # happens in the same pipeline, full status set by persist node)
            protocol = session.get(Protocol, state["protocol_id"])
            if protocol:
                protocol.status = "grounding"
                session.add(protocol)

            session.commit()

            # Capture batch_id before session closes (avoids DetachedInstanceError)
            batch_id = batch.id

        logger.info(
            "Parsed and persisted CriteriaBatch %s with %d criteria for protocol %s",
            batch_id,
            len(entity_items),
            state["protocol_id"],
        )

        # Build entities_json for the ground node
        entities_json = json.dumps(entity_items)

        # Return batch_id, entities_json, and clear pdf_bytes (state size optimization)
        return {
            "batch_id": batch_id,
            "entities_json": entities_json,
            "pdf_bytes": None,  # Clear pdf_bytes — no longer needed after extraction
        }

    except Exception as e:
        logger.exception(
            "Parse failed for protocol %s: %s",
            state.get("protocol_id", "unknown"),
            e,
        )
        return {"error": f"Parse failed: {e}"}
