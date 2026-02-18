"""FastAPI router for unified terminology search proxy via ToolUniverse.

Provides per-system search endpoints for RxNorm, ICD-10, LOINC, HPO, UMLS,
and SNOMED. Used by frontend TerminologyCombobox for autocomplete across all
entity types. Results are cached via the TTLCache in the tooluniverse_client
wrapper (5-minute TTL) to reduce autocomplete latency.

Endpoints:
    GET /api/terminology/{system}/search?q={term}&max_results=5

Supported systems: rxnorm, icd10, loinc, hpo, umls, snomed.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from protocol_processor.tools.tooluniverse_client import (
    search_terminology as tu_search,
)
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/terminology", tags=["terminology"])

# Valid system identifiers
_VALID_SYSTEMS = {"rxnorm", "icd10", "loinc", "hpo", "umls", "snomed"}


# --- Response model ---


class TerminologySearchResult(BaseModel):
    """Single result from a terminology system search.

    Attributes:
        code: Terminology code (RxCUI, ICD-10, LOINC, HPO, CUI, or SNOMED CUI).
        display: Preferred term or display name.
        system: Terminology system name.
        semantic_type: UMLS/ontology semantic type, if available.
        confidence: Relevance score from the API (0.0-1.0).
    """

    code: str
    display: str
    system: str
    semantic_type: str | None = None
    confidence: float = 1.0


# --- Endpoint ---


@router.get("/{system}/search")
async def search_terminology(
    system: str,
    q: str = Query(..., min_length=3),
    max_results: int = Query(default=5, ge=1, le=20),
) -> JSONResponse:
    """Search a specific terminology system by term via ToolUniverse.

    Routes to the ToolUniverse SDK for all supported systems. Results are
    cached in the tooluniverse_client TTLCache.

    Args:
        system: Terminology system to search. One of: rxnorm, icd10, loinc,
            hpo, umls, snomed.
        q: Search query (minimum 3 characters).
        max_results: Maximum number of results to return (1-20, default 5).

    Returns:
        List of TerminologySearchResult objects for the matched concepts.

    Raises:
        HTTPException: 400 if system is invalid or query too short,
            502 if ToolUniverse API fails.
    """
    if system not in _VALID_SYSTEMS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Invalid terminology system '{system}'. "
                f"Must be one of: {', '.join(sorted(_VALID_SYSTEMS))}"
            ),
        )

    if len(q.strip()) < 3:
        raise HTTPException(
            status_code=400,
            detail="Search query must be at least 3 characters",
        )

    limit = max(1, min(max_results, 20))

    try:
        candidates = await tu_search(system, q, max_results=limit)
        results = [
            TerminologySearchResult(
                code=c.code,
                display=c.preferred_term,
                system=system,
                semantic_type=c.semantic_type,
                confidence=c.score,
            )
            for c in candidates
        ]
        logger.debug("Terminology search %s '%s' → %d results", system, q, len(results))
        return JSONResponse(
            content=[r.model_dump() for r in results],
            headers={"Cache-Control": "public, max-age=300"},
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Terminology search failed system=%s query='%s': %s",
            system,
            q,
            exc,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Terminology search failed for {system}",
        ) from exc
