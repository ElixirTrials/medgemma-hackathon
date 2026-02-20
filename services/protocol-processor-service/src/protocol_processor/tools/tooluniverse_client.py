"""ToolUniverse client wrapper for terminology system lookups.

Provides a module-level singleton ToolUniverse instance with in-memory TTL
caching for autocomplete and pipeline grounding. Exposes a single
`search_terminology(system, query)` function for all 6 medical terminology
systems: UMLS, SNOMED, ICD-10, LOINC, RxNorm, HPO.

Architecture:
- Singleton via @lru_cache(maxsize=1) on _get_tu()
- Two-layer cache: exact-match TTLCache + prefix-aware autocomplete cache
- Selective tool loading (5 categories, ~18 tools) rather than all 1495
- Response parsing handles each system's unique return format
- Retry on transient 502/503 errors (3 attempts, exponential backoff)
- Circuit breaker trips after 10 consecutive failures (60s cooldown)
- Sentence-length queries pre-processed to extract medical terms

Caching strategy for autocomplete:
  Typing "hyp" → "hype" → "hyper" used to make 3 API calls (different keys).
  Now the prefix cache checks: if we already have results for "hyp" and the
  new query "hype" starts with "hyp", we filter the cached "hyp" results
  client-side by checking if preferred_term contains "hype". This avoids
  redundant API calls for progressive typing.

Per user decision: ToolUniverse SDK for all 6 terminology systems (UMLS,
SNOMED, RxNorm, ICD-10, LOINC, HPO) — single SDK, single dependency.

See 40-RESEARCH.md for tool names, response formats, and latency info.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Any

import pybreaker
from cachetools import TTLCache  # type: ignore[import-untyped]
from shared.resilience import tu_breaker
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from tooluniverse import ToolUniverse  # type: ignore[import-untyped]

from protocol_processor.schemas.grounding import GroundingCandidate

logger = logging.getLogger(__name__)


class ToolUniverseError(Exception):
    """ToolUniverse returned an error dict response."""

    pass


class ToolUniverseUnavailableError(ToolUniverseError):
    """Transient 502/503 error — eligible for retry."""

    pass


# Sentence extraction thresholds
_SENTENCE_WORD_THRESHOLD = 4
_SENTENCE_CHAR_THRESHOLD = 40

# Regex to strip clinical preamble from sentence-length queries before search.
# Matches common patterns like "patients must have", "history of", "diagnosis of", etc.
_PREAMBLE_PATTERN = re.compile(
    r"^(?:patient(?:s)?\s+(?:must|should|may|with|who|have|has|had|are|is)\s+"
    r"|(?:has|have|had|is|are|must|should|may)\s+(?:a|an|the|confirmed|known|documented|active|history\s+of)\s+"
    r"|(?:history\s+of|presence\s+of|absence\s+of|diagnosis\s+of)\s+)",
    re.IGNORECASE,
)


def _extract_term_from_sentence(query: str) -> str:
    """Extract medical term from sentence-length query.

    Sentence-length queries (>= 4 words or >= 40 chars) are pre-processed
    to remove clinical preamble before searching. This prevents 422 errors
    from APIs that don't accept full sentences as search terms.

    Args:
        query: Raw query string from user or pipeline.

    Returns:
        Extracted medical term, or original query if it's short.
    """
    stripped = query.strip()
    word_count = len(stripped.split())
    too_short = (
        word_count < _SENTENCE_WORD_THRESHOLD
        or len(stripped) < _SENTENCE_CHAR_THRESHOLD
    )
    if too_short:
        return stripped
    cleaned = _PREAMBLE_PATTERN.sub("", stripped).strip()
    if cleaned and cleaned != stripped and len(cleaned) >= 3:
        logger.debug("Extracted term '%s' from sentence '%s'", cleaned, stripped[:60])
        return cleaned
    # Fallback: take last 4 words as the medical term
    words = stripped.split()
    return " ".join(words[-min(4, len(words)) :])


# Tool categories to load (subset of 1495 total tools — only medical terminology)
_TOOL_CATEGORIES = ["umls", "icd", "loinc", "rxnorm", "hpo"]

# In-memory result cache: (tool_name, normalized_query, max_results) → candidates
# TTL = 300s (5 minutes) — appropriate for autocomplete endpoints
_CACHE: TTLCache = TTLCache(maxsize=1000, ttl=300)

# Tool name per system (verified 2026-02-17 with ToolUniverse 1.0.18)
_SYSTEM_TOOL_MAP: dict[str, str] = {
    "umls": "umls_search_concepts",
    "snomed": "snomed_search_concepts",
    "icd10": "ICD10_search_codes",
    "loinc": "LOINC_search_tests",
    "rxnorm": "RxNorm_get_drug_names",
    "hpo": "HPO_search_terms",
}


@lru_cache(maxsize=1)
def _get_tu() -> ToolUniverse:
    """Get or create singleton ToolUniverse instance.

    lru_cache(maxsize=1) ensures only one ToolUniverse is created per process.
    load_tools() with selective categories takes ~0.002s vs ~0.3s for all tools.

    Returns:
        Initialized ToolUniverse instance with medical terminology tools loaded.
    """
    tu = ToolUniverse()
    tu.load_tools(tool_type=_TOOL_CATEGORIES)
    logger.info("ToolUniverse initialized (categories: %s)", _TOOL_CATEGORIES)
    return tu


def _check_prefix_cache(
    tool_name: str,
    normalized_query: str,
    max_results: int,
) -> list[GroundingCandidate] | None:
    """Check if a shorter (prefix) query is cached and filter its results.

    For autocomplete: if the user typed "hyp" and we cached results, then
    typing "hype" can reuse those results by filtering on preferred_term.

    We only reuse when the cached shorter query returned fewer results than
    max_results (meaning the API exhausted all matches — a longer query
    can only produce a subset) OR when we can filter the cached results
    to find matches containing the longer query.

    Args:
        tool_name: ToolUniverse tool name (cache key component).
        normalized_query: Current query, stripped and lowered.
        max_results: Max results requested.

    Returns:
        Filtered candidate list if a prefix match was found, None otherwise.
    """
    for (cached_tool, cached_query, cached_max), cached_candidates in list(
        _CACHE.items()
    ):
        if cached_tool != tool_name or cached_max != max_results:
            continue
        # Check if cached query is a prefix of the new query
        starts_with = normalized_query.startswith(cached_query)
        is_prefix = starts_with and cached_query != normalized_query
        if not is_prefix:
            continue

        # Filter cached results: keep candidates whose preferred_term
        # contains the longer query (case-insensitive)
        filtered = [
            c for c in cached_candidates if normalized_query in c.preferred_term.lower()
        ]

        # If the original shorter query returned fewer than max_results,
        # the API had no more matches — any longer query is a strict subset.
        # Safe to return the filtered list even if empty.
        if len(cached_candidates) < max_results:
            return filtered

        # If the shorter query returned max_results (truncated), we can still
        # return filtered results if we got some. But if filtered is empty,
        # we can't be sure — there might be results the API would return
        # for the longer query that weren't in the truncated shorter results.
        if filtered:
            return filtered

        # Truncated + no filtered matches → must query the API
        return None

    return None


async def search_terminology(
    system: str,
    query: str,
    max_results: int = 10,
    use_cache: bool = True,
) -> list[GroundingCandidate]:
    """Search a terminology system via ToolUniverse SDK.

    Routes the query to the appropriate ToolUniverse tool for the given system,
    parses the response into GroundingCandidate objects, and caches results.

    Args:
        system: Terminology system to search. One of: umls, snomed, icd10,
            loinc, rxnorm, hpo.
        query: Clinical search term (e.g. "hypertension", "metformin").
        max_results: Maximum number of candidates to return.
        use_cache: Whether to use in-memory TTL cache (default True).
            Set False for pipeline runs that need fresh results.

    Returns:
        List of GroundingCandidate objects. Empty list on any failure
        (missing API key, network error, unknown system, empty results).
    """
    tool_name = _SYSTEM_TOOL_MAP.get(system)
    if not tool_name:
        logger.warning("Unknown terminology system requested: '%s'", system)
        return []

    # Pre-process sentence-length queries to extract medical terms.
    # This prevents 422 errors caused by submitting full sentences to term search APIs.
    query = _extract_term_from_sentence(query)

    normalized_query = query.strip().lower()
    cache_key = (tool_name, normalized_query, max_results)

    if use_cache:
        # Layer 1: exact match
        if cache_key in _CACHE:
            logger.debug("Cache hit (exact) for %s '%s'", system, query)
            return _CACHE[cache_key]

        # Layer 2: prefix match — reuse results from a shorter query
        prefix_result = _check_prefix_cache(tool_name, normalized_query, max_results)
        if prefix_result is not None:
            logger.debug("Cache hit (prefix) for %s '%s'", system, query)
            # Store the filtered result under the exact key too
            _CACHE[cache_key] = prefix_result
            return prefix_result

    tu = _get_tu()
    try:
        raw = await _call_tool_with_resilience(
            tu, system, tool_name, query, max_results
        )
    except pybreaker.CircuitBreakerError:
        logger.warning(
            "Circuit breaker open for ToolUniverse — returning cached/empty for '%s'",
            query,
        )
        # Return cached results if available (TTLCache may still have them)
        if use_cache and cache_key in _CACHE:
            return _CACHE[cache_key]
        return []
    except ToolUniverseError as e:
        logger.warning("ToolUniverse error for '%s': %s", query, e)
        return []
    candidates = _parse_result(system, tool_name, query, raw)

    if use_cache:
        _CACHE[cache_key] = candidates

    logger.debug(
        "ToolUniverse %s for '%s': %d candidates",
        tool_name,
        query,
        len(candidates),
    )
    return candidates


async def _call_tool_raw(
    tu: ToolUniverse,
    system: str,
    tool_name: str,
    query: str,
    max_results: int,
) -> dict[str, Any]:
    """Execute a single ToolUniverse tool call (raw, no retry/circuit breaker).

    Constructs the correct argument dict per system's tool specification
    and calls tu.run(). Returns {} on any exception.

    Args:
        tu: ToolUniverse singleton instance.
        system: System identifier for argument construction.
        tool_name: ToolUniverse tool name to call.
        query: Search term.
        max_results: Max results to request.

    Returns:
        Raw response dict from ToolUniverse, or empty dict on error.
    """
    args: dict[str, Any]
    if system in ("umls", "snomed"):
        args = {"query": query, "pageSize": min(max_results, 25)}
    elif system == "icd10":
        args = {"query": query, "limit": min(max_results, 100)}
    elif system == "loinc":
        args = {"terms": query, "max_results": min(max_results, 20)}
    elif system == "rxnorm":
        args = {"drug_name": query}
    elif system == "hpo":
        args = {"query": query, "max_results": min(max_results, 50)}
    else:
        logger.warning("No argument mapping for system '%s'", system)
        return {}

    try:
        return await tu.run({"name": tool_name, "arguments": args})  # type: ignore[return-value]
    except Exception:
        logger.exception("ToolUniverse %s failed for query '%s'", tool_name, query)
        return {}


@tu_breaker
@retry(
    retry=retry_if_exception_type(ToolUniverseUnavailableError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def _call_tool_with_resilience(
    tu: ToolUniverse,
    system: str,
    tool_name: str,
    query: str,
    max_results: int,
) -> dict[str, Any]:
    """Call ToolUniverse with retry on transient errors and circuit breaker.

    Decorator order: @tu_breaker (outer) wraps @retry (inner). This means
    tenacity retries up to 3 times before counting as 1 circuit breaker failure.

    ToolUniverse SDK catches HTTP exceptions internally and returns error dicts
    instead of raising. This function detects those error dicts and converts
    them to typed exceptions for retry/breaker interception.

    Args:
        tu: ToolUniverse singleton instance.
        system: System identifier for argument construction.
        tool_name: ToolUniverse tool name to call.
        query: Search term (already extracted from sentence if needed).
        max_results: Max results to request.

    Returns:
        Raw response dict from ToolUniverse.

    Raises:
        ToolUniverseUnavailableError: On 502/503/timeout — triggers retry.
        ToolUniverseError: On other non-transient errors — no retry.
    """
    raw = await _call_tool_raw(tu, system, tool_name, query, max_results)

    # Detect error dict: ToolUniverse catches HTTP exceptions internally
    # and returns {"error": "..."} dicts instead of raising.
    if isinstance(raw, dict) and "error" in raw:
        error_msg = str(raw["error"])
        transient_markers = ("502", "503", "Service Unavailable", "timeout", "Timeout")
        if any(s in error_msg for s in transient_markers):
            raise ToolUniverseUnavailableError(f"Transient error: {error_msg}")
        raise ToolUniverseError(f"Non-transient error: {error_msg}")

    return raw


def _parse_result(  # noqa: C901
    system: str,
    tool_name: str,
    query: str,
    raw: dict[str, Any],
) -> list[GroundingCandidate]:
    """Parse ToolUniverse response into GroundingCandidate list.

    Each system returns a different response format. This function handles
    all formats with graceful degradation on unexpected shapes.

    Args:
        system: System identifier for format dispatch.
        tool_name: ToolUniverse tool name (for error logging).
        query: Original query (used as fallback for preferred_term).
        raw: Raw ToolUniverse response dict.

    Returns:
        List of GroundingCandidate objects. Empty on error or no results.
    """
    if not raw:
        return []

    if "error" in raw:
        logger.warning(
            "ToolUniverse %s returned error: %s",
            tool_name,
            raw["error"],
        )
        return []

    candidates: list[GroundingCandidate] = []

    if system in ("umls", "snomed"):
        # UMLSRESTTool: data.result.results[].{ui, name, rootSource}
        # Note: snomed_search_concepts returns UMLS CUIs (not SNOMED codes)
        # rootSource="SNOMEDCT_US" confirms SNOMED provenance.
        results = raw.get("data", {}).get("result", {}).get("results", [])
        for i, r in enumerate(results):
            code = r.get("ui", "")
            if not code or code == "NONE":
                continue
            candidates.append(
                GroundingCandidate(
                    source_api=system,
                    code=code,
                    preferred_term=r.get("name", query),
                    semantic_type=r.get("rootSource"),
                    score=max(1.0 - i * 0.1, 0.5),
                )
            )

    elif system == "icd10":
        # ICD10Tool: data.results[].{code, name}
        results = raw.get("data", {}).get("results", [])
        for i, r in enumerate(results):
            code = r.get("code", "")
            if not code:
                continue
            candidates.append(
                GroundingCandidate(
                    source_api="icd10",
                    code=code,
                    preferred_term=r.get("name", query),
                    semantic_type=None,
                    score=max(1.0 - i * 0.1, 0.5),
                )
            )

    elif system == "loinc":
        # LOINCTool: results[].{code/LOINC_NUM, LONG_COMMON_NAME}
        results = raw.get("results", [])
        for i, r in enumerate(results):
            code = r.get("code") or r.get("LOINC_NUM", "")
            if not code:
                continue
            candidates.append(
                GroundingCandidate(
                    source_api="loinc",
                    code=code,
                    preferred_term=r.get("LONG_COMMON_NAME", query),
                    semantic_type=None,
                    score=max(1.0 - i * 0.1, 0.5),
                )
            )

    elif system == "rxnorm":
        # RxNormTool: single result dict {rxcui, drug_name, names}
        # Returns ONE best match, not a list.
        # RxNorm focuses on specific drug names, not drug classes.
        # Drug class terms (e.g., "beta-blockers", "ACE inhibitors") may return
        # no RXCUI — the TerminologyRouter falls through to UMLS for these.
        rxcui = raw.get("rxcui", "")
        if rxcui:
            candidates.append(
                GroundingCandidate(
                    source_api="rxnorm",
                    code=rxcui,
                    preferred_term=raw.get("drug_name", query),
                    semantic_type=None,
                    score=0.9,
                )
            )

    elif system == "hpo":
        # HPOTool: data[].{id, name, definition}
        results = raw.get("data", [])
        for i, r in enumerate(results):
            code = r.get("id", "")
            if not code:
                continue
            candidates.append(
                GroundingCandidate(
                    source_api="hpo",
                    code=code,
                    preferred_term=r.get("name", query),
                    semantic_type=None,
                    score=max(1.0 - i * 0.1, 0.5),
                )
            )

    return candidates
