"""OHDSI CIRCE CohortExpression JSON builder.

Converts structured criteria (expression trees with atomic/composite nodes)
into the CIRCE JSON format consumed by OHDSI Atlas and WebAPI.
"""

from __future__ import annotations

from typing import Any

from shared.models import AtomicCriterion

from api_service.exporters import ProtocolExportData

# Map our entity_domain values to CIRCE domain table names
_DOMAIN_TO_CIRCE: dict[str, str] = {
    "condition": "ConditionOccurrence",
    "measurement": "Measurement",
    "drug": "DrugExposure",
    "procedure": "ProcedureOccurrence",
    "observation": "Observation",
    "device": "DeviceExposure",
    "visit": "VisitOccurrence",
}

# Map relation_operator to CIRCE Op string
_OP_MAP: dict[str, str] = {
    ">": "gt",
    ">=": "gte",
    "<": "lt",
    "<=": "lte",
    "=": "eq",
    "==": "eq",
    "!=": "neq",
    "gt": "gt",
    "gte": "gte",
    "lt": "lt",
    "lte": "lte",
    "eq": "eq",
    "neq": "neq",
}


def build_circe_export(data: ProtocolExportData) -> dict[str, Any]:
    """Build a CIRCE CohortExpression JSON from structured criteria.

    Args:
        data: Loaded protocol export data.

    Returns:
        Dict representing the CIRCE CohortExpression.
    """
    concept_sets: list[dict[str, Any]] = []
    concept_set_index: dict[str, int] = {}  # concept_id -> index in concept_sets

    inclusion_criteria: list[dict[str, Any]] = []
    censoring_criteria: list[dict[str, Any]] = []

    for criterion in data.criteria:
        tree = criterion.structured_criterion
        if not tree:
            continue

        is_exclusion = criterion.criteria_type == "exclusion"
        group = _build_criteria_group(tree, data, concept_sets, concept_set_index)
        if group is None:
            continue

        if is_exclusion:
            censoring_criteria.append(group)
        else:
            inclusion_criteria.append(group)

    expression: dict[str, Any] = {
        "ConceptSets": concept_sets,
        "PrimaryCriteria": {
            "CriteriaList": [],
            "ObservationWindow": {
                "PriorDays": 0,
                "PostDays": 0,
            },
            "PrimaryCriteriaLimit": {"Type": "First"},
        },
        "AdditionalCriteria": {
            "Type": "ALL",
            "CriteriaList": inclusion_criteria,
        },
        "CensoringCriteria": censoring_criteria,
    }

    return expression


def _get_concept_id(atomic: AtomicCriterion) -> int | None:
    """Get the best concept ID for an atomic criterion.

    Prefers omop_concept_id, falls back to entity_concept_id.
    Returns None if neither is a valid integer.
    """
    for field_val in (atomic.omop_concept_id, atomic.entity_concept_id):
        if field_val is not None:
            try:
                return int(field_val)
            except (ValueError, TypeError):
                continue
    return None


def _ensure_concept_set(
    atomic: AtomicCriterion,
    concept_sets: list[dict[str, Any]],
    concept_set_index: dict[str, int],
) -> int | None:
    """Ensure a ConceptSet exists for the atomic's concept ID.

    Returns the ConceptSet index, or None if no valid concept ID.
    """
    concept_id = _get_concept_id(atomic)
    if concept_id is None:
        return None

    key = str(concept_id)
    if key in concept_set_index:
        return concept_set_index[key]

    idx = len(concept_sets)
    concept_sets.append(
        {
            "id": idx,
            "name": atomic.original_text or f"Concept {concept_id}",
            "expression": {
                "items": [
                    {
                        "concept": {
                            "CONCEPT_ID": concept_id,
                            "CONCEPT_NAME": atomic.original_text or "",
                        },
                        "isExcluded": False,
                        "includeDescendants": True,
                        "includeMapped": False,
                    }
                ],
            },
        }
    )
    concept_set_index[key] = idx
    return idx


def _build_demographic_criteria(
    atomic: AtomicCriterion,
) -> dict[str, Any] | None:
    """Build a CIRCE DemographicCriteria entry for age.

    CIRCE handles demographics via DemographicCriteria with an Age
    range — no ConceptSet needed. Atlas derives age from year_of_birth.
    """
    if atomic.value_numeric is None or not atomic.relation_operator:
        return None

    op_str = _OP_MAP.get(atomic.relation_operator, "gte")
    age_filter: dict[str, Any] = {
        "Value": int(atomic.value_numeric),
        "Op": op_str,
    }

    return {
        "Criteria": {
            "DemographicCriteria": {
                "Age": age_filter,
            },
        },
    }


def _build_atomic_criteria(
    atomic: AtomicCriterion,
    concept_sets: list[dict[str, Any]],
    concept_set_index: dict[str, int],
) -> dict[str, Any] | None:
    """Build a CIRCE criteria entry from an AtomicCriterion."""
    # Demographics: use DemographicCriteria (no ConceptSet)
    if (atomic.entity_domain or "").lower() == "demographics":
        return _build_demographic_criteria(atomic)

    cs_idx = _ensure_concept_set(atomic, concept_sets, concept_set_index)
    if cs_idx is None:
        return None

    domain = _DOMAIN_TO_CIRCE.get(
        (atomic.entity_domain or "").lower(), "ConditionOccurrence"
    )

    criteria_entry: dict[str, Any] = {
        "Criteria": {
            domain: {
                "CodesetId": cs_idx,
            },
        },
    }

    # Handle negation: absence = OccurrenceCount of 0
    if atomic.negation:
        criteria_entry["Criteria"]["OccurrenceCount"] = {
            "Value": 0,
            "Op": "eq",
        }

    # Add value filter for measurements
    if atomic.relation_operator and atomic.value_numeric is not None:
        op_str = _OP_MAP.get(atomic.relation_operator, "eq")
        value_filter: dict[str, Any] = {
            "Value": atomic.value_numeric,
            "Op": op_str,
        }
        if atomic.unit_concept_id is not None:
            value_filter["UnitConceptId"] = atomic.unit_concept_id
        criteria_entry["Criteria"]["ValueAsNumber"] = value_filter

    return criteria_entry


def _build_and_or_group(
    tree: dict[str, Any],
    data: ProtocolExportData,
    concept_sets: list[dict[str, Any]],
    concept_set_index: dict[str, int],
) -> dict[str, Any] | None:
    """Build a CIRCE AND/OR CriteriaGroup from child nodes."""
    node_type = tree.get("type", "").upper()
    children = tree.get("children", [])
    child_criteria = []
    for child in children:
        result = _build_criteria_group(child, data, concept_sets, concept_set_index)
        if result is not None:
            child_criteria.append(result)

    if not child_criteria:
        return None

    group_type = "ALL" if node_type == "AND" else "ANY"
    return {"Type": group_type, "CriteriaList": child_criteria}


def _build_not_group(
    tree: dict[str, Any],
    data: ProtocolExportData,
    concept_sets: list[dict[str, Any]],
    concept_set_index: dict[str, int],
) -> dict[str, Any] | None:
    """Build a negated CIRCE criteria entry."""
    children = tree.get("children", [])
    if not children:
        return None
    inner = _build_criteria_group(children[0], data, concept_sets, concept_set_index)
    if inner is None:
        return None
    if "Criteria" in inner:
        inner["Criteria"]["OccurrenceCount"] = {
            "Value": 0,
            "Op": "eq",
        }
    return inner


def _build_criteria_group(
    tree: dict[str, Any],
    data: ProtocolExportData,
    concept_sets: list[dict[str, Any]],
    concept_set_index: dict[str, int],
) -> dict[str, Any] | None:
    """Recursively build a CIRCE CriteriaGroup from an expression tree."""
    node_type = tree.get("type", "").upper()

    if node_type == "ATOMIC":
        atomic_id = tree.get("atomic_criterion_id")
        if not atomic_id:
            return None
        atomic = data.atomics_by_id.get(atomic_id)
        if not atomic:
            return None
        return _build_atomic_criteria(atomic, concept_sets, concept_set_index)

    if node_type in ("AND", "OR"):
        return _build_and_or_group(tree, data, concept_sets, concept_set_index)

    if node_type == "NOT":
        return _build_not_group(tree, data, concept_sets, concept_set_index)

    return None
