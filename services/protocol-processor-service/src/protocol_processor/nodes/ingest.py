"""Ingest node: fetch PDF bytes from GCS or local storage.

This node is the first in the protocol processing graph. It fetches the PDF
from the file_uri (local:// or gs://) and populates state with raw PDF bytes.

Architecture note: Graph nodes are integration glue and ARE allowed to import
from api-service for database access (e.g., api_service.storage.engine).
This cross-service import is intentional for workflow orchestration nodes.
"""

from __future__ import annotations

import logging
from typing import Any

from api_service.storage import engine
from shared.models import Protocol
from sqlmodel import Session

from protocol_processor.state import PipelineState
from protocol_processor.tools.pdf_parser import fetch_pdf_bytes

logger = logging.getLogger(__name__)


async def ingest_node(state: PipelineState) -> dict[str, Any]:
    """Fetch PDF bytes and update protocol status to 'extracting'.

    Delegates PDF fetching to the fetch_pdf_bytes tool. Updates the
    protocol record status to 'extracting' in the database.

    Args:
        state: Current pipeline state with protocol_id, file_uri, and title.

    Returns:
        Dict with pdf_bytes and status="processing", or error dict on failure.
    """
    if state.get("error"):
        return {}

    try:
        pdf_bytes = await fetch_pdf_bytes(state["file_uri"])

        # Update protocol status to 'extracting'
        with Session(engine) as session:
            protocol = session.get(Protocol, state["protocol_id"])
            if protocol:
                protocol.status = "extracting"
                session.add(protocol)
                session.commit()

        logger.info(
            "Ingested protocol %s: %d bytes of PDF",
            state["protocol_id"],
            len(pdf_bytes),
        )
        return {"pdf_bytes": pdf_bytes, "status": "processing"}

    except Exception as e:
        logger.exception(
            "Ingestion failed for protocol %s: %s",
            state.get("protocol_id", "unknown"),
            e,
        )
        return {"error": f"Ingestion failed: {e}", "status": "failed"}
