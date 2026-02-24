"""Unit and value normalizer: UCUM lookup with OMOP concept ID resolution.

Queries the OMOP vocabulary database for UCUM unit codes, categorical value
concepts, and ordinal scale grades. All lookups are cached via lru_cache
for performance.

No LLM calls — pure DB lookup with alias expansion and case-insensitive
matching.  Returns (None, None) for unrecognized inputs; never raises.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

_ORDINAL_PREFIX_RE = re.compile(
    r"^(?:grade|stage|class|score|level)\s*",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Clinical knowledge: ordinal scale alias -> canonical scale name
# (This mapping is not in OMOP — it's clinical domain knowledge about
# which entity names refer to which performance/grading scale.)
# ---------------------------------------------------------------------------

ORDINAL_SCALE_ALIASES: dict[str, str] = {
    "ecog": "ecog",
    "ecog ps": "ecog",
    "ecog performance status": "ecog",
    "eastern cooperative oncology group": "ecog",
    "who performance status": "ecog",
    "zubrod score": "ecog",
    "karnofsky": "karnofsky",
    "kps": "karnofsky",
    "karnofsky performance status": "karnofsky",
    "karnofsky performance scale": "karnofsky",
    "nyha": "nyha",
    "nyha class": "nyha",
    "nyha functional class": "nyha",
    "nyha classification": "nyha",
    "new york heart association": "nyha",
    "asa": "asa",
    "asa physical status": "asa",
    "asa ps": "asa",
    "asa class": "asa",
    "asa classification": "asa",
    "asa score": "asa",
    "american society of anesthesiologists": "asa",
}

# Unit concept ID for ordinal scores — always 8527 ({score})
_ORDINAL_UNIT_CONCEPT_ID = 8527


# ---------------------------------------------------------------------------
# DB-backed unit normalization
# ---------------------------------------------------------------------------


@lru_cache(maxsize=512)
def _cached_ucum_lookup(unit_key: str) -> tuple[str | None, int | None]:
    """Cached wrapper around _lookup_ucum_unit (keyed on lowercased unit text)."""
    from protocol_processor.tools.omop_mapper import _get_omop_engine, _lookup_ucum_unit

    try:
        engine = _get_omop_engine()
    except RuntimeError:
        logger.debug("OMOP_VOCAB_URL not set — unit lookup unavailable")
        return (None, None)
    return _lookup_ucum_unit(engine, unit_key)


def normalize_unit(unit_text: str | None) -> tuple[str | None, int | None]:
    """Normalize a unit string to its UCUM code and OMOP unit_concept_id.

    Args:
        unit_text: Raw unit text (e.g. "mg/dL", "%", "years").

    Returns:
        Tuple of (ucum_code, omop_unit_concept_id), or (None, None)
        if the input is None, empty, or unrecognized.
    """
    if unit_text is not None and not isinstance(unit_text, str):
        unit_text = str(unit_text)
    if not unit_text or not unit_text.strip():
        return (None, None)

    key = unit_text.strip().lower()
    return _cached_ucum_lookup(key)


# ---------------------------------------------------------------------------
# DB-backed categorical value normalization
# ---------------------------------------------------------------------------


@lru_cache(maxsize=128)
def _cached_value_lookup(value_key: str) -> tuple[str | None, int | None]:
    """Cached wrapper around _lookup_value_concept (keyed on lowercased value text)."""
    from protocol_processor.tools.omop_mapper import (
        _get_omop_engine,
        _lookup_value_concept,
    )

    try:
        engine = _get_omop_engine()
    except RuntimeError:
        logger.debug("OMOP_VOCAB_URL not set — value lookup unavailable")
        return (None, None)
    return _lookup_value_concept(engine, value_key)


def normalize_value(
    value_text: str | None,
) -> tuple[str | None, int | None]:
    """Normalize a categorical value to its SNOMED code and OMOP concept ID.

    Args:
        value_text: Raw value text (e.g. "positive", "negative", "normal").

    Returns:
        Tuple of (normalized_text, omop_value_concept_id), or (None, None)
        if the input is None, empty, or unrecognized.
    """
    if value_text is not None and not isinstance(value_text, str):
        value_text = str(value_text)
    if not value_text or not value_text.strip():
        return (None, None)

    key = value_text.strip().lower()
    return _cached_value_lookup(key)


# ---------------------------------------------------------------------------
# Ordinal scale normalization
# ---------------------------------------------------------------------------


def _match_ordinal_scale(entity_text: str) -> str | None:
    """Match entity text to an ordinal scale key.

    Uses three strategies in order:
    1. Exact alias match (case-insensitive)
    2. Entity text is a substring of an alias
    3. An alias is a substring of entity text

    Returns:
        Scale key (e.g. "ecog") or None if no match.
    """
    key = entity_text.strip().lower()

    # Strategy 1: exact alias match
    if key in ORDINAL_SCALE_ALIASES:
        return ORDINAL_SCALE_ALIASES[key]

    # Strategy 2 & 3: bidirectional substring containment
    for alias, scale_key in ORDINAL_SCALE_ALIASES.items():
        if key in alias or alias in key:
            return scale_key

    return None


def normalize_ordinal_value(
    value_text: str | None,
    entity_text: str | None = None,
) -> tuple[int | None, int | None] | None:
    """Entity-context-aware ordinal value normalization.

    Returns:
        (value_concept_id, unit_concept_id) if entity matches an ordinal scale.
        value_concept_id is the OMOP ID from DB lookup (or None if not found).
        unit_concept_id is always 8527 ({score}) for ordinal scales.
        Returns None (not a tuple) if entity doesn't match any ordinal scale.
    """
    if not entity_text or not entity_text.strip():
        return None

    scale_key = _match_ordinal_scale(entity_text)
    if scale_key is None:
        return None

    if not value_text or not value_text.strip():
        return (None, _ORDINAL_UNIT_CONCEPT_ID)

    # Normalize value: strip ordinal prefixes, convert "2.0" -> "2"
    cleaned = _ORDINAL_PREFIX_RE.sub("", value_text.strip())
    try:
        numeric = float(cleaned)
        if numeric == int(numeric):
            cleaned = str(int(numeric))
        else:
            cleaned = str(numeric)
    except (ValueError, TypeError):
        cleaned = cleaned.strip()

    # Look up the grade in the OMOP vocabulary
    from protocol_processor.tools.omop_mapper import (
        _get_omop_engine,
        _lookup_ordinal_concept,
    )

    try:
        engine = _get_omop_engine()
        omop_value_cid = _lookup_ordinal_concept(engine, scale_key, cleaned)
    except RuntimeError:
        logger.debug("OMOP_VOCAB_URL not set — ordinal lookup unavailable")
        omop_value_cid = None

    return (omop_value_cid, _ORDINAL_UNIT_CONCEPT_ID)


def propose_ordinal_mappings() -> list[dict[str, Any]]:
    """Return an empty list — ordinal mappings are now resolved dynamically from the DB.

    Retained for backward compatibility with callers that reference this function.
    """
    return []
