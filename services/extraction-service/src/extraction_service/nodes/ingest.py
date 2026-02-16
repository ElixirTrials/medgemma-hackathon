"""Ingest node: fetch PDF bytes.

This node is the first in the extraction graph. It fetches the PDF
from the file_uri (local:// or gs://) and updates the protocol status
to 'extracting'.

Architecture note: Graph nodes are integration glue and ARE allowed
to import from api-service for database access (e.g., api_service.storage.engine).
This cross-service import is intentional for workflow orchestration nodes.
"""

from __future__ import annotations

import logging
from typing import Any

from api_service.storage import engine
from shared.models import Protocol
from sqlmodel import Session

from extraction_service.pdf_fetcher import fetch_pdf_bytes
from extraction_service.state import ExtractionState

logger = logging.getLogger(__name__)


async def ingest_node(state: ExtractionState) -> dict[str, Any]:
    """Fetch PDF bytes and update protocol status.

    Args:
        state: Current extraction state with protocol_id and file_uri.

    Returns:
        Dict with pdf_bytes, or error dict on failure.
    """
    if state.get("error"):
        return {}

    try:
        pdf_bytes = fetch_pdf_bytes(state["file_uri"])

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
        return {"pdf_bytes": pdf_bytes}

    except Exception as e:
        logger.exception(
            "Ingestion failed for protocol %s: %s",
            state.get("protocol_id", "unknown"),
            e,
        )
        return {"error": f"Ingestion failed: {e}"}
