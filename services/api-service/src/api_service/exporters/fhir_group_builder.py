"""FHIR R4 Group resource builder (EBM IG).

Converts structured criteria into a FHIR Group resource with
characteristics representing eligibility criteria.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from shared.models import AtomicCriterion

from api_service.exporters import ProtocolExportData
from api_service.exporters.concept_utils import get_concept_code

# Map entity_concept_system to FHIR system URIs
_SYSTEM_URI_MAP: dict[str, str] = {
    "snomed": "http://snomed.info/sct",
    "snomedct": "http://snomed.info/sct",
    "loinc": "http://loinc.org",
    "rxnorm": "http://www.nlm.nih.gov/research/umls/rxnorm",
    "icd10": "http://hl7.org/fhir/sid/icd-10",
    "icd10cm": "http://hl7.org/fhir/sid/icd-10-cm",
    "cpt": "http://www.ama-assn.org/go/cpt",
    "hcpcs": "urn:oid:2.16.840.1.113883.6.285",
    "omop": "http://ohdsi.org/omop/concept",
}

# Map our relation_operator to FHIR comparator
_COMPARATOR_MAP: dict[str, str] = {
    ">": "gt",
    ">=": "ge",
    "<": "lt",
    "<=": "le",
    "gt": "gt",
    "gte": "ge",
    "lt": "lt",
    "lte": "le",
}


def build_fhir_group_export(data: ProtocolExportData) -> dict[str, Any]:
    """Build a FHIR R4 Group resource from structured criteria.

    Args:
        data: Loaded protocol export data.

    Returns:
        Dict representing the FHIR Group resource.
    """
    characteristics: list[dict[str, Any]] = []

    for criterion in data.criteria:
        tree = criterion.structured_criterion
        if not tree:
            continue

        is_exclusion = criterion.criteria_type == "exclusion"
        chars = _build_characteristics_from_tree(tree, data, exclude=is_exclusion)
        characteristics.extend(chars)

    group: dict[str, Any] = {
        "resourceType": "Group",
        "id": data.protocol.id,
        "type": "person",
        "actual": False,
        "name": data.protocol.title,
        "characteristic": characteristics,
    }

    # Set combination method if we have characteristics
    if characteristics:
        group["extension"] = [
            {
                "url": (
                    "http://hl7.org/fhir/uv/ebm/StructureDefinition"
                    "/characteristic-combination"
                ),
                "valueCode": "all-of",
            }
        ]

    return group


def _build_or_characteristic(
    tree: dict[str, Any],
    data: ProtocolExportData,
    exclude: bool,
) -> list[dict[str, Any]]:
    """Build a nested FHIR Group for OR logic."""
    children = tree.get("children", [])
    or_chars: list[dict[str, Any]] = []
    for child in children:
        or_chars.extend(_build_characteristics_from_tree(child, data, exclude=exclude))
    if not or_chars:
        return []

    nested_group_id = str(uuid4())
    nested_group: dict[str, Any] = {
        "resourceType": "Group",
        "id": nested_group_id,
        "type": "person",
        "actual": False,
        "characteristic": or_chars,
        "extension": [
            {
                "url": (
                    "http://hl7.org/fhir/uv/ebm/StructureDefinition"
                    "/characteristic-combination"
                ),
                "valueCode": "any-of",
            }
        ],
    }
    return [
        {
            "code": {"text": "Nested OR group"},
            "valueReference": {"reference": f"#/{nested_group_id}"},
            "exclude": exclude,
            "_contained": nested_group,
        }
    ]


def _build_characteristics_from_tree(
    tree: dict[str, Any],
    data: ProtocolExportData,
    exclude: bool = False,
) -> list[dict[str, Any]]:
    """Recursively build FHIR characteristics from an expression tree."""
    node_type = tree.get("type", "").upper()

    if node_type == "ATOMIC":
        atomic_id = tree.get("atomic_criterion_id")
        atomic = data.atomics_by_id.get(atomic_id) if atomic_id else None
        if not atomic:
            return []
        char = _build_characteristic(atomic, exclude=exclude)
        return [char] if char else []

    if node_type == "AND":
        result: list[dict[str, Any]] = []
        for child in tree.get("children", []):
            result.extend(
                _build_characteristics_from_tree(child, data, exclude=exclude)
            )
        return result

    if node_type == "OR":
        return _build_or_characteristic(tree, data, exclude)

    if node_type == "NOT":
        children = tree.get("children", [])
        if not children:
            return []
        return _build_characteristics_from_tree(children[0], data, exclude=not exclude)

    return []


def _get_system_uri(system: str | None) -> str:
    """Map an entity_concept_system to a FHIR system URI."""
    if not system:
        return "http://ohdsi.org/omop/concept"
    return _SYSTEM_URI_MAP.get(system.lower(), f"urn:oid:{system}")


def _get_concept_code(atomic: AtomicCriterion) -> str | None:
    """Get the best concept code for an atomic criterion.

    Delegates to the shared get_concept_code() helper.
    """
    return get_concept_code(atomic)


def _build_demographic_characteristic(
    atomic: AtomicCriterion,
    exclude: bool = False,
) -> dict[str, Any] | None:
    """Build a FHIR characteristic for demographics (age).

    Uses the usage-context-type CodeSystem for age instead of
    a SNOMED coded concept. The matcher derives age from birthDate.
    """
    if atomic.value_numeric is None:
        return None

    quantity: dict[str, Any] = {
        "value": atomic.value_numeric,
        "unit": atomic.unit_text or "years",
        "system": "http://unitsofmeasure.org",
        "code": "a",
    }
    if atomic.relation_operator:
        comparator = _COMPARATOR_MAP.get(atomic.relation_operator)
        if comparator:
            quantity["comparator"] = comparator

    return {
        "code": {
            "coding": [
                {
                    "system": (
                        "http://terminology.hl7.org/CodeSystem/usage-context-type"
                    ),
                    "code": "age",
                    "display": "Age Range",
                }
            ],
        },
        "exclude": exclude,
        "valueQuantity": quantity,
    }


def _build_characteristic(
    atomic: AtomicCriterion,
    exclude: bool = False,
) -> dict[str, Any] | None:
    """Build a single FHIR Group characteristic from an AtomicCriterion."""
    # Demographics: use age context type (not a coded concept)
    if (atomic.entity_domain or "").lower() == "demographics":
        return _build_demographic_characteristic(atomic, exclude=exclude)

    concept_code = _get_concept_code(atomic)
    if concept_code is None:
        return None

    system_uri = _get_system_uri(atomic.entity_concept_system)

    char: dict[str, Any] = {
        "code": {
            "coding": [
                {
                    "system": system_uri,
                    "code": concept_code,
                    "display": atomic.original_text or "",
                }
            ],
        },
        "exclude": exclude or atomic.negation,
    }

    # Add value: quantity or text
    if atomic.value_numeric is not None:
        quantity: dict[str, Any] = {
            "value": atomic.value_numeric,
        }
        if atomic.unit_text:
            quantity["unit"] = atomic.unit_text
        if atomic.relation_operator:
            comparator = _COMPARATOR_MAP.get(atomic.relation_operator)
            if comparator:
                quantity["comparator"] = comparator
        char["valueQuantity"] = quantity
    elif atomic.value_text:
        char["valueCodeableConcept"] = {
            "text": atomic.value_text,
        }
    else:
        # Boolean presence/absence
        char["valueBoolean"] = not atomic.negation

    return char
