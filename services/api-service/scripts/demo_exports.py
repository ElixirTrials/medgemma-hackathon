"""Demo: seed realistic criteria and show all three export outputs.

Usage (from api-service/):
    uv run python scripts/demo_exports.py
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any
from uuid import uuid4

# Ensure we can import api_service and shared
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "libs", "shared", "src"),
)

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import shared.models  # noqa: F401 — register tables
from shared.models import (
    AtomicCriterion,
    CompositeCriterion,
    Criteria,
    CriteriaBatch,
    CriterionRelationship,
    Protocol,
)
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel

from api_service.exporters import ProtocolExportData
from api_service.exporters.circe_builder import build_circe_export
from api_service.exporters.evaluation_sql_builder import build_evaluation_sql
from api_service.exporters.fhir_group_builder import build_fhir_group_export

# ── Criteria definitions ────────────────────────────────────────

CRITERIA_DEFS: list[dict[str, Any]] = [
    # ── Inclusion ───
    {
        "type": "inclusion",
        "text": "Adults aged 18 years or older",
        "atomics": [
            {
                "entity_domain": "demographics",
                "entity_concept_system": "snomed",
                "entity_concept_id": "424144002",
                "omop_concept_id": "4265453",
                "relation_operator": ">=",
                "value_numeric": 18.0,
                "unit_text": "years",
                "unit_concept_id": 9448,
                "original_text": "Age >= 18 years",
            },
        ],
    },
    {
        "type": "inclusion",
        "text": "Confirmed type 2 diabetes mellitus",
        "atomics": [
            {
                "entity_domain": "condition",
                "entity_concept_system": "snomed",
                "entity_concept_id": "44054006",
                "omop_concept_id": "201826",
                "original_text": "Type 2 diabetes mellitus",
            },
        ],
    },
    {
        "type": "inclusion",
        "text": "HbA1c between 7.0% and 10.0%",
        "logic": "AND",
        "atomics": [
            {
                "entity_domain": "measurement",
                "entity_concept_system": "loinc",
                "entity_concept_id": "4548-4",
                "omop_concept_id": "3004410",
                "relation_operator": ">=",
                "value_numeric": 7.0,
                "unit_text": "%",
                "unit_concept_id": 8554,
                "original_text": "HbA1c >= 7.0%",
            },
            {
                "entity_domain": "measurement",
                "entity_concept_system": "loinc",
                "entity_concept_id": "4548-4",
                "omop_concept_id": "3004410",
                "relation_operator": "<=",
                "value_numeric": 10.0,
                "unit_text": "%",
                "unit_concept_id": 8554,
                "original_text": "HbA1c <= 10.0%",
            },
        ],
    },
    {
        "type": "inclusion",
        "text": "eGFR >= 30 mL/min/1.73m2",
        "atomics": [
            {
                "entity_domain": "measurement",
                "entity_concept_system": "loinc",
                "entity_concept_id": "62238-1",
                "omop_concept_id": "3049187",
                "relation_operator": ">=",
                "value_numeric": 30.0,
                "unit_text": "mL/min/1.73m2",
                "unit_concept_id": 8795,
                "original_text": "eGFR >= 30 mL/min/1.73m2",
            },
        ],
    },
    # ── Exclusion ───
    {
        "type": "exclusion",
        "text": "Type 1 diabetes mellitus",
        "atomics": [
            {
                "entity_domain": "condition",
                "entity_concept_system": "snomed",
                "entity_concept_id": "46635009",
                "omop_concept_id": "201254",
                "negation": True,
                "original_text": "Type 1 diabetes mellitus",
            },
        ],
    },
    {
        "type": "exclusion",
        "text": "Current use of insulin or GLP-1 receptor agonist",
        "logic": "OR",
        "atomics": [
            {
                "entity_domain": "drug",
                "entity_concept_system": "rxnorm",
                "entity_concept_id": "253182",
                "omop_concept_id": "1567198",
                "original_text": "Insulin",
            },
            {
                "entity_domain": "drug",
                "entity_concept_system": "rxnorm",
                "entity_concept_id": "60548",
                "omop_concept_id": "1583722",
                "original_text": "GLP-1 receptor agonist",
            },
        ],
    },
    {
        "type": "exclusion",
        "text": "NYHA class III or IV heart failure",
        "atomics": [
            {
                "entity_domain": "condition",
                "entity_concept_system": "snomed",
                "entity_concept_id": "195111005",
                "omop_concept_id": "316139",
                "value_text": "Class III-IV",
                "original_text": "NYHA class III/IV heart failure",
            },
        ],
    },
]


def _seed(session: Session) -> ProtocolExportData:
    """Seed the database and return export data."""
    proto = Protocol(
        id=str(uuid4()),
        title="Phase 3 T2DM SGLT2 Inhibitor Trial (NCT00000000)",
        file_uri="local://demo.pdf",
        status="complete",
    )
    session.add(proto)
    session.flush()

    batch = CriteriaBatch(
        id=str(uuid4()),
        protocol_id=proto.id,
        is_archived=False,
    )
    session.add(batch)
    session.flush()

    all_criteria = []
    all_atomics = []
    all_composites = []
    all_rels = []

    for cdef in CRITERIA_DEFS:
        atomic_ids = [str(uuid4()) for _ in cdef["atomics"]]
        logic = cdef.get("logic")

        # Build expression tree
        tree: dict[str, Any]
        if len(atomic_ids) == 1:
            tree = {
                "type": "ATOMIC",
                "atomic_criterion_id": atomic_ids[0],
            }
        else:
            tree = {
                "type": logic or "AND",
                "children": [
                    {"type": "ATOMIC", "atomic_criterion_id": aid} for aid in atomic_ids
                ],
            }

        crit = Criteria(
            id=str(uuid4()),
            batch_id=batch.id,
            criteria_type=cdef["type"],
            text=cdef["text"],
            structured_criterion=tree,
        )
        session.add(crit)
        session.flush()
        all_criteria.append(crit)

        for i, (adef, aid) in enumerate(zip(cdef["atomics"], atomic_ids)):
            adef_dict: dict[str, Any] = adef
            a = AtomicCriterion(
                id=aid,
                criterion_id=crit.id,
                protocol_id=proto.id,
                inclusion_exclusion=cdef["type"],
                entity_concept_id=adef_dict.get("entity_concept_id"),
                entity_concept_system=adef_dict.get("entity_concept_system"),
                omop_concept_id=adef_dict.get("omop_concept_id"),
                entity_domain=adef_dict.get("entity_domain"),
                relation_operator=adef_dict.get("relation_operator"),
                value_numeric=adef_dict.get("value_numeric"),
                value_text=adef_dict.get("value_text"),
                unit_text=adef_dict.get("unit_text"),
                unit_concept_id=adef_dict.get("unit_concept_id"),
                negation=adef_dict.get("negation", False),
                original_text=adef_dict.get("original_text"),
                confidence_score=0.95,
            )
            session.add(a)
            all_atomics.append(a)

        # If composite, also make a composite + relationships
        if logic and len(atomic_ids) > 1:
            comp = CompositeCriterion(
                id=str(uuid4()),
                criterion_id=crit.id,
                protocol_id=proto.id,
                inclusion_exclusion=cdef["type"],
                logic_operator=logic,
                original_text=cdef["text"],
            )
            session.add(comp)
            session.flush()
            all_composites.append(comp)

            for seq, aid in enumerate(atomic_ids):
                rel = CriterionRelationship(
                    parent_criterion_id=comp.id,
                    child_criterion_id=aid,
                    child_type="atomic",
                    child_sequence=seq,
                )
                session.add(rel)
                all_rels.append(rel)

    session.commit()

    return ProtocolExportData(
        protocol=proto,
        criteria=all_criteria,
        atomics=all_atomics,
        composites=all_composites,
        relationships=all_rels,
        atomics_by_id={a.id: a for a in all_atomics},
        criteria_by_id={c.id: c for c in all_criteria},
    )


def _sep(title: str) -> None:
    print(f"\n{'=' * 72}")
    print(f"  {title}")
    print(f"{'=' * 72}")


def _print_criteria_table(data: ProtocolExportData) -> None:
    """Print a summary table of seeded criteria."""
    header = (
        f"{'#':<3} {'Type':<10} {'Domain':<14} {'Text':<35} "
        f"{'OMOP':<10} {'Op':<4} {'Value':<8} {'Unit':<14} {'Neg':<4}"
    )
    print(header)
    print("-" * len(header))
    for i, a in enumerate(data.atomics, 1):
        print(
            f"{i:<3} "
            f"{a.inclusion_exclusion:<10} "
            f"{(a.entity_domain or '-'):<14} "
            f"{(a.original_text or '-')[:35]:<35} "
            f"{(a.omop_concept_id or '-'):<10} "
            f"{(a.relation_operator or '-'):<4} "
            f"{str(a.value_numeric or a.value_text or '-'):<8} "
            f"{(a.unit_text or '-'):<14} "
            f"{'Y' if a.negation else 'N':<4}"
        )


def main() -> None:
    """Seed data and display export outputs."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        data = _seed(session)

        # ── Table ────────────────────────────────────────────────
        _sep("SEEDED ATOMIC CRITERIA")
        _print_criteria_table(data)
        print(
            f"\nTotals: {len(data.criteria)} criteria, "
            f"{len(data.atomics)} atomics, "
            f"{len(data.composites)} composites, "
            f"{len(data.relationships)} relationships"
        )

        # ── CIRCE ────────────────────────────────────────────────
        _sep("CIRCE CohortExpression JSON")
        circe = build_circe_export(data)
        print(json.dumps(circe, indent=2))

        # ── FHIR Group ───────────────────────────────────────────
        _sep("FHIR R4 Group Resource JSON")
        fhir = build_fhir_group_export(data)
        print(json.dumps(fhir, indent=2))

        # ── Evaluation SQL ───────────────────────────────────────
        _sep("OMOP CDM v5.4 Evaluation SQL")
        sql = build_evaluation_sql(data)
        print(sql)

    _sep("DONE")


if __name__ == "__main__":
    main()
