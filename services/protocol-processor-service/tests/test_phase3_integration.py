"""Phase 3 Integration: Run realistic clinical criteria through the backend.

Feeds representative inclusion/exclusion criteria (as field_mappings) through
build_expression_tree and verifies that entities, relations, values, units,
unit_concept_id, and value_concept_id are all correctly populated in the DB.

These field_mappings simulate what the ground node would produce for real
clinical trial protocols.
"""

from __future__ import annotations

import gc
import os
from typing import Any, Generator
from unittest.mock import patch

import pytest
from shared.models import AtomicCriterion, Criteria, CriteriaBatch, Protocol
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from protocol_processor.tools.structure_builder import build_expression_tree

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    import shared.models  # noqa: F401

    SQLModel.metadata.create_all(eng)
    try:
        yield eng
    finally:
        eng.dispose()
        gc.collect()


@pytest.fixture()
def session(engine) -> Generator[Session, None, None]:
    s = Session(engine)
    try:
        yield s
    finally:
        s.close()


def _setup_parent(
    session: Session,
) -> tuple[str, str, str]:
    """Create Protocol + CriteriaBatch, return (protocol_id, batch_id)."""
    protocol = Protocol(title="NCT00001234", file_uri="local://test.pdf")
    session.add(protocol)
    session.flush()
    batch = CriteriaBatch(protocol_id=protocol.id)
    session.add(batch)
    session.flush()
    return protocol.id, batch.id


def _make_criterion(
    session: Session,
    batch_id: str,
    text: str,
    criteria_type: str = "inclusion",
) -> Criteria:
    crit = Criteria(batch_id=batch_id, criteria_type=criteria_type, text=text)
    session.add(crit)
    session.flush()
    return crit


# ---------------------------------------------------------------------------
# Realistic clinical trial criteria
# ---------------------------------------------------------------------------

CRITERIA: list[dict[str, Any]] = [
    # 1. Lab value with % unit
    {
        "text": "HbA1c >= 6.5% and <= 10%",
        "type": "inclusion",
        "mappings": [
            {
                "entity": "HbA1c",
                "relation": ">=",
                "value": "6.5",
                "unit": "%",
                "entity_concept_id": "2345-7",
                "entity_concept_system": "loinc",
                "omop_concept_id": "3004410",
            },
            {
                "entity": "HbA1c",
                "relation": "<=",
                "value": "10",
                "unit": "%",
                "entity_concept_id": "2345-7",
                "entity_concept_system": "loinc",
                "omop_concept_id": "3004410",
            },
        ],
    },
    # 2. Age with years unit
    {
        "text": "Age >= 18 years and <= 75 years",
        "type": "inclusion",
        "mappings": [
            {
                "entity": "Age",
                "relation": ">=",
                "value": "18",
                "unit": "years",
                "entity_concept_id": "C0001779",
                "entity_concept_system": "umls",
                "omop_concept_id": "4265453",
            },
            {
                "entity": "Age",
                "relation": "<=",
                "value": "75",
                "unit": "years",
                "entity_concept_id": "C0001779",
                "entity_concept_system": "umls",
                "omop_concept_id": "4265453",
            },
        ],
    },
    # 3. eGFR with mL/min/1.73m2 unit
    {
        "text": "eGFR >= 30 mL/min/1.73m2",
        "type": "inclusion",
        "mappings": [
            {
                "entity": "eGFR",
                "relation": ">=",
                "value": "30",
                "unit": "mL/min/1.73m2",
                "entity_concept_id": "C0017654",
                "entity_concept_system": "umls",
                "omop_concept_id": "3049187",
            },
        ],
    },
    # 4. BMI with kg/m2 unit
    {
        "text": "BMI between 18.5 and 35 kg/m2",
        "type": "inclusion",
        "mappings": [
            {
                "entity": "BMI",
                "relation": ">=",
                "value": "18.5",
                "unit": "kg/m2",
                "entity_concept_id": "C0005893",
                "entity_concept_system": "umls",
                "omop_concept_id": "3038553",
            },
            {
                "entity": "BMI",
                "relation": "<=",
                "value": "35",
                "unit": "kg/m2",
                "entity_concept_id": "C0005893",
                "entity_concept_system": "umls",
                "omop_concept_id": "3038553",
            },
        ],
    },
    # 5. Blood pressure with mmHg unit
    {
        "text": "Systolic blood pressure <= 160 mmHg",
        "type": "inclusion",
        "mappings": [
            {
                "entity": "Systolic blood pressure",
                "relation": "<=",
                "value": "160",
                "unit": "mmHg",
                "entity_concept_id": "C0871470",
                "entity_concept_system": "umls",
                "omop_concept_id": "3004249",
            },
        ],
    },
    # 6. Platelet count with cell count unit
    {
        "text": "Platelet count >= 100 x10^3/uL",
        "type": "inclusion",
        "mappings": [
            {
                "entity": "Platelet count",
                "relation": ">=",
                "value": "100",
                "unit": "10*3/uL",
                "entity_concept_id": "C0032181",
                "entity_concept_system": "umls",
                "omop_concept_id": "3024929",
            },
        ],
    },
    # 7. Categorical value: HIV status positive (exclusion)
    {
        "text": "HIV status is positive",
        "type": "exclusion",
        "mappings": [
            {
                "entity": "HIV status",
                "relation": "is",
                "value": "positive",
                "unit": None,
                "entity_concept_id": "C0019693",
                "entity_concept_system": "umls",
                "omop_concept_id": "439727",
            },
        ],
    },
    # 8. Categorical value: Hepatitis B surface antigen negative
    {
        "text": "Hepatitis B surface antigen is negative",
        "type": "exclusion",
        "mappings": [
            {
                "entity": "Hepatitis B surface antigen",
                "relation": "is",
                "value": "negative",
                "unit": None,
                "entity_concept_id": "C0019168",
                "entity_concept_system": "umls",
                "omop_concept_id": "4027133",
            },
        ],
    },
    # 9. Lab value with mg/dL
    {
        "text": "Serum creatinine <= 1.5 mg/dL",
        "type": "inclusion",
        "mappings": [
            {
                "entity": "Serum creatinine",
                "relation": "<=",
                "value": "1.5",
                "unit": "mg/dL",
                "entity_concept_id": "2160-0",
                "entity_concept_system": "loinc",
                "omop_concept_id": "3016723",
            },
        ],
    },
    # 10. Lab value with mmol/L
    {
        "text": "Fasting glucose < 7.0 mmol/L",
        "type": "inclusion",
        "mappings": [
            {
                "entity": "Fasting glucose",
                "relation": "<",
                "value": "7.0",
                "unit": "mmol/L",
                "entity_concept_id": "C0015965",
                "entity_concept_system": "umls",
                "omop_concept_id": "3004501",
            },
        ],
    },
    # 11. Unrecognized unit — should produce None concept IDs
    {
        "text": "ECOG performance status <= 2",
        "type": "inclusion",
        "mappings": [
            {
                "entity": "ECOG performance status",
                "relation": "<=",
                "value": "2",
                "unit": None,
                "entity_concept_id": "C1520224",
                "entity_concept_system": "umls",
                "omop_concept_id": "4174241",
            },
        ],
    },
    # 12. Karnofsky performance status (ordinal scale)
    {
        "text": "Karnofsky performance status >= 70",
        "type": "inclusion",
        "mappings": [
            {
                "entity": "Karnofsky performance status",
                "relation": ">=",
                "value": "70",
                "unit": None,
                "entity_concept_id": "C0206065",
                "entity_concept_system": "umls",
                "omop_concept_id": "4174245",
            },
        ],
    },
    # 13. WBC with 10*9/L
    {
        "text": "WBC >= 3.0 x 10^9/L",
        "type": "inclusion",
        "mappings": [
            {
                "entity": "WBC",
                "relation": ">=",
                "value": "3.0",
                "unit": "10*9/L",
                "entity_concept_id": "C0023508",
                "entity_concept_system": "umls",
                "omop_concept_id": "3000905",
            },
        ],
    },
]

# Expected results per mapping (index into flat list of all mappings)
EXPECTED: list[dict[str, Any]] = [
    # 1a: HbA1c >= 6.5%
    {
        "entity_concept_id": "2345-7",
        "relation_operator": ">=",
        "value_numeric": 6.5,
        "value_text": None,
        "unit_text": "%",
        "unit_concept_id": 8554,
        "value_concept_id": None,
    },
    # 1b: HbA1c <= 10%
    {
        "entity_concept_id": "2345-7",
        "relation_operator": "<=",
        "value_numeric": 10.0,
        "unit_text": "%",
        "unit_concept_id": 8554,
        "value_concept_id": None,
    },
    # 2a: Age >= 18 years
    {
        "entity_concept_id": "C0001779",
        "relation_operator": ">=",
        "value_numeric": 18.0,
        "unit_text": "years",
        "unit_concept_id": 9448,
        "value_concept_id": None,
    },
    # 2b: Age <= 75 years
    {
        "entity_concept_id": "C0001779",
        "relation_operator": "<=",
        "value_numeric": 75.0,
        "unit_text": "years",
        "unit_concept_id": 9448,
        "value_concept_id": None,
    },
    # 3: eGFR >= 30 mL/min/1.73m2
    {
        "entity_concept_id": "C0017654",
        "relation_operator": ">=",
        "value_numeric": 30.0,
        "unit_text": "mL/min/1.73m2",
        "unit_concept_id": 720870,
        "value_concept_id": None,
    },
    # 4a: BMI >= 18.5 kg/m2
    {
        "entity_concept_id": "C0005893",
        "relation_operator": ">=",
        "value_numeric": 18.5,
        "unit_text": "kg/m2",
        "unit_concept_id": 9531,
        "value_concept_id": None,
    },
    # 4b: BMI <= 35 kg/m2
    {
        "entity_concept_id": "C0005893",
        "relation_operator": "<=",
        "value_numeric": 35.0,
        "unit_text": "kg/m2",
        "unit_concept_id": 9531,
        "value_concept_id": None,
    },
    # 5: SBP <= 160 mmHg
    {
        "entity_concept_id": "C0871470",
        "relation_operator": "<=",
        "value_numeric": 160.0,
        "unit_text": "mmHg",
        "unit_concept_id": 8876,
        "value_concept_id": None,
    },
    # 6: Platelet count >= 100 10*3/uL
    {
        "entity_concept_id": "C0032181",
        "relation_operator": ">=",
        "value_numeric": 100.0,
        "unit_text": "10*3/uL",
        "unit_concept_id": 8848,
        "value_concept_id": None,
    },
    # 7: HIV status is positive (categorical)
    {
        "entity_concept_id": "C0019693",
        "relation_operator": "is",
        "value_numeric": None,
        "value_text": "positive",
        "unit_text": None,
        "unit_concept_id": None,
        "value_concept_id": 45884084,
    },
    # 8: HBsAg is negative (categorical)
    {
        "entity_concept_id": "C0019168",
        "relation_operator": "is",
        "value_numeric": None,
        "value_text": "negative",
        "unit_text": None,
        "unit_concept_id": None,
        "value_concept_id": 45878583,
    },
    # 9: Serum creatinine <= 1.5 mg/dL
    {
        "entity_concept_id": "2160-0",
        "relation_operator": "<=",
        "value_numeric": 1.5,
        "unit_text": "mg/dL",
        "unit_concept_id": 8840,
        "value_concept_id": None,
    },
    # 10: Fasting glucose < 7.0 mmol/L
    {
        "entity_concept_id": "C0015965",
        "relation_operator": "<",
        "value_numeric": 7.0,
        "unit_text": "mmol/L",
        "unit_concept_id": 8753,
        "value_concept_id": None,
    },
    # 11: ECOG <= 2 (ordinal scale — unit_concept_id=8527 via Phase 3b)
    {
        "entity_concept_id": "C1520224",
        "relation_operator": "<=",
        "value_numeric": 2.0,
        "unit_text": None,
        "unit_concept_id": 8527,
        "value_concept_id": None,
    },
    # 12: Karnofsky >= 70 (ordinal scale — unit_concept_id=8527 via Phase 3b)
    {
        "entity_concept_id": "C0206065",
        "relation_operator": ">=",
        "value_numeric": 70.0,
        "unit_text": None,
        "unit_concept_id": 8527,
        "value_concept_id": None,
    },
    # 13: WBC >= 3.0 10*9/L
    {
        "entity_concept_id": "C0023508",
        "relation_operator": ">=",
        "value_numeric": 3.0,
        "unit_text": "10*9/L",
        "unit_concept_id": 9444,
        "value_concept_id": None,
    },
]


# ===========================================================================
# Tests
# ===========================================================================


class TestPhase3RealisticCriteria:
    """Run 12 realistic clinical trial criteria through the backend."""

    async def test_all_criteria_processed(self, session) -> None:
        """All 12 criteria produce correct AtomicCriterion records."""
        protocol_id, batch_id = _setup_parent(session)
        all_atomics: list[AtomicCriterion] = []

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_API_KEY", None)

            for crit_def in CRITERIA:
                crit = _make_criterion(
                    session,
                    batch_id,
                    crit_def["text"],
                    crit_def["type"],
                )
                await build_expression_tree(
                    criterion_text=crit_def["text"],
                    field_mappings=crit_def["mappings"],
                    criterion_id=crit.id,
                    protocol_id=protocol_id,
                    inclusion_exclusion=crit_def["type"],
                    session=session,
                )
                session.flush()

                # Collect atomics for this criterion
                atomics = session.exec(
                    select(AtomicCriterion).where(
                        AtomicCriterion.criterion_id == crit.id
                    )
                ).all()
                all_atomics.extend(atomics)

        session.commit()

        # Total expected: sum of mappings across all criteria
        total_mappings = sum(len(c["mappings"]) for c in CRITERIA)
        assert len(all_atomics) == total_mappings, (
            f"Expected {total_mappings} atomics, got {len(all_atomics)}"
        )

        # Verify each atomic against expected values
        for i, (atomic, exp) in enumerate(zip(all_atomics, EXPECTED)):
            label = f"Atomic #{i}"
            assert atomic.entity_concept_id == exp["entity_concept_id"], (
                f"{label}: entity_concept_id"
            )
            assert atomic.relation_operator == exp["relation_operator"], (
                f"{label}: relation_operator"
            )
            assert atomic.unit_text == exp.get("unit_text"), f"{label}: unit_text"
            assert atomic.unit_concept_id == exp["unit_concept_id"], (
                f"{label}: unit_concept_id "
                f"(got {atomic.unit_concept_id}, "
                f"expected {exp['unit_concept_id']} "
                f"for unit '{atomic.unit_text}')"
            )
            assert atomic.value_concept_id == exp["value_concept_id"], (
                f"{label}: value_concept_id "
                f"(got {atomic.value_concept_id}, "
                f"expected {exp['value_concept_id']} "
                f"for value '{atomic.value_text}')"
            )
            if exp.get("value_numeric") is not None:
                assert atomic.value_numeric == pytest.approx(exp["value_numeric"]), (
                    f"{label}: value_numeric"
                )
            else:
                assert atomic.value_numeric is None, (
                    f"{label}: value_numeric should be None"
                )
            if "value_text" in exp:
                assert atomic.value_text == exp["value_text"], f"{label}: value_text"

    async def test_inclusion_exclusion_correct(self, session) -> None:
        """Criteria correctly tagged as inclusion or exclusion."""
        protocol_id, batch_id = _setup_parent(session)

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_API_KEY", None)

            for crit_def in CRITERIA:
                crit = _make_criterion(
                    session,
                    batch_id,
                    crit_def["text"],
                    crit_def["type"],
                )
                await build_expression_tree(
                    criterion_text=crit_def["text"],
                    field_mappings=crit_def["mappings"],
                    criterion_id=crit.id,
                    protocol_id=protocol_id,
                    inclusion_exclusion=crit_def["type"],
                    session=session,
                )

        session.commit()

        inclusion_atomics = session.exec(
            select(AtomicCriterion).where(
                AtomicCriterion.inclusion_exclusion == "inclusion"
            )
        ).all()
        exclusion_atomics = session.exec(
            select(AtomicCriterion).where(
                AtomicCriterion.inclusion_exclusion == "exclusion"
            )
        ).all()

        # Criteria 7 and 8 are exclusion (1 mapping each = 2 atomics)
        assert len(exclusion_atomics) == 2
        # All others are inclusion (14 mappings total)
        assert len(inclusion_atomics) == 14

    async def test_unit_coverage_summary(self, session) -> None:
        """Print a coverage summary of all units processed."""
        protocol_id, batch_id = _setup_parent(session)

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_API_KEY", None)

            for crit_def in CRITERIA:
                crit = _make_criterion(
                    session,
                    batch_id,
                    crit_def["text"],
                    crit_def["type"],
                )
                await build_expression_tree(
                    criterion_text=crit_def["text"],
                    field_mappings=crit_def["mappings"],
                    criterion_id=crit.id,
                    protocol_id=protocol_id,
                    inclusion_exclusion=crit_def["type"],
                    session=session,
                )

        session.commit()

        all_atomics = session.exec(select(AtomicCriterion)).all()

        resolved = [a for a in all_atomics if a.unit_concept_id is not None]
        unresolved_with_unit = [
            a
            for a in all_atomics
            if a.unit_text is not None and a.unit_concept_id is None
        ]
        no_unit = [a for a in all_atomics if a.unit_text is None]
        value_resolved = [a for a in all_atomics if a.value_concept_id is not None]

        # Verify we got good coverage
        # 14 mappings have unit_concept_id (12 explicit units +
        # ECOG {score} + Karnofsky {score} via ordinal normalizer)
        assert len(resolved) == 14
        assert len(unresolved_with_unit) == 0  # no unrecognized units
        # 4 with unit_text=None: HIV, HBsAg, ECOG, Karnofsky
        # (ECOG/Karnofsky get unit_concept_id from ordinal dispatch, not unit_text)
        assert len(no_unit) == 4
        assert len(value_resolved) == 2  # positive + negative
