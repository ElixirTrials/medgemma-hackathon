"""OMOP vocabulary mapper: look up standard OMOP concept_ids for medical entities.

Queries Athena vocabulary tables (concept, concept_synonym) in a dedicated
OMOP vocabulary database. Requires OMOP_VOCAB_URL environment variable
pointing to a Postgres instance with loaded Athena vocabulary data.

This tool provides the OMOP grounding leg of the dual-grounding pipeline:
- TerminologyRouter provides UMLS/SNOMED/RxNorm/ICD-10/LOINC/HPO codes
- OmopMapper provides OMOP standard concept_ids for CIRCE export and CDM joins

Connection: Uses a dedicated SQLAlchemy engine created from OMOP_VOCAB_URL.
This is separate from the main app database (DATABASE_URL). If OMOP_VOCAB_URL
is not set, lookup_omop_concept raises RuntimeError — callers must handle this
explicitly rather than silently receiving empty results.

All DB I/O is synchronous SQLAlchemy wrapped in run_in_executor for async
compatibility.
"""

from __future__ import annotations

import asyncio
import logging
import os
from difflib import SequenceMatcher
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OMOP_MIN_MATCH_SCORE: float = 0.3
"""Minimum fuzzy-match score to accept a candidate. Below this, return None."""

OMOP_MAX_CANDIDATES: int = 50
"""Maximum number of rows to fetch from each SQL query (LIMIT clause)."""

# ---------------------------------------------------------------------------
# Dedicated OMOP vocabulary engine (lazy singleton)
# ---------------------------------------------------------------------------

_omop_engine: Any = None


def _get_omop_engine() -> Any:
    """Return the OMOP vocabulary SQLAlchemy engine.

    Creates a dedicated engine from OMOP_VOCAB_URL on first call.
    Raises RuntimeError if the env var is not set — callers must
    handle this rather than silently degrading.
    """
    global _omop_engine  # noqa: PLW0603
    if _omop_engine is not None:
        return _omop_engine

    omop_url = os.getenv("OMOP_VOCAB_URL")
    if not omop_url:
        raise RuntimeError(
            "OMOP_VOCAB_URL environment variable is not set. "
            "Set it to the OMOP vocabulary Postgres connection string "
            "(e.g. postgresql://postgres:postgres@localhost:5433/omop_vocab) "
            "or start the omop-vocab container: "
            "docker compose -f infra/docker-compose.yml --profile omop up -d"
        )

    _omop_engine = create_engine(omop_url, pool_pre_ping=True)
    logger.info("OMOP vocabulary engine created: %s", omop_url.split("@")[-1])
    return _omop_engine


# ---------------------------------------------------------------------------
# Entity type -> OMOP domain mapping
# ---------------------------------------------------------------------------

ENTITY_TYPE_TO_OMOP_DOMAIN: dict[str, str] = {
    "Condition": "Condition",
    "Medication": "Drug",
    "Lab_Value": "Measurement",
    "Procedure": "Procedure",
    "Demographic": "Observation",
}
"""Map pipeline entity types to OMOP CDM domain_id values (legacy single-domain).

Demographic is a catch-all routed to Observation. Entity types not present
here will fall back to Observation as well.
"""

ENTITY_TYPE_TO_OMOP_DOMAINS: dict[str, list[str]] = {
    "Condition": ["Condition", "Observation"],
    "Medication": ["Drug"],
    "Lab_Value": ["Measurement", "Observation"],
    "Procedure": ["Procedure", "Observation"],
    "Demographic": ["Observation", "Measurement"],
}
"""Map pipeline entity types to OMOP CDM domain_id values (multi-domain).

Primary domain is first in the list. Fallback domains follow.
Candidates from the primary domain receive a small scoring bonus.
"""

PRIMARY_DOMAIN_BONUS: float = 0.05
"""Small scoring bonus applied to candidates from the primary (first) domain."""

# ---------------------------------------------------------------------------
# Result schema
# ---------------------------------------------------------------------------


class OmopLookupResult(BaseModel):
    """Result of an OMOP vocabulary lookup for a single entity.

    Attributes:
        omop_concept_id: Matched OMOP concept_id as a string, or None.
        omop_concept_name: Matched concept_name from the vocabulary, or None.
        omop_vocabulary_id: Vocabulary source of the match (e.g. SNOMED, RxNorm).
        omop_domain_id: OMOP domain_id of the matched concept.
        match_score: Fuzzy similarity score between 0.0 and 1.0.
        match_method: How the match was found: "concept_name" or "synonym".
    """

    omop_concept_id: str | None = Field(
        default=None,
        description=("Matched OMOP concept_id as a string, or None if no match."),
    )
    omop_concept_name: str | None = Field(
        default=None,
        description="Matched concept_name from the OMOP vocabulary.",
    )
    omop_vocabulary_id: str | None = Field(
        default=None,
        description=("Vocabulary source of the match (e.g. 'SNOMED', 'RxNorm')."),
    )
    omop_domain_id: str | None = Field(
        default=None,
        description="OMOP domain_id of the matched concept.",
    )
    match_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Fuzzy similarity score between 0.0 and 1.0.",
    )
    match_method: str = Field(
        default="",
        description='How the match was found: "concept_name" or "synonym".',
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _score_candidates(
    entity_text: str, candidates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Score and sort candidates by fuzzy string similarity to *entity_text*.

    Uses ``difflib.SequenceMatcher`` ratio as the base score, with a bonus
    for exact case-insensitive substring containment.

    Args:
        entity_text: The original entity text to match against.
        candidates: List of candidate dicts, each with at least a
            ``"match_text"`` key containing the string to compare.

    Returns:
        The same candidate dicts augmented with a ``"score"`` key, sorted
        in descending order of score.
    """
    entity_lower = entity_text.lower().strip()

    for candidate in candidates:
        match_text = candidate.get("match_text", "").lower().strip()

        # Base score: SequenceMatcher ratio
        base_score = SequenceMatcher(None, entity_lower, match_text).ratio()

        # Bonus for exact substring containment (either direction)
        bonus = 0.0
        if entity_lower in match_text or match_text in entity_lower:
            bonus = 0.15

        # Bonus for exact match
        if entity_lower == match_text:
            bonus = 0.25

        candidate["score"] = min(base_score + bonus, 1.0)

    # Sort by score desc, then by length similarity (prefer match_text
    # closest in length to entity_text) as tiebreaker.
    entity_len = len(entity_lower)

    def _sort_key(c: dict[str, Any]) -> tuple[float, int]:
        match_len = len(c.get("match_text", "").strip())
        return (c["score"], -abs(match_len - entity_len))

    candidates.sort(key=_sort_key, reverse=True)
    return candidates


def _get_domain_filter(entity_type: str) -> str:
    """Resolve entity type to an OMOP domain_id filter value.

    Falls back to ``"Observation"`` for unknown entity types.

    Args:
        entity_type: Pipeline entity type (e.g. "Condition", "Medication").

    Returns:
        OMOP domain_id string.
    """
    domain = ENTITY_TYPE_TO_OMOP_DOMAIN.get(entity_type, "Observation")
    if entity_type not in ENTITY_TYPE_TO_OMOP_DOMAIN:
        logger.info(
            "Entity type '%s' not in OMOP domain map — defaulting to '%s'",
            entity_type,
            domain,
        )
    return domain


def _get_domain_filters(entity_type: str) -> list[str]:
    """Resolve entity type to a list of OMOP domain_id filter values.

    Returns primary + fallback domains. The first domain in the list
    is the primary domain (candidates from it receive a scoring bonus).
    Falls back to ``["Observation"]`` for unknown entity types.

    Args:
        entity_type: Pipeline entity type (e.g. "Condition", "Medication").

    Returns:
        List of OMOP domain_id strings, primary first.
    """
    domains = ENTITY_TYPE_TO_OMOP_DOMAINS.get(entity_type)
    if domains is not None:
        return domains
    logger.info(
        "Entity type '%s' not in OMOP multi-domain map — defaulting to ['Observation']",
        entity_type,
    )
    return ["Observation"]


def _query_concept_table(
    engine: Any, entity_text: str, domain_ids: list[str]
) -> list[dict[str, Any]]:
    """Query concept table for standard concepts matching *entity_text*.

    Args:
        engine: SQLAlchemy engine for the OMOP vocabulary database.
        entity_text: Text to search for (used in ILIKE pattern).
        domain_ids: List of OMOP domain_id values to filter on.

    Returns:
        List of candidate dicts with keys: concept_id, concept_name,
        domain_id, vocabulary_id, match_text, match_method.
    """
    # Build parameterized IN clause for domain_ids
    domain_params = {f"d{i}": d for i, d in enumerate(domain_ids)}
    domain_placeholders = ", ".join(f":d{i}" for i in range(len(domain_ids)))

    sql = text(
        "SELECT concept_id, concept_name, domain_id, vocabulary_id "
        "FROM concept "
        "WHERE standard_concept = 'S' "
        f"  AND domain_id IN ({domain_placeholders}) "
        "  AND concept_name ILIKE :pattern "
        "ORDER BY length(concept_name) ASC "
        "LIMIT :max_candidates"
    )
    pattern = f"%{entity_text}%"
    params = {
        **domain_params,
        "pattern": pattern,
        "max_candidates": OMOP_MAX_CANDIDATES,
    }
    with engine.connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    candidates: list[dict[str, Any]] = []
    for row in rows:
        candidates.append(
            {
                "concept_id": str(row[0]),
                "concept_name": row[1],
                "domain_id": row[2],
                "vocabulary_id": row[3],
                "match_text": row[1],
                "match_method": "concept_name",
            }
        )
    return candidates


def _query_synonym_table(
    engine: Any,
    entity_text: str,
    domain_ids: list[str],
    *,
    skip_domain_filter: bool = False,
) -> list[dict[str, Any]]:
    """Query concept_synonym joined with concept for synonym matches.

    Args:
        engine: SQLAlchemy engine for the OMOP vocabulary database.
        entity_text: Text to search for (used in ILIKE pattern).
        domain_ids: List of OMOP domain_id values to filter on.
        skip_domain_filter: If True, search across ALL domains (used for
            acronym lookups where the domain may be ambiguous).

    Returns:
        List of candidate dicts with keys: concept_id, concept_name,
        domain_id, vocabulary_id, match_text, match_method.
    """
    pattern = f"%{entity_text}%"

    if skip_domain_filter:
        sql = text(
            "SELECT c.concept_id, c.concept_name, c.domain_id, "
            "       c.vocabulary_id, s.concept_synonym_name "
            "FROM concept_synonym s "
            "JOIN concept c ON s.concept_id = c.concept_id "
            "WHERE c.standard_concept = 'S' "
            "  AND s.concept_synonym_name ILIKE :pattern "
            "ORDER BY length(s.concept_synonym_name) ASC "
            "LIMIT :max_candidates"
        )
        params: dict[str, Any] = {
            "pattern": pattern,
            "max_candidates": OMOP_MAX_CANDIDATES,
        }
    else:
        domain_params = {f"d{i}": d for i, d in enumerate(domain_ids)}
        domain_placeholders = ", ".join(f":d{i}" for i in range(len(domain_ids)))
        sql = text(
            "SELECT c.concept_id, c.concept_name, c.domain_id, "
            "       c.vocabulary_id, s.concept_synonym_name "
            "FROM concept_synonym s "
            "JOIN concept c ON s.concept_id = c.concept_id "
            "WHERE c.standard_concept = 'S' "
            f"  AND c.domain_id IN ({domain_placeholders}) "
            "  AND s.concept_synonym_name ILIKE :pattern "
            "ORDER BY length(s.concept_synonym_name) ASC "
            "LIMIT :max_candidates"
        )
        params = {
            **domain_params,
            "pattern": pattern,
            "max_candidates": OMOP_MAX_CANDIDATES,
        }

    with engine.connect() as conn:
        rows = conn.execute(sql, params).fetchall()

    candidates: list[dict[str, Any]] = []
    for row in rows:
        candidates.append(
            {
                "concept_id": str(row[0]),
                "concept_name": row[1],
                "domain_id": row[2],
                "vocabulary_id": row[3],
                "match_text": row[4],  # synonym name used for scoring
                "match_method": "synonym",
            }
        )
    return candidates


def _sync_lookup(
    entity_text: str,
    domain_ids: list[str],
    *,
    is_acronym: bool = False,
) -> OmopLookupResult:
    """Synchronous OMOP lookup — runs inside run_in_executor.

    Queries both concept and concept_synonym tables, deduplicates
    candidates by concept_id (preferring concept_name match), scores them,
    and returns the best match above the threshold.

    Args:
        entity_text: The entity text to look up.
        domain_ids: List of OMOP domain_id values to filter on.
            The first domain is considered "primary" and gets a scoring bonus.
        is_acronym: If True, skip domain filter for synonym search
            (acronyms may appear in any OMOP domain).

    Returns:
        OmopLookupResult with best match, or empty result if nothing found
        or all candidates score below OMOP_MIN_MATCH_SCORE.

    Raises:
        RuntimeError: If OMOP_VOCAB_URL is not configured.
        Exception: Database errors are propagated, not swallowed.
    """
    engine = _get_omop_engine()

    concept_candidates = _query_concept_table(engine, entity_text, domain_ids)
    synonym_candidates = _query_synonym_table(
        engine,
        entity_text,
        domain_ids,
        skip_domain_filter=is_acronym,
    )

    # Deduplicate by concept_id — prefer concept_name match over synonym
    seen: dict[str, dict[str, Any]] = {}
    for candidate in concept_candidates:
        seen[candidate["concept_id"]] = candidate
    for candidate in synonym_candidates:
        if candidate["concept_id"] not in seen:
            seen[candidate["concept_id"]] = candidate

    all_candidates = list(seen.values())

    if not all_candidates:
        logger.debug(
            "No OMOP candidates found for '%s' in domains %s",
            entity_text[:50],
            domain_ids,
        )
        return OmopLookupResult()

    # Score and sort
    scored = _score_candidates(entity_text, all_candidates)

    # Apply primary domain bonus
    primary_domain = domain_ids[0] if domain_ids else None
    if primary_domain:
        for candidate in scored:
            if candidate.get("domain_id") == primary_domain:
                candidate["score"] = min(candidate["score"] + PRIMARY_DOMAIN_BONUS, 1.0)
        # Re-sort after bonus
        scored.sort(key=lambda c: c["score"], reverse=True)

    best = scored[0]

    if best["score"] < OMOP_MIN_MATCH_SCORE:
        logger.debug(
            "Best OMOP candidate for '%s' scored %.3f "
            "(below threshold %.2f) — skipping",
            entity_text[:50],
            best["score"],
            OMOP_MIN_MATCH_SCORE,
        )
        return OmopLookupResult()

    logger.info(
        "OMOP match for '%s': concept_id=%s, name='%s', score=%.3f, method=%s",
        entity_text[:50],
        best["concept_id"],
        best["concept_name"][:60],
        best["score"],
        best["match_method"],
    )

    return OmopLookupResult(
        omop_concept_id=best["concept_id"],
        omop_concept_name=best["concept_name"],
        omop_vocabulary_id=best["vocabulary_id"],
        omop_domain_id=best["domain_id"],
        match_score=best["score"],
        match_method=best["match_method"],
    )


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Unit / value / ordinal DB lookups (used by unit_normalizer)
# ---------------------------------------------------------------------------


def _lookup_ucum_unit(engine: Any, unit_text: str) -> tuple[str | None, int | None]:
    """Query concept + concept_synonym where vocabulary_id='UCUM'.

    Searches for *unit_text* (case-insensitive) in both concept_name and
    concept_synonym_name within UCUM vocabulary. Returns the best match.

    Args:
        engine: SQLAlchemy engine for the OMOP vocabulary database.
        unit_text: Raw unit string (e.g. "mg/dL", "years", "%").

    Returns:
        (ucum_code, omop_concept_id) or (None, None) if not found.
    """
    key = unit_text.strip()
    if not key:
        return (None, None)

    # Try exact concept_name match first (fastest path)
    sql_exact = text(
        "SELECT concept_id, concept_name "
        "FROM concept "
        "WHERE vocabulary_id = 'UCUM' "
        "  AND standard_concept = 'S' "
        "  AND LOWER(concept_name) = LOWER(:unit_text) "
        "LIMIT 1"
    )
    with engine.connect() as conn:
        row = conn.execute(sql_exact, {"unit_text": key}).fetchone()
        if row is not None:
            return (row[1], int(row[0]))

        # Try synonym match
        sql_syn = text(
            "SELECT c.concept_id, c.concept_name "
            "FROM concept_synonym s "
            "JOIN concept c ON s.concept_id = c.concept_id "
            "WHERE c.vocabulary_id = 'UCUM' "
            "  AND c.standard_concept = 'S' "
            "  AND LOWER(s.concept_synonym_name) = LOWER(:unit_text) "
            "LIMIT 1"
        )
        row = conn.execute(sql_syn, {"unit_text": key}).fetchone()
        if row is not None:
            return (row[1], int(row[0]))

    return (None, None)


def _lookup_value_concept(
    engine: Any, value_text: str
) -> tuple[str | None, int | None]:
    """Query concept where domain_id='Meas Value' for SNOMED qualifiers.

    Searches for categorical value terms like "positive", "negative",
    "normal", "abnormal" in the Meas Value domain.

    Args:
        engine: SQLAlchemy engine for the OMOP vocabulary database.
        value_text: Raw value text (e.g. "positive", "absent").

    Returns:
        (normalized_text, omop_concept_id) or (None, None) if not found.
    """
    key = value_text.strip()
    if not key:
        return (None, None)

    sql = text(
        "SELECT concept_id, concept_name "
        "FROM concept "
        "WHERE domain_id = 'Meas Value' "
        "  AND standard_concept = 'S' "
        "  AND LOWER(concept_name) = LOWER(:value_text) "
        "LIMIT 1"
    )
    with engine.connect() as conn:
        row = conn.execute(sql, {"value_text": key}).fetchone()
        if row is not None:
            return (row[1].lower(), int(row[0]))

        # Try synonym match
        sql_syn = text(
            "SELECT c.concept_id, c.concept_name "
            "FROM concept_synonym s "
            "JOIN concept c ON s.concept_id = c.concept_id "
            "WHERE c.domain_id = 'Meas Value' "
            "  AND c.standard_concept = 'S' "
            "  AND LOWER(s.concept_synonym_name) = LOWER(:value_text) "
            "LIMIT 1"
        )
        row = conn.execute(sql_syn, {"value_text": key}).fetchone()
        if row is not None:
            return (row[1].lower(), int(row[0]))

    return (None, None)


def _lookup_ordinal_concept(engine: Any, scale_name: str, grade: str) -> int | None:
    """Query concept + concept_synonym for a scale+grade combination.

    Searches for ordinal scale values (e.g. "ECOG 2", "NYHA class III")
    in the OMOP vocabulary.

    Args:
        engine: SQLAlchemy engine for the OMOP vocabulary database.
        scale_name: Canonical scale name (e.g. "ecog", "karnofsky").
        grade: Grade/level value (e.g. "2", "80").

    Returns:
        omop_concept_id or None if not found.
    """
    # Build search patterns for the scale + grade combo
    patterns = [
        f"{scale_name} {grade}",
        f"{scale_name} grade {grade}",
        f"{scale_name} performance status {grade}",
        f"{scale_name} score {grade}",
        f"{scale_name} class {grade}",
    ]

    for pattern in patterns:
        sql = text(
            "SELECT c.concept_id "
            "FROM concept c "
            "WHERE c.standard_concept = 'S' "
            "  AND LOWER(c.concept_name) LIKE LOWER(:pattern) "
            "LIMIT 1"
        )
        with engine.connect() as conn:
            row = conn.execute(sql, {"pattern": f"%{pattern}%"}).fetchone()
            if row is not None:
                return int(row[0])

        # Try synonyms
        sql_syn = text(
            "SELECT c.concept_id "
            "FROM concept_synonym s "
            "JOIN concept c ON s.concept_id = c.concept_id "
            "WHERE c.standard_concept = 'S' "
            "  AND LOWER(s.concept_synonym_name) LIKE LOWER(:pattern) "
            "LIMIT 1"
        )
        with engine.connect() as conn:
            row = conn.execute(sql_syn, {"pattern": f"%{pattern}%"}).fetchone()
            if row is not None:
                return int(row[0])

    return None


# ---------------------------------------------------------------------------
# Public async API
# ---------------------------------------------------------------------------


async def lookup_omop_concept(
    entity_text: str,
    entity_type: str,
    *,
    is_acronym: bool = False,
) -> OmopLookupResult:
    """Look up the best OMOP standard concept for a medical entity.

    Maps the entity type to OMOP domain filters (primary + fallback),
    queries the concept and concept_synonym tables in the OMOP vocabulary
    database, scores candidates with fuzzy string matching, and returns
    the best result above the minimum similarity threshold.

    The synchronous database I/O is executed in a thread-pool executor to
    avoid blocking the async event loop.

    Requires OMOP_VOCAB_URL to be set. Raises RuntimeError if not configured.

    Args:
        entity_text: The medical entity text to look up (e.g. "metformin",
            "type 2 diabetes mellitus", "hemoglobin A1c").
        entity_type: Pipeline entity type used to determine the OMOP domain
            filter. One of "Condition", "Medication", "Lab_Value",
            "Procedure", "Demographic". Unknown types fall back to
            "Observation".
        is_acronym: If True, skip domain filter for synonym search
            to find acronyms across all OMOP domains.

    Returns:
        OmopLookupResult with the best-matching OMOP concept, or an empty
        result if no match is found above the similarity threshold.

    Raises:
        RuntimeError: If OMOP_VOCAB_URL is not set.
    """
    if not entity_text or not entity_text.strip():
        raise ValueError("Empty entity_text passed to lookup_omop_concept")

    domain_ids = _get_domain_filters(entity_type)

    logger.debug(
        "OMOP lookup: entity='%s', type='%s', domains=%s, acronym=%s",
        entity_text[:50],
        entity_type,
        domain_ids,
        is_acronym,
    )

    result = await asyncio.to_thread(
        _sync_lookup, entity_text, domain_ids, is_acronym=is_acronym
    )

    return result
