"""FastAPI router for terminology search proxy endpoints.

Provides REST API endpoints that wrap the terminology HTTP clients
(RxNorm, ICD-10, LOINC, HPO) for frontend autocomplete consumption.

Each endpoint follows the same pattern as umls_search.py:
- GET /api/terminology/{system}/search?q={query}&max_results=5
- Returns: { "results": [{ "code", "display", "system", "confidence" }] }

Clients are lazily-initialised singletons — one client per system per
process lifecycle to avoid creating new HTTP clients per request.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, HTTPException, Query
from grounding_service.terminology import (
    BaseTerminologyClient,
    HpoClient,
    Icd10Client,
    LoincClient,
    RxNormClient,
    TerminologyResult,
)
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/terminology", tags=["terminology"])

_C = TypeVar("_C", bound=BaseTerminologyClient)


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class TerminologyResultResponse(BaseModel):
    """Response model for a single terminology search result."""

    code: str
    display: str
    system: str
    confidence: float


class TerminologySearchResponse(BaseModel):
    """Wrapper response model for terminology search results."""

    results: list[TerminologyResultResponse]


# ---------------------------------------------------------------------------
# Singleton clients (lazy-initialised on first request)
# ---------------------------------------------------------------------------

_rxnorm_client: RxNormClient | None = None
_icd10_client: Icd10Client | None = None
_loinc_client: LoincClient | None = None
_hpo_client: HpoClient | None = None


def _get_rxnorm() -> RxNormClient:
    """Return or initialise the singleton RxNorm client."""
    global _rxnorm_client
    if _rxnorm_client is None:
        _rxnorm_client = RxNormClient()
    return _rxnorm_client


def _get_icd10() -> Icd10Client:
    """Return or initialise the singleton ICD-10 client."""
    global _icd10_client
    if _icd10_client is None:
        _icd10_client = Icd10Client()
    return _icd10_client


def _get_loinc() -> LoincClient:
    """Return or initialise the singleton LOINC client."""
    global _loinc_client
    if _loinc_client is None:
        _loinc_client = LoincClient()
    return _loinc_client


def _get_hpo() -> HpoClient:
    """Return or initialise the singleton HPO client."""
    global _hpo_client
    if _hpo_client is None:
        _hpo_client = HpoClient()
    return _hpo_client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _map_result(r: TerminologyResult) -> TerminologyResultResponse:
    """Map a TerminologyResult to the API response model."""
    return TerminologyResultResponse(
        code=r.code,
        display=r.display,
        system=r.system,
        confidence=r.confidence,
    )


async def _run_search(
    client_getter: Callable[[], BaseTerminologyClient],
    query: str,
    limit: int,
    system_name: str,
) -> TerminologySearchResponse:
    """Execute a terminology search with consistent error handling.

    Args:
        client_getter: Callable that returns the singleton client.
        query: Validated search query string.
        limit: Maximum results to return.
        system_name: Human-readable name for error messages.

    Returns:
        TerminologySearchResponse with matched results.

    Raises:
        HTTPException: 502 if the upstream terminology API fails.
    """
    client = client_getter()
    try:
        results = await client.search(query, limit=limit)
        return TerminologySearchResponse(results=[_map_result(r) for r in results])
    except Exception as exc:
        logger.error(
            "%s search failed for query=%r: %s",
            system_name,
            query,
            exc,
        )
        raise HTTPException(
            status_code=502,
            detail=f"{system_name} API error: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/rxnorm/search", response_model=TerminologySearchResponse)
async def search_rxnorm(
    q: str = Query(..., min_length=3),
    max_results: int = Query(default=5, ge=1, le=20),
) -> TerminologySearchResponse:
    """Search RxNorm for drug/medication concepts.

    Args:
        q: Search query (minimum 3 characters).
        max_results: Maximum results to return (1-20, default 5).

    Returns:
        TerminologySearchResponse with RxNorm code matches.

    Raises:
        HTTPException: 400 if query too short, 502 if RxNorm API fails.
    """
    return await _run_search(_get_rxnorm, q, max_results, "RxNorm")


@router.get("/icd10/search", response_model=TerminologySearchResponse)
async def search_icd10(
    q: str = Query(..., min_length=3),
    max_results: int = Query(default=5, ge=1, le=20),
) -> TerminologySearchResponse:
    """Search ICD-10-CM for diagnosis codes.

    Args:
        q: Search query (minimum 3 characters).
        max_results: Maximum results to return (1-20, default 5).

    Returns:
        TerminologySearchResponse with ICD-10-CM code matches.

    Raises:
        HTTPException: 400 if query too short, 502 if ICD-10 API fails.
    """
    return await _run_search(_get_icd10, q, max_results, "ICD-10-CM")


@router.get("/loinc/search", response_model=TerminologySearchResponse)
async def search_loinc(
    q: str = Query(..., min_length=3),
    max_results: int = Query(default=5, ge=1, le=20),
) -> TerminologySearchResponse:
    """Search LOINC for lab and clinical observation codes.

    Args:
        q: Search query (minimum 3 characters).
        max_results: Maximum results to return (1-20, default 5).

    Returns:
        TerminologySearchResponse with LOINC code matches.

    Raises:
        HTTPException: 400 if query too short, 502 if LOINC API fails.
    """
    return await _run_search(_get_loinc, q, max_results, "LOINC")


@router.get("/hpo/search", response_model=TerminologySearchResponse)
async def search_hpo(
    q: str = Query(..., min_length=3),
    max_results: int = Query(default=5, ge=1, le=20),
) -> TerminologySearchResponse:
    """Search HPO for phenotype and rare disease concepts.

    Args:
        q: Search query (minimum 3 characters).
        max_results: Maximum results to return (1-20, default 5).

    Returns:
        TerminologySearchResponse with HPO term matches.

    Raises:
        HTTPException: 400 if query too short, 502 if HPO API fails.
    """
    return await _run_search(_get_hpo, q, max_results, "HPO")
