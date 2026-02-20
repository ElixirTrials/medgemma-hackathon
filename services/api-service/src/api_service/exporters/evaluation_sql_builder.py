"""OMOP CDM v5.4 evaluation SQL generator.

Generates ready-to-run SQL that evaluates a protocol's eligibility criteria
against an OMOP CDM database. The SQL is returned as text, not executed.

Limitation: This builder uses a flat AND/OR model. All inclusion atomics are
combined with AND (all required); all exclusion atomics use NOT EXISTS (any
disqualifies). The expression tree's nested AND/OR/NOT structure is NOT
respected. For example, "HbA1c >= 7% OR fasting glucose >= 126" is evaluated
as requiring both rather than either. The CIRCE and FHIR Group builders
correctly walk the expression tree. A future enhancement could add tree-aware
SQL generation using recursive CTE grouping.
"""

from __future__ import annotations

from shared.models import AtomicCriterion

from api_service.exporters import ProtocolExportData
from api_service.exporters.concept_utils import get_concept_id

# Map entity_domain to OMOP CDM table + concept_id column
_DOMAIN_TABLE: dict[str, tuple[str, str]] = {
    "condition": ("condition_occurrence", "condition_concept_id"),
    "measurement": ("measurement", "measurement_concept_id"),
    "drug": ("drug_exposure", "drug_concept_id"),
    "procedure": ("procedure_occurrence", "procedure_concept_id"),
    "observation": ("observation", "observation_concept_id"),
    "device": ("device_exposure", "device_concept_id"),
    "visit": ("visit_occurrence", "visit_concept_id"),
}

# Map relation_operator to SQL operator
_SQL_OP: dict[str, str] = {
    ">": ">",
    ">=": ">=",
    "<": "<",
    "<=": "<=",
    "=": "=",
    "==": "=",
    "!=": "!=",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
    "eq": "=",
    "neq": "!=",
}


def build_evaluation_sql(data: ProtocolExportData) -> str:
    """Generate OMOP CDM evaluation SQL from structured criteria.

    Produces:
    1. Per-atomic CTEs using concept_ancestor for descendant expansion
    2. Domain-specific evaluation logic
    3. Final eligibility query combining inclusion/exclusion

    Args:
        data: Loaded protocol export data.

    Returns:
        SQL string ready for execution against an OMOP CDM v5.4 database.
    """
    ctes: list[str] = []
    inclusion_cte_names: list[str] = []
    exclusion_cte_names: list[str] = []

    for i, atomic in enumerate(data.atomics):
        concept_id = _get_valid_concept_id(atomic)
        if concept_id is None:
            continue

        cte_name = f"cte_{i}"
        cte_sql = _build_atomic_cte(atomic, concept_id, cte_name)
        ctes.append(cte_sql)

        if atomic.inclusion_exclusion == "exclusion" or atomic.negation:
            exclusion_cte_names.append(cte_name)
        else:
            inclusion_cte_names.append(cte_name)

    if not ctes:
        return (
            "-- No structured criteria with valid concept IDs found.\n"
            "SELECT NULL AS person_id WHERE 1=0;\n"
        )

    parts: list[str] = []
    parts.append("-- Auto-generated OMOP CDM v5.4 eligibility evaluation SQL")
    parts.append(f"-- Protocol: {data.protocol.title} ({data.protocol.id})")
    parts.append(f"-- Generated from {len(ctes)} atomic criteria\n")
    parts.append("WITH")
    parts.append(",\n\n".join(ctes))

    # Build final SELECT
    parts.append("\n\nSELECT p.person_id")
    parts.append("FROM person p")

    # Inclusion: require all
    for cte_name in inclusion_cte_names:
        parts.append(
            f"WHERE EXISTS (\n"
            f"    SELECT 1 FROM {cte_name} c\n"
            f"    WHERE c.person_id = p.person_id\n"
            f")"
            if cte_name == inclusion_cte_names[0]
            else f"AND EXISTS (\n"
            f"    SELECT 1 FROM {cte_name} c\n"
            f"    WHERE c.person_id = p.person_id\n"
            f")"
        )

    # Exclusion: reject any
    for cte_name in exclusion_cte_names:
        prefix = (
            "AND"
            if inclusion_cte_names
            else ("WHERE" if cte_name == exclusion_cte_names[0] else "AND")
        )
        parts.append(
            f"{prefix} NOT EXISTS (\n"
            f"    SELECT 1 FROM {cte_name} c\n"
            f"    WHERE c.person_id = p.person_id\n"
            f")"
        )

    parts.append(";")
    return "\n".join(parts)


def _get_valid_concept_id(atomic: AtomicCriterion) -> int | None:
    """Get a validated integer concept ID for SQL interpolation.

    Delegates to the shared get_concept_id() helper.
    """
    return get_concept_id(atomic)


def _build_atomic_cte(atomic: AtomicCriterion, concept_id: int, cte_name: str) -> str:
    """Build a CTE for a single atomic criterion."""
    domain = (atomic.entity_domain or "condition").lower()

    # Demographics: special handling for age
    if domain == "demographics":
        return _build_demographics_cte(atomic, cte_name)

    table_name, concept_col = _DOMAIN_TABLE.get(
        domain, ("condition_occurrence", "condition_concept_id")
    )

    lines: list[str] = []
    lines.append(f"{cte_name} AS (")
    lines.append("    SELECT DISTINCT t.person_id")
    lines.append(f"    FROM {table_name} t")
    lines.append("    INNER JOIN concept_ancestor ca")
    lines.append(f"        ON ca.descendant_concept_id = t.{concept_col}")
    lines.append(f"    WHERE ca.ancestor_concept_id = {concept_id}")

    # Measurement value filter
    is_measurement = (
        domain == "measurement"
        and atomic.relation_operator
        and atomic.value_numeric is not None
    )
    if is_measurement:
        sql_op = _SQL_OP.get(atomic.relation_operator or "=", "=")
        lines.append(f"    AND t.value_as_number {sql_op} {atomic.value_numeric}")
        if atomic.unit_concept_id is not None:
            lines.append(f"    AND t.unit_concept_id = {atomic.unit_concept_id}")

    lines.append(")")
    return "\n".join(lines)


def _build_demographics_cte(atomic: AtomicCriterion, cte_name: str) -> str:
    """Build a CTE for demographics-based criteria (age)."""
    lines: list[str] = []
    lines.append(f"{cte_name} AS (")
    lines.append("    SELECT p.person_id")
    lines.append("    FROM person p")

    if atomic.relation_operator and atomic.value_numeric is not None:
        sql_op = _SQL_OP.get(atomic.relation_operator or "=", "=")
        lines.append(
            f"    WHERE EXTRACT(YEAR FROM CURRENT_DATE) - p.year_of_birth"
            f" {sql_op} {int(atomic.value_numeric)}"
        )
    else:
        lines.append("    WHERE 1=1")

    lines.append(")")
    return "\n".join(lines)
