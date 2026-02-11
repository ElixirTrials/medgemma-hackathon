"""Ingest node: fetch PDF bytes and parse to markdown.

This node is the first in the extraction graph. It fetches the PDF
from the file_uri (local:// or gs://), parses it to markdown using
pymupdf4llm with diskcache caching, and updates the protocol status
to 'extracting'.

Architecture note: Graph nodes are integration glue and ARE allowed
to import from api-service for database access (e.g., api_service.storage.engine).
This cross-service import is intentional for workflow orchestration nodes.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_a_service.pdf_parser import fetch_pdf_bytes, parse_pdf_to_markdown
from agent_a_service.state import ExtractionState
from api_service.storage import engine
from shared.models import Protocol
from sqlmodel import Session

logger = logging.getLogger(__name__)


async def ingest_node(state: ExtractionState) -> dict[str, Any]:
    """Fetch PDF and parse to markdown, updating protocol status.

    Args:
        state: Current extraction state with protocol_id and file_uri.

    Returns:
        Dict with markdown_content, or error dict on failure.
    """
    if state.get("error"):
        return {}

    try:
        pdf_bytes = fetch_pdf_bytes(state["file_uri"])
        md_text = parse_pdf_to_markdown(
            pdf_bytes,
            cache_key=state["protocol_id"],
        )

        # Update protocol status to 'extracting'
        with Session(engine) as session:
            protocol = session.get(Protocol, state["protocol_id"])
            if protocol:
                protocol.status = "extracting"
                session.add(protocol)
                session.commit()

        logger.info(
            "Ingested protocol %s: %d chars of markdown",
            state["protocol_id"],
            len(md_text),
        )
        return {"markdown_content": md_text}

    except Exception as e:
        logger.exception(
            "Ingestion failed for protocol %s: %s",
            state.get("protocol_id", "unknown"),
            e,
        )
        return {"error": f"Ingestion failed: {e}"}
