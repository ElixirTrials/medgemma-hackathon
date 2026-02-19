"""Unit and value normalizer: UCUM lookup with OMOP concept ID resolution.

Phase 3 (Gap 7): Deterministic YAML-based lookup mapping common clinical
trial units to UCUM codes and OMOP unit_concept_id values, plus optional
categorical value normalization (e.g. "positive" -> SNOMED qualifier concept).

Phase 3b: Ordinal scale normalization (ECOG, Karnofsky, NYHA, etc.) with
agent-assisted concept resolution.  Recognized ordinal entities get
unit_concept_id=8527 ({score}); value_concept_id comes from YAML config
(populated incrementally via agent/approval workflow).

No LLM calls — pure static lookup with alias expansion and case-insensitive
matching.  Returns (None, None) for unrecognized inputs; never raises.
"""

from __future__ import annotations

import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "ucum_mappings.yaml"

_ORDINAL_PREFIX_RE = re.compile(
    r"^(?:grade|stage|class|score|level)\s*",
    re.IGNORECASE,
)


@lru_cache(maxsize=1)
def _load_ucum_mappings() -> tuple[dict[str, tuple[str, int]], dict[str, int]]:
    """Load and index the UCUM mappings YAML (cached after first call).

    Returns:
        Tuple of (unit_lookup, value_lookup) where:
        - unit_lookup: lowercased alias/canonical -> (canonical, omop_id)
        - value_lookup: lowercased value text -> omop_value_concept_id
    """
    with open(_CONFIG_PATH) as f:
        data: dict[str, Any] = yaml.safe_load(f)

    unit_lookup: dict[str, tuple[str, int]] = {}
    for entry in data.get("units", []):
        canonical: str = entry["canonical"]
        omop_id: int = entry["omop_unit_concept_id"]
        # Index canonical form
        unit_lookup[canonical.strip().lower()] = (canonical, omop_id)
        # Index all aliases
        for alias in entry.get("aliases", []):
            unit_lookup[alias.strip().lower()] = (canonical, omop_id)

    value_lookup: dict[str, int] = {}
    for text, concept_id in data.get("value_mappings", {}).items():
        value_lookup[str(text).strip().lower()] = int(concept_id)

    return unit_lookup, value_lookup


def normalize_unit(unit_text: str | None) -> tuple[str | None, int | None]:
    """Normalize a unit string to its UCUM code and OMOP unit_concept_id.

    Args:
        unit_text: Raw unit text (e.g. "mg/dL", "%", "years").

    Returns:
        Tuple of (ucum_code, omop_unit_concept_id), or (None, None)
        if the input is None, empty, or unrecognized.
    """
    if not unit_text or not unit_text.strip():
        return (None, None)

    key = unit_text.strip().lower()
    unit_lookup, _ = _load_ucum_mappings()
    result = unit_lookup.get(key)
    if result is not None:
        return result
    return (None, None)


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
    if not value_text or not value_text.strip():
        return (None, None)

    key = value_text.strip().lower()
    _, value_lookup = _load_ucum_mappings()
    concept_id = value_lookup.get(key)
    if concept_id is not None:
        return (key, concept_id)
    return (None, None)


# ---------------------------------------------------------------------------
# Ordinal scale normalization (Phase 3b)
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _load_ordinal_scales() -> tuple[dict[str, str], dict[str, Any]]:
    """Load ordinal scale definitions from YAML config (cached).

    Returns:
        Tuple of (alias_to_scale, scale_defs) where:
        - alias_to_scale: lowercased alias -> scale key (e.g. "ecog")
        - scale_defs: raw ordinal_scales dict from YAML
    """
    with open(_CONFIG_PATH) as f:
        data: dict[str, Any] = yaml.safe_load(f)

    scale_defs: dict[str, Any] = data.get("ordinal_scales", {})
    alias_to_scale: dict[str, str] = {}
    for scale_key, scale_def in scale_defs.items():
        for alias in scale_def.get("entity_aliases", []):
            alias_to_scale[alias.strip().lower()] = scale_key

    return alias_to_scale, scale_defs


def _match_ordinal_scale(entity_text: str) -> str | None:
    """Match entity text to an ordinal scale key.

    Uses three strategies in order:
    1. Exact alias match (case-insensitive)
    2. Entity text is a substring of an alias
    3. An alias is a substring of entity text

    Returns:
        Scale key (e.g. "ecog") or None if no match.
    """
    alias_to_scale, _ = _load_ordinal_scales()
    key = entity_text.strip().lower()

    # Strategy 1: exact alias match
    if key in alias_to_scale:
        return alias_to_scale[key]

    # Strategy 2 & 3: bidirectional substring containment
    for alias, scale_key in alias_to_scale.items():
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
        value_concept_id is the approved OMOP ID from YAML (or None if not yet
        resolved).  unit_concept_id is always 8527 ({score}) for ordinal scales.
        Returns None (not a tuple) if entity doesn't match any ordinal scale.
    """
    if not entity_text or not entity_text.strip():
        return None

    scale_key = _match_ordinal_scale(entity_text)
    if scale_key is None:
        return None

    _, scale_defs = _load_ordinal_scales()
    scale_def = scale_defs[scale_key]
    unit_concept_id: int | None = scale_def.get("unit_concept_id")

    if not value_text or not value_text.strip():
        return (None, unit_concept_id)

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

    values = scale_def.get("values", {})
    val_entry = values.get(cleaned)
    if val_entry is None:
        # Grade not in the defined values for this scale
        return (None, unit_concept_id)

    omop_value_cid = val_entry.get("omop_value_concept_id")
    return (omop_value_cid, unit_concept_id)


def propose_ordinal_mappings() -> list[dict[str, Any]]:
    """Scan ordinal_scales config and return entries missing omop_value_concept_id.

    Returns a list of dicts, each with:
      - scale: scale key (e.g., "ecog")
      - grade: value string (e.g., "2")
      - snomed_code: known SNOMED code (if any)
      - loinc_answer: known LOINC answer code (if any)
      - description: human-readable description
      - status: "needs_resolution"

    This output can be fed to an LLM agent or OMOP vocabulary lookup to propose
    omop_value_concept_id values.  Once approved, add them to the YAML.
    """
    _, scale_defs = _load_ordinal_scales()
    missing: list[dict[str, Any]] = []

    for scale_key, scale_def in scale_defs.items():
        for grade, val_entry in scale_def.get("values", {}).items():
            if val_entry.get("omop_value_concept_id") is not None:
                continue
            missing.append(
                {
                    "scale": scale_key,
                    "grade": grade,
                    "snomed_code": val_entry.get("snomed_code"),
                    "loinc_answer": val_entry.get("loinc_answer"),
                    "description": val_entry.get("description"),
                    "status": "needs_resolution",
                }
            )

    return missing
