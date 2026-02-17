"""FastAPI router for unified terminology search proxy.

Provides per-system search endpoints for RxNorm, ICD-10, LOINC, HPO, UMLS,
and SNOMED. Used by frontend TerminologyCombobox for autocomplete across all
entity types.

Endpoints:
    GET /api/terminology/{system}/search?q={term}&max_results=5

Supported systems: rxnorm, icd10, loinc, hpo, umls, snomed.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/terminology", tags=["terminology"])

# Valid system identifiers
_VALID_SYSTEMS = {"rxnorm", "icd10", "loinc", "hpo", "umls", "snomed"}

# NLM API URLs
_RXNORM_APPROXIMATE_URL = "https://rxnav.nlm.nih.gov/REST/approximateTerm.json"
_ICD10_SEARCH_URL = "https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search"
_LOINC_SEARCH_URL = "https://clinicaltables.nlm.nih.gov/api/loincs/v3/search"
_HPO_SEARCH_URL = "https://ontology.jax.org/api/hp/search"

# HTTP timeout for NLM API calls
_HTTP_TIMEOUT = 10.0


# --- Response model ---


class TerminologySearchResult(BaseModel):
    """Single result from a terminology system search.

    Attributes:
        code: Terminology code (RxCUI, ICD-10, LOINC, HPO, CUI, or SNOMED code).
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


@router.get("/{system}/search", response_model=list[TerminologySearchResult])
async def search_terminology(
    system: str,
    q: str = Query(..., min_length=3),
    max_results: int = Query(default=5, ge=1, le=20),
) -> list[TerminologySearchResult]:
    """Search a specific terminology system by term.

    Routes to the appropriate NLM REST API or UMLS client based on system.

    Args:
        system: Terminology system to search. One of: rxnorm, icd10, loinc,
            hpo, umls, snomed.
        q: Search query (minimum 3 characters).
        max_results: Maximum number of results to return (1-20, default 5).

    Returns:
        List of TerminologySearchResult objects for the matched concepts.

    Raises:
        HTTPException: 400 if system is invalid or query too short,
            502 if upstream API error, 503 if service not configured.
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
        return await _dispatch_search(system, q, limit)
    except HTTPException:
        raise
    except httpx.TimeoutException as exc:
        logger.error(
            "Terminology API timeout for system=%s query='%s': %s",
            system,
            q,
            exc,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Terminology API timeout for {system}",
        ) from exc
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Terminology API HTTP error for system=%s query='%s': %s %s",
            system,
            q,
            exc.response.status_code,
            exc,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Terminology API error for {system}: {exc.response.status_code}",
        ) from exc
    except Exception as exc:
        logger.error(
            "Unexpected error in terminology search system=%s query='%s': %s",
            system,
            q,
            exc,
        )
        raise HTTPException(
            status_code=502,
            detail=f"Terminology search failed for {system}",
        ) from exc


async def _dispatch_search(
    system: str, q: str, limit: int
) -> list[TerminologySearchResult]:
    """Dispatch to the correct per-system search function.

    Args:
        system: Terminology system name (already validated).
        q: Search query string.
        limit: Maximum number of results.

    Returns:
        List of TerminologySearchResult objects.
    """
    if system == "rxnorm":
        return await _search_rxnorm(q, limit)
    elif system == "icd10":
        return await _search_icd10(q, limit)
    elif system == "loinc":
        return await _search_loinc(q, limit)
    elif system == "hpo":
        return await _search_hpo(q, limit)
    elif system == "umls":
        return await _search_umls(q, limit)
    elif system == "snomed":
        return await _search_snomed(q, limit)
    # Unreachable due to validation in endpoint, but satisfies type checker
    raise HTTPException(status_code=400, detail=f"Unknown system: {system}")


# --- Per-system search implementations ---


async def _search_rxnorm(q: str, limit: int) -> list[TerminologySearchResult]:
    """Search RxNorm via NLM RxNav approximate term API.

    Args:
        q: Search query string.
        limit: Maximum number of results.

    Returns:
        List of TerminologySearchResult with RxCUI codes.
    """
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.get(
            _RXNORM_APPROXIMATE_URL,
            params={"term": q, "maxEntries": str(limit)},
        )
        resp.raise_for_status()
        data = resp.json()

    results: list[TerminologySearchResult] = []
    approx_group = data.get("approximateGroup", {})
    raw_candidates = approx_group.get("candidate", []) or []

    for i, item in enumerate(raw_candidates[:limit]):
        rxcui = item.get("rxcui", "")
        name = item.get("name", q)
        raw_score = float(item.get("score", 0))
        confidence = min(raw_score / 100.0, 1.0) if raw_score > 0 else 0.5

        if rxcui:
            results.append(
                TerminologySearchResult(
                    code=rxcui,
                    display=name,
                    system="rxnorm",
                    confidence=confidence,
                )
            )

    logger.debug("RxNorm search '%s' → %d results", q, len(results))
    return results


async def _search_icd10(q: str, limit: int) -> list[TerminologySearchResult]:
    """Search ICD-10-CM via NLM Clinical Tables API.

    Args:
        q: Search query string.
        limit: Maximum number of results.

    Returns:
        List of TerminologySearchResult with ICD-10 codes.
    """
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.get(
            _ICD10_SEARCH_URL,
            params={"sf": "code,name", "terms": q, "maxList": str(limit)},
        )
        resp.raise_for_status()
        data = resp.json()

    results: list[TerminologySearchResult] = []

    # Response: [total, codes_list, extra, display_strings]
    if not isinstance(data, list) or len(data) < 4:
        logger.debug("ICD-10 API returned unexpected format for '%s'", q)
        return results

    codes_list = data[1] or []
    display_list = data[3] or []

    for i, code_item in enumerate(codes_list[:limit]):
        if not isinstance(code_item, list) or not code_item:
            continue
        code = code_item[0] if code_item else ""
        display = q
        if i < len(display_list) and isinstance(display_list[i], list):
            display = display_list[i][0] if display_list[i] else q

        if code:
            confidence = max(1.0 - i * 0.1, 0.5)
            results.append(
                TerminologySearchResult(
                    code=code,
                    display=display,
                    system="icd10",
                    confidence=confidence,
                )
            )

    logger.debug("ICD-10 search '%s' → %d results", q, len(results))
    return results


async def _search_loinc(q: str, limit: int) -> list[TerminologySearchResult]:
    """Search LOINC via NLM Clinical Tables API.

    Args:
        q: Search query string.
        limit: Maximum number of results.

    Returns:
        List of TerminologySearchResult with LOINC codes.
    """
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.get(
            _LOINC_SEARCH_URL,
            params={
                "sf": "LOINC_NUM,LONG_COMMON_NAME",
                "terms": q,
                "maxList": str(limit),
            },
        )
        resp.raise_for_status()
        data = resp.json()

    results: list[TerminologySearchResult] = []

    # Same format as ICD-10: [total, codes_list, extra, display_strings]
    if not isinstance(data, list) or len(data) < 4:
        logger.debug("LOINC API returned unexpected format for '%s'", q)
        return results

    codes_list = data[1] or []
    display_list = data[3] or []

    for i, code_item in enumerate(codes_list[:limit]):
        if not isinstance(code_item, list) or not code_item:
            continue
        code = code_item[0] if code_item else ""
        display = q
        if i < len(display_list) and isinstance(display_list[i], list):
            display = display_list[i][0] if display_list[i] else q

        if code:
            confidence = max(1.0 - i * 0.1, 0.5)
            results.append(
                TerminologySearchResult(
                    code=code,
                    display=display,
                    system="loinc",
                    confidence=confidence,
                )
            )

    logger.debug("LOINC search '%s' → %d results", q, len(results))
    return results


async def _search_hpo(q: str, limit: int) -> list[TerminologySearchResult]:
    """Search HPO via JAX ontology API.

    Args:
        q: Search query string.
        limit: Maximum number of results.

    Returns:
        List of TerminologySearchResult with HPO codes.
    """
    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
        resp = await client.get(
            _HPO_SEARCH_URL,
            params={"q": q, "max": str(limit)},
        )
        resp.raise_for_status()
        data = resp.json()

    results: list[TerminologySearchResult] = []
    terms = data.get("terms", []) or []

    for i, term in enumerate(terms[:limit]):
        hpo_id = term.get("id", "")
        name = term.get("name", q)
        confidence = max(1.0 - i * 0.1, 0.5)

        if hpo_id:
            results.append(
                TerminologySearchResult(
                    code=hpo_id,
                    display=name,
                    system="hpo",
                    confidence=confidence,
                )
            )

    logger.debug("HPO search '%s' → %d results", q, len(results))
    return results


async def _search_umls(q: str, limit: int) -> list[TerminologySearchResult]:
    """Search UMLS concepts via umls_mcp_server client.

    Delegates to get_umls_client().search_snomed() for UMLS concept search
    with SNOMED codes, using the same path as the existing /api/umls/search.

    Args:
        q: Search query string.
        limit: Maximum number of results.

    Returns:
        List of TerminologySearchResult with UMLS CUI codes.

    Raises:
        HTTPException: 503 if UMLS not configured, 502 on API error.
    """
    from umls_mcp_server.umls_api import (  # type: ignore[import-untyped]
        UmlsApiError,
        get_umls_client,
    )

    try:
        with get_umls_client() as client:
            candidates = client.search_snomed(q, limit=limit)
            results = []
            for c in candidates:
                results.append(
                    TerminologySearchResult(
                        code=c.cui,
                        display=c.display,
                        system="umls",
                        semantic_type=None,
                        confidence=c.confidence,
                    )
                )
            logger.debug("UMLS search '%s' → %d results", q, len(results))
            return results
    except ValueError as exc:
        logger.error("UMLS service not configured: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="UMLS service not configured",
        ) from exc
    except UmlsApiError as exc:
        logger.error("UMLS API error during search: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"UMLS API error: {exc.message}",
        ) from exc


async def _search_snomed(q: str, limit: int) -> list[TerminologySearchResult]:
    """Search SNOMED CT concepts via umls_mcp_server client.

    Uses get_umls_client().search_snomed() which returns SNOMED codes from
    the UMLS SNOMED CT source vocabulary.

    Args:
        q: Search query string.
        limit: Maximum number of results.

    Returns:
        List of TerminologySearchResult with SNOMED codes.

    Raises:
        HTTPException: 503 if UMLS not configured, 502 on API error.
    """
    from umls_mcp_server.umls_api import (  # type: ignore[import-untyped]
        UmlsApiError,
        get_umls_client,
    )

    try:
        with get_umls_client() as client:
            candidates = client.search_snomed(q, limit=limit)
            results = []
            for c in candidates:
                results.append(
                    TerminologySearchResult(
                        code=c.code,
                        display=c.display,
                        system="snomed",
                        semantic_type=None,
                        confidence=c.confidence,
                    )
                )
            logger.debug("SNOMED search '%s' → %d results", q, len(results))
            return results
    except ValueError as exc:
        logger.error("UMLS service not configured for SNOMED search: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="UMLS service not configured",
        ) from exc
    except UmlsApiError as exc:
        logger.error("UMLS API error during SNOMED search: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"UMLS API error: {exc.message}",
        ) from exc
