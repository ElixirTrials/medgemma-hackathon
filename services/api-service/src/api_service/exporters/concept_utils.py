"""Shared concept ID resolution for export builders.

Centralizes the logic for resolving the best concept identifier
from AtomicCriterion records, used by CIRCE, FHIR Group, and
evaluation SQL builders.
"""

from __future__ import annotations

from shared.models import AtomicCriterion


def get_concept_id(atomic: AtomicCriterion) -> int | None:
    """Get the best integer concept ID for an atomic criterion.

    Prefers omop_concept_id, falls back to entity_concept_id.
    Returns None if neither is a valid integer.

    Args:
        atomic: AtomicCriterion record.

    Returns:
        Integer concept ID, or None.
    """
    for val in (atomic.omop_concept_id, atomic.entity_concept_id):
        if val is not None:
            try:
                return int(val)
            except (ValueError, TypeError):
                continue
    return None


def get_concept_code(atomic: AtomicCriterion) -> str | None:
    """Get the best string concept code for an atomic criterion.

    Prefers omop_concept_id, falls back to entity_concept_id.
    Returns None if neither is available.

    Args:
        atomic: AtomicCriterion record.

    Returns:
        String concept code, or None.
    """
    for val in (atomic.omop_concept_id, atomic.entity_concept_id):
        if val is not None:
            return str(val)
    return None
