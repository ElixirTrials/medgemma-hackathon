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

import asyncio
import json
import logging
import os
from typing import Any

from api_service.storage import engine
from shared.models import Criteria, CriteriaBatch, Protocol
from sqlmodel import Session

from protocol_processor.schemas.extraction import ExtractionResult
from protocol_processor.state import PipelineState
from protocol_processor.tools.entity_decomposer import decompose_entities_from_criterion
from protocol_processor.tracing import pipeline_span

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

    with pipeline_span("parse_node") as span:
        span.set_inputs({"protocol_id": state.get("protocol_id", "")})

        try:
            extraction_json = state.get("extraction_json")
            if not extraction_json:
                span.set_outputs({"error": "No extraction_json in state"})
                return {
                    "error": (
                        "No extraction_json in state — extract node may have failed"
                    )
                }

            # Parse extraction JSON into Pydantic model
            extraction_result = ExtractionResult.model_validate_json(extraction_json)

            extraction_model = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")

            # Phase A: Persist criteria to DB and collect raw data
            criteria_raws: list[dict[str, Any]] = []
            criterion_ids: list[str] = []

            with Session(engine) as session:
                # Create CriteriaBatch
                batch = CriteriaBatch(
                    protocol_id=state["protocol_id"],
                    status="pending_review",
                    extraction_model=extraction_model,
                )
                session.add(batch)
                session.flush()  # Get batch.id

                # Create Criteria records and collect raw data for decomposition
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

                    criteria_raws.append(raw)
                    criterion_ids.append(criterion.id)

                # Update protocol status to 'processing' (not 'extracted' — grounding
                # happens in the same pipeline, full status set by persist node)
                protocol = session.get(Protocol, state["protocol_id"])
                if protocol:
                    protocol.status = "grounding"
                    session.add(protocol)

                session.commit()

                # Capture batch_id before session closes (avoids DetachedInstanceError)
                batch_id = batch.id

            # Phase B: Decompose criteria into discrete medical entities concurrently
            # Runs OUTSIDE DB session — async LLM calls shouldn't hold sessions open
            decompose_tasks = [
                decompose_entities_from_criterion(raw["text"], raw.get("category"))
                for raw in criteria_raws
            ]
            decomposed_results = await asyncio.gather(*decompose_tasks)

            # Build entity_items from decomposition results
            entity_items: list[dict[str, Any]] = []
            for raw, cid, decomposed in zip(
                criteria_raws, criterion_ids, decomposed_results
            ):
                if decomposed:
                    for ent in decomposed:
                        entity_items.append(
                            {
                                "criterion_id": cid,
                                "text": ent["text"],
                                "entity_type": ent["entity_type"],
                                "criterion_text": raw["text"],
                                "criteria_type": raw["criteria_type"],
                            }
                        )
                else:
                    # Fallback: category-based type mapping with full text
                    category = raw.get("category", "")
                    fallback_type = {
                        "medications": "Medication",
                        "lab_values": "Lab_Value",
                        "procedures": "Procedure",
                        "demographics": "Demographic",
                    }.get(category, "Condition")
                    entity_items.append(
                        {
                            "criterion_id": cid,
                            "text": raw["text"],
                            "entity_type": fallback_type,
                            "criterion_text": raw["text"],
                            "criteria_type": raw["criteria_type"],
                        }
                    )

            logger.info(
                "Parsed CriteriaBatch %s: %d criteria -> %d entities for protocol %s",
                batch_id,
                len(criteria_raws),
                len(entity_items),
                state["protocol_id"],
            )

            # Build entities_json for the ground node
            entities_json = json.dumps(entity_items)

            span.set_outputs(
                {
                    "batch_id": batch_id,
                    "criteria_count": len(entity_items),
                }
            )

            # Return batch_id, entities_json; clear pdf_bytes (state size optimization)
            return {
                "batch_id": batch_id,
                "entities_json": entities_json,
                "pdf_bytes": None,  # No longer needed after extraction
            }

        except Exception as e:
            logger.exception(
                "Parse failed for protocol %s: %s",
                state.get("protocol_id", "unknown"),
                e,
            )
            span.set_outputs({"error": str(e)})
            return {"error": f"Parse failed: {e}"}
