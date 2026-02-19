"""Real E2E: ordinal resolution with live Gemini + live Postgres.

Creates a protocol with mixed criteria (known ordinal, unknown ordinal,
lab values), runs build_expression_tree to create AtomicCriterion
records, then runs ordinal_resolve_node with the REAL Gemini API.

Usage:
    set -a && source ../../.env && set +a
    uv run python scripts/run_ordinal_e2e.py
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from api_service.storage import engine
from shared.models import (
    AtomicCriterion,
    AuditLog,
    Criteria,
    CriteriaBatch,
    Protocol,
)
from sqlmodel import Session, select

from protocol_processor.nodes.ordinal_resolve import (
    ordinal_resolve_node,
)
from protocol_processor.tools.structure_builder import (
    build_expression_tree,
)
from protocol_processor.tools.unit_normalizer import (
    normalize_ordinal_value,
)

# ── Test criteria: mix of known, unknown, and non-ordinal ─────────

CRITERIA = [
    {
        "text": "ECOG performance status <= 2",
        "label": "ECOG (known ordinal)",
        "mappings": [
            {
                "entity": "ECOG performance status",
                "relation": "<=",
                "value": "2",
                "unit": None,
            },
        ],
    },
    {
        "text": "Child-Pugh score <= 6 (class A)",
        "label": "Child-Pugh (unknown ordinal)",
        "mappings": [
            {
                "entity": "Child-Pugh score",
                "relation": "<=",
                "value": "6",
                "unit": None,
            },
        ],
    },
    {
        "text": "Glasgow Coma Scale >= 13",
        "label": "GCS (unknown ordinal)",
        "mappings": [
            {
                "entity": "Glasgow Coma Scale",
                "relation": ">=",
                "value": "13",
                "unit": None,
            },
        ],
    },
    {
        "text": "MELD score <= 15",
        "label": "MELD (unknown ordinal)",
        "mappings": [
            {
                "entity": "MELD score",
                "relation": "<=",
                "value": "15",
                "unit": None,
            },
        ],
    },
    {
        "text": "HbA1c <= 7.0%",
        "label": "HbA1c (lab value, not ordinal)",
        "mappings": [
            {
                "entity": "HbA1c",
                "relation": "<=",
                "value": "7.0",
                "unit": "%",
            },
        ],
    },
    {
        "text": "Creatinine clearance >= 60 mL/min",
        "label": "CrCl (lab value, not ordinal)",
        "mappings": [
            {
                "entity": "Creatinine clearance",
                "relation": ">=",
                "value": "60",
                "unit": "mL/min",
            },
        ],
    },
]


def _sep(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}\n")


def _phase1_create(session: Session) -> tuple[str, str]:
    """Create protocol + batch and build expression trees."""
    protocol = Protocol(
        title="ORDINAL-E2E-LIVE",
        file_uri="local://ordinal-e2e.pdf",
    )
    session.add(protocol)
    session.flush()
    batch = CriteriaBatch(protocol_id=protocol.id)
    session.add(batch)
    session.flush()
    return protocol.id, batch.id


async def _phase1_build(
    session: Session,
    protocol_id: str,
    batch_id: str,
) -> None:
    """Process each criterion through build_expression_tree."""
    for crit_def in CRITERIA:
        crit = Criteria(
            batch_id=batch_id,
            criteria_type="inclusion",
            text=crit_def["text"],
        )
        session.add(crit)
        session.flush()

        await build_expression_tree(
            criterion_text=crit_def["text"],
            field_mappings=crit_def["mappings"],
            criterion_id=crit.id,
            protocol_id=protocol_id,
            inclusion_exclusion="inclusion",
            session=session,
        )
        session.flush()

        atomics = session.exec(
            select(AtomicCriterion).where(
                AtomicCriterion.criterion_id == crit.id,
            )
        ).all()
        a = atomics[0] if atomics else None

        ordinal_check = normalize_ordinal_value(
            str(crit_def["mappings"][0].get("value", "")),
            crit_def["mappings"][0].get("entity"),
        )

        label = crit_def["label"]
        if a:
            print(
                f"  {label}:"
                f"  unit_concept_id={a.unit_concept_id}"
                f"  value_numeric={a.value_numeric}"
                f"  unit_text={a.unit_text!r}"
                f"  ordinal_match={'YES' if ordinal_check else 'no'}"
            )
        else:
            print(f"  {label}: NO ATOMIC CREATED")

    session.commit()


def _print_proposals(result: dict[str, Any]) -> None:
    """Print Gemini proposals from result state."""
    proposals_json = result.get("ordinal_proposals_json")
    if not proposals_json:
        print("\nNo proposals returned (LLM may have failed)")
        return

    proposals = json.loads(proposals_json)
    print(f"\nProposals from Gemini ({len(proposals)}):")
    for p in proposals:
        print(f"\n  Scale: {p.get('scale_name')}")
        print(f"  Entity: {p.get('entity_text')}")
        print(f"  Confidence: {p.get('confidence')}")
        print(f"  LOINC: {p.get('loinc_code')}")
        print(f"  Aliases: {p.get('entity_aliases', [])}")
        values = p.get("values", [])
        if values:
            print(f"  Values ({len(values)}):")
            for v in values[:5]:
                print(
                    f"    {v.get('grade')}: {v.get('description')}"
                    f" (SNOMED: {v.get('snomed_code')})"
                )
            if len(values) > 5:
                print(f"    ... and {len(values) - 5} more")


def _phase3_verify(batch_id: str) -> None:
    """Verify DB state after ordinal resolution."""
    with Session(engine) as session:
        atomics = session.exec(
            select(AtomicCriterion)
            .join(
                Criteria,
                AtomicCriterion.criterion_id == Criteria.id,
            )
            .where(Criteria.batch_id == batch_id)
        ).all()

        print(f"AtomicCriteria in batch: {len(atomics)}\n")
        for a in atomics:
            marker = ""
            if a.unit_concept_id == 8527:
                marker = " << {score}"
            elif a.unit_concept_id is not None:
                marker = f" << unit={a.unit_concept_id}"
            print(
                f"  {a.original_text!r}"
                f"\n    unit_concept_id={a.unit_concept_id}"
                f"  value_numeric={a.value_numeric}"
                f"  unit_text={a.unit_text!r}{marker}"
            )
            print()

        audits = session.exec(
            select(AuditLog).where(
                AuditLog.event_type == "ordinal_scale_proposed",
                AuditLog.target_id == batch_id,
            )
        ).all()
        if audits:
            print(f"AuditLog entries: {len(audits)}")
            for audit in audits:
                details = audit.details
                print(
                    f"  candidates_found={details.get('candidates_found')}"
                    f"  updated={details.get('updated_count')}"
                    f"  proposals="
                    f"{len(details.get('proposals', []))}"
                )
        else:
            print("No AuditLog entries found")


async def main() -> None:
    """Run full E2E ordinal resolution pipeline."""
    _sep("PHASE 1: Create protocol & build expression trees")

    with Session(engine) as session:
        protocol_id, batch_id = _phase1_create(session)
        print(f"Protocol: {protocol_id}")
        print(f"Batch:    {batch_id}")
        await _phase1_build(session, protocol_id, batch_id)

    _sep("PHASE 2: Run ordinal_resolve_node (REAL Gemini)")

    state = {
        "protocol_id": protocol_id,
        "batch_id": batch_id,
        "error": None,
        "errors": [],
    }

    result = await ordinal_resolve_node(state)  # type: ignore[arg-type]

    print(f"Status: {result.get('status')}")
    print(f"Errors: {result.get('errors', [])}")
    _print_proposals(result)

    _sep("PHASE 3: Verify DB state")
    _phase3_verify(batch_id)

    _sep("DONE")


if __name__ == "__main__":
    asyncio.run(main())
