"""FastAPI router for UMLS search proxy.

Provides a REST API endpoint that wraps the UMLS MCP server's concept_search
functionality for frontend autocomplete consumption.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from umls_mcp_server.umls_api import (
    SnomedCandidate,
    UmlsApiError,
    get_umls_client,
)

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
    """Search UMLS SNOMED concepts by clinical term.

    Args:
        q: Search query (minimum 3 characters).
        max_results: Maximum number of results to return (1-20, default 5).

    Returns:
        List of UMLS concept results with CUI, SNOMED code, preferred term,
        semantic type, and confidence.

    Raises:
        HTTPException: 400 if query too short, 502 if UMLS API error,
            503 if UMLS service not configured.
    """
    # FastAPI Query validator handles min_length, but add explicit check for clarity
    if len(q.strip()) < 3:
        raise HTTPException(
            status_code=400,
            detail="Search query must be at least 3 characters",
        )

    # Clamp max_results to valid range
    limit = max(1, min(max_results, 20))

    try:
        with get_umls_client() as client:
            candidates = client.search_snomed(q, limit=limit)
            return [_map_candidate_to_response(c) for c in candidates]
    except ValueError as exc:
        # Missing API key or configuration
        logger.error("UMLS service not configured: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="UMLS service not configured",
        ) from exc
    except UmlsApiError as exc:
        # UMLS API error (auth, rate limit, server error, etc.)
        logger.error("UMLS API error during search: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"UMLS API error: {exc.message}",
        ) from exc


# --- Helpers ---


def _map_candidate_to_response(candidate: SnomedCandidate) -> UmlsConceptResponse:
    """Map a SnomedCandidate to UmlsConceptResponse.

    The UMLS search API returns ontology field which indicates the source
    (e.g., SNOMEDCT_US). For semantic_type, we use the ontology field value
    or default to "Clinical Finding" since the search endpoint doesn't
    return semantic type directly.
    """
    # Map ontology to semantic type (simplified for now)
    semantic_type = _infer_semantic_type(candidate.ontology)

    return UmlsConceptResponse(
        cui=candidate.cui,
        snomed_code=candidate.code,
        preferred_term=candidate.display,
        semantic_type=semantic_type,
        confidence=candidate.confidence,
    )


def _infer_semantic_type(ontology: str) -> str:
    """Infer semantic type from ontology field.

    The UMLS search API doesn't return semantic type directly, so we
    use the ontology field as a proxy. In practice, SNOMEDCT_US concepts
    can be various types (Clinical Finding, Disease or Syndrome, etc.),
    but we default to "Clinical Finding" as a reasonable fallback.
    """
    # For now, use a simple default since the ontology field doesn't
    # directly indicate semantic type
    return "Clinical Finding"
