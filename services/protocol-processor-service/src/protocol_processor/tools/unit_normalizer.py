"""Unit and value normalizer: UCUM lookup with OMOP concept ID resolution.

Phase 3 (Gap 7): Deterministic YAML-based lookup mapping common clinical
trial units to UCUM codes and OMOP unit_concept_id values, plus optional
categorical value normalization (e.g. "positive" -> SNOMED qualifier concept).

No LLM calls — pure static lookup with alias expansion and case-insensitive
matching.  Returns (None, None) for unrecognized inputs; never raises.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_CONFIG_PATH = Path(__file__).parent.parent / "config" / "ucum_mappings.yaml"


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
