"""FastAPI router for UMLS search proxy via ToolUniverse.

Provides a REST API endpoint that wraps ToolUniverse-backed UMLS concept search
for frontend autocomplete consumption. Results are cached via the TTLCache in
the tooluniverse_client wrapper (5-minute TTL) to reduce autocomplete latency.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from protocol_processor.tools.tooluniverse_client import search_terminology
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/umls", tags=["umls"])


# --- Response models ---


class UmlsConceptResponse(BaseModel):
    """Response model for a single UMLS concept result."""

    cui: str
    snomed_code: str
    preferred_term: str
    semantic_type: str
    confidence: float


# --- Endpoints ---


@router.get("/search", response_model=list[UmlsConceptResponse])
def search_umls_concepts(
    q: str = Query(..., min_length=3),
    max_results: int = Query(default=5, ge=1, le=20),
) -> list[UmlsConceptResponse]:
    """Search UMLS concepts by clinical term via ToolUniverse.

    Args:
        q: Search query (minimum 3 characters).
        max_results: Maximum number of results to return (1-20, default 5).

    Returns:
        List of UMLS concept results with CUI, preferred term, semantic type,
        and confidence. SNOMED code field is populated with the source API
        root source (e.g. "SNOMEDCT_US") since ToolUniverse UMLS search
        returns CUIs, not SNOMED numeric codes.

    Raises:
        HTTPException: 400 if query too short, 502 if ToolUniverse fails.
    """
    if len(q.strip()) < 3:
        raise HTTPException(
            status_code=400,
            detail="Search query must be at least 3 characters",
        )

    limit = max(1, min(max_results, 20))

    try:
        candidates = search_terminology("umls", q, max_results=limit)
        return [
            UmlsConceptResponse(
                cui=c.code,
                snomed_code=c.semantic_type or "",
                preferred_term=c.preferred_term,
                semantic_type=c.semantic_type or "Clinical Finding",
                confidence=c.score,
            )
            for c in candidates
        ]
    except Exception as exc:
        logger.error("ToolUniverse UMLS search failed for query '%s': %s", q, exc)
        raise HTTPException(
            status_code=502,
            detail=f"Terminology lookup failed: {exc}",
        ) from exc
