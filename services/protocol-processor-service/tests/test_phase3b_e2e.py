"""Phase 3b E2E: Ordinal scale normalization through the full backend.

Feeds realistic ordinal criteria (ECOG, Karnofsky, NYHA) through
build_expression_tree and verifies that unit_concept_id=8527 ({score})
is correctly populated, value parsing works, and non-ordinal criteria
are unaffected.

Also tests the propose_ordinal_mappings() agent utility.
"""

from __future__ import annotations

import os
from typing import Any, Generator
from unittest.mock import patch

import pytest
from shared.models import AtomicCriterion, Criteria, CriteriaBatch, Protocol
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from protocol_processor.tools.structure_builder import build_expression_tree
from protocol_processor.tools.unit_normalizer import (
    normalize_ordinal_value,
    propose_ordinal_mappings,
)

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


@pytest.fixture()
def session(engine) -> Generator[Session, None, None]:
    s = Session(engine)
    try:
        yield s
    finally:
        s.close()


def _setup(session: Session) -> tuple[str, str]:
    protocol = Protocol(title="NCT-ORDINAL-E2E", file_uri="local://test.pdf")
    session.add(protocol)
    session.flush()
    batch = CriteriaBatch(protocol_id=protocol.id)
    session.add(batch)
    session.flush()
    return protocol.id, batch.id


def _make_crit(session: Session, batch_id: str, text: str) -> Criteria:
    c = Criteria(batch_id=batch_id, criteria_type="inclusion", text=text)
    session.add(c)
    session.flush()
    return c


# ---------------------------------------------------------------------------
# Ordinal criteria test data
# ---------------------------------------------------------------------------

ORDINAL_CRITERIA: list[dict[str, Any]] = [
    # ECOG — standard oncology eligibility
    {
        "text": "ECOG performance status <= 2",
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
        "expect": {
            "unit_concept_id": 8527,
            "value_numeric": 2.0,
        },
    },
    # ECOG — using short alias "ECOG PS"
    {
        "text": "ECOG PS 0 or 1",
        "mappings": [
            {
                "entity": "ECOG PS",
                "relation": "<=",
                "value": "1",
                "unit": None,
                "entity_concept_id": "C1520224",
                "entity_concept_system": "umls",
                "omop_concept_id": "4174241",
            },
        ],
        "expect": {
            "unit_concept_id": 8527,
            "value_numeric": 1.0,
        },
    },
    # Karnofsky — performance status
    {
        "text": "Karnofsky performance status >= 70",
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
        "expect": {
            "unit_concept_id": 8527,
            "value_numeric": 70.0,
        },
    },
    # Karnofsky — short alias "KPS"
    {
        "text": "KPS >= 60",
        "mappings": [
            {
                "entity": "KPS",
                "relation": ">=",
                "value": "60",
                "unit": None,
                "entity_concept_id": "C0206065",
                "entity_concept_system": "umls",
                "omop_concept_id": "4174245",
            },
        ],
        "expect": {
            "unit_concept_id": 8527,
            "value_numeric": 60.0,
        },
    },
    # NYHA — cardiology
    {
        "text": "NYHA functional class <= III",
        "mappings": [
            {
                "entity": "NYHA functional class",
                "relation": "<=",
                "value": "3",
                "unit": None,
                "entity_concept_id": "C0027774",
                "entity_concept_system": "umls",
                "omop_concept_id": "4173632",
            },
        ],
        "expect": {
            "unit_concept_id": 8527,
            "value_numeric": 3.0,
        },
    },
    # NYHA — short alias
    {
        "text": "NYHA class I or II",
        "mappings": [
            {
                "entity": "NYHA class",
                "relation": "<=",
                "value": "2",
                "unit": None,
                "entity_concept_id": "C0027774",
                "entity_concept_system": "umls",
                "omop_concept_id": "4173632",
            },
        ],
        "expect": {
            "unit_concept_id": 8527,
            "value_numeric": 2.0,
        },
    },
    # Non-ordinal: HbA1c (should NOT get ordinal treatment)
    {
        "text": "HbA1c <= 10%",
        "mappings": [
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
        "expect": {
            "unit_concept_id": 8554,  # % — NOT 8527
            "value_numeric": 10.0,
        },
    },
    # Non-ordinal: categorical HIV status (should NOT get ordinal treatment)
    {
        "text": "HIV status positive",
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
        "expect": {
            "unit_concept_id": None,
            "value_concept_id": 45884084,  # positive
        },
    },
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPhase3bOrdinalE2E:
    """E2E: ordinal criteria through build_expression_tree → DB."""

    async def test_ordinal_criteria_get_score_unit(self, session) -> None:
        """All ordinal criteria get unit_concept_id=8527 ({score})."""
        protocol_id, batch_id = _setup(session)

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_API_KEY", None)

            for i, crit_def in enumerate(ORDINAL_CRITERIA):
                crit = _make_crit(session, batch_id, crit_def["text"])
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
                        AtomicCriterion.criterion_id == crit.id
                    )
                ).all()
                assert len(atomics) == 1, f"Criterion {i}: expected 1 atomic"

                a = atomics[0]
                exp = crit_def["expect"]

                assert a.unit_concept_id == exp["unit_concept_id"], (
                    f"Criterion {i} ({crit_def['text']}): "
                    f"unit_concept_id={a.unit_concept_id}, "
                    f"expected {exp['unit_concept_id']}"
                )

                if "value_numeric" in exp:
                    assert a.value_numeric == pytest.approx(exp["value_numeric"]), (
                        f"Criterion {i}: value_numeric"
                    )

                if "value_concept_id" in exp:
                    assert a.value_concept_id == exp["value_concept_id"], (
                        f"Criterion {i}: value_concept_id"
                    )

        session.commit()

    async def test_ecog_grade_prefix_through_backend(self, session) -> None:
        """'Grade 2' value text resolves through full backend path."""
        protocol_id, batch_id = _setup(session)

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_API_KEY", None)

            crit = _make_crit(session, batch_id, "ECOG Grade 2")
            await build_expression_tree(
                criterion_text="ECOG Grade 2",
                field_mappings=[
                    {
                        "entity": "ECOG",
                        "relation": "=",
                        "value": "Grade 2",
                        "unit": None,
                    },
                ],
                criterion_id=crit.id,
                protocol_id=protocol_id,
                inclusion_exclusion="inclusion",
                session=session,
            )
            session.flush()

            atomics = session.exec(
                select(AtomicCriterion).where(AtomicCriterion.criterion_id == crit.id)
            ).all()
            assert len(atomics) == 1
            # "Grade 2" parses to numeric because _parse_value can't parse it,
            # so value_text="Grade 2" and value_numeric=None
            # But the ordinal normalizer still matches the entity and sets
            # unit_concept_id=8527
            assert atomics[0].unit_concept_id == 8527

    async def test_ecog_float_value_through_backend(self, session) -> None:
        """'2.0' value resolves to grade 2 through full backend."""
        protocol_id, batch_id = _setup(session)

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_API_KEY", None)

            crit = _make_crit(session, batch_id, "ECOG 2.0")
            await build_expression_tree(
                criterion_text="ECOG <= 2.0",
                field_mappings=[
                    {
                        "entity": "ECOG performance status",
                        "relation": "<=",
                        "value": "2.0",
                        "unit": None,
                    },
                ],
                criterion_id=crit.id,
                protocol_id=protocol_id,
                inclusion_exclusion="inclusion",
                session=session,
            )
            session.flush()

            atomics = session.exec(
                select(AtomicCriterion).where(AtomicCriterion.criterion_id == crit.id)
            ).all()
            assert len(atomics) == 1
            assert atomics[0].unit_concept_id == 8527
            assert atomics[0].value_numeric == pytest.approx(2.0)

    async def test_mixed_ordinal_and_lab_criteria(self, session) -> None:
        """Mixed criteria: ordinal + lab values in same batch work correctly."""
        protocol_id, batch_id = _setup(session)

        mixed = [
            # Ordinal
            {
                "text": "ECOG <= 1",
                "mappings": [
                    {
                        "entity": "ECOG",
                        "relation": "<=",
                        "value": "1",
                        "unit": None,
                    },
                ],
            },
            # Lab value
            {
                "text": "Creatinine <= 1.5 mg/dL",
                "mappings": [
                    {
                        "entity": "Serum creatinine",
                        "relation": "<=",
                        "value": "1.5",
                        "unit": "mg/dL",
                    },
                ],
            },
            # Another ordinal
            {
                "text": "NYHA class <= 2",
                "mappings": [
                    {
                        "entity": "NYHA class",
                        "relation": "<=",
                        "value": "2",
                        "unit": None,
                    },
                ],
            },
        ]

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_API_KEY", None)

            crit_ids = []
            for crit_def in mixed:
                crit = _make_crit(session, batch_id, crit_def["text"])
                crit_ids.append(crit.id)
                await build_expression_tree(
                    criterion_text=crit_def["text"],
                    field_mappings=crit_def["mappings"],
                    criterion_id=crit.id,
                    protocol_id=protocol_id,
                    inclusion_exclusion="inclusion",
                    session=session,
                )
                session.flush()

        session.commit()

        # ECOG: unit_concept_id=8527
        ecog = session.exec(
            select(AtomicCriterion).where(AtomicCriterion.criterion_id == crit_ids[0])
        ).first()
        assert ecog is not None
        assert ecog.unit_concept_id == 8527

        # Creatinine: unit_concept_id=8840 (mg/dL)
        creat = session.exec(
            select(AtomicCriterion).where(AtomicCriterion.criterion_id == crit_ids[1])
        ).first()
        assert creat is not None
        assert creat.unit_concept_id == 8840

        # NYHA: unit_concept_id=8527
        nyha = session.exec(
            select(AtomicCriterion).where(AtomicCriterion.criterion_id == crit_ids[2])
        ).first()
        assert nyha is not None
        assert nyha.unit_concept_id == 8527


class TestProposeOrdinalMappingsE2E:
    """Test the agent proposal utility end-to-end."""

    def test_all_grades_need_resolution(self) -> None:
        """Since no omop_value_concept_id is set, all grades need resolution."""
        missing = propose_ordinal_mappings()
        assert len(missing) > 0

        # Should include entries from all 3 scales
        scales = {e["scale"] for e in missing}
        assert "ecog" in scales
        assert "karnofsky" in scales
        assert "nyha" in scales

    def test_ecog_grades_in_proposals(self) -> None:
        """All 6 ECOG grades appear in proposals."""
        missing = propose_ordinal_mappings()
        ecog_grades = {e["grade"] for e in missing if e["scale"] == "ecog"}
        assert ecog_grades == {"0", "1", "2", "3", "4", "5"}

    def test_proposals_have_snomed_codes(self) -> None:
        """ECOG proposals include SNOMED codes from YAML."""
        missing = propose_ordinal_mappings()
        ecog_entries = [e for e in missing if e["scale"] == "ecog"]
        snomed_codes = [e["snomed_code"] for e in ecog_entries if e["snomed_code"]]
        # All 6 ECOG grades have SNOMED codes
        assert len(snomed_codes) == 6

    def test_karnofsky_proposals_no_snomed(self) -> None:
        """Karnofsky proposals have no SNOMED codes (not in YAML)."""
        missing = propose_ordinal_mappings()
        kps_entries = [e for e in missing if e["scale"] == "karnofsky"]
        assert all(e["snomed_code"] is None for e in kps_entries)


class TestNormalizeOrdinalDirectE2E:
    """Direct normalize_ordinal_value() tests with various real-world inputs."""

    def test_who_performance_status_alias(self) -> None:
        """'WHO performance status' is an ECOG alias."""
        result = normalize_ordinal_value("1", "WHO performance status")
        assert result is not None
        _, unit_cid = result
        assert unit_cid == 8527

    def test_zubrod_score_alias(self) -> None:
        """'Zubrod score' is an ECOG alias."""
        result = normalize_ordinal_value("0", "Zubrod score")
        assert result is not None
        _, unit_cid = result
        assert unit_cid == 8527

    def test_eastern_cooperative_oncology_group(self) -> None:
        """Full formal name matches."""
        result = normalize_ordinal_value("2", "Eastern Cooperative Oncology Group")
        assert result is not None
        _, unit_cid = result
        assert unit_cid == 8527

    def test_new_york_heart_association(self) -> None:
        """Full NYHA name matches."""
        result = normalize_ordinal_value("1", "New York Heart Association")
        assert result is not None
        _, unit_cid = result
        assert unit_cid == 8527

    def test_karnofsky_performance_scale(self) -> None:
        """Alternative Karnofsky alias."""
        result = normalize_ordinal_value("90", "Karnofsky performance scale")
        assert result is not None
        _, unit_cid = result
        assert unit_cid == 8527

    def test_empty_value_still_identifies_scale(self) -> None:
        """Empty value with ordinal entity still returns unit_concept_id."""
        result = normalize_ordinal_value("", "ECOG")
        assert result is not None
        value_cid, unit_cid = result
        assert value_cid is None
        assert unit_cid == 8527

    def test_none_value_still_identifies_scale(self) -> None:
        """None value with ordinal entity still returns unit_concept_id."""
        result = normalize_ordinal_value(None, "ECOG")
        assert result is not None
        value_cid, unit_cid = result
        assert value_cid is None
        assert unit_cid == 8527

    def test_score_prefix_strip(self) -> None:
        """'Score 3' strips prefix for ECOG."""
        result = normalize_ordinal_value("Score 3", "ECOG")
        assert result is not None
        _, unit_cid = result
        assert unit_cid == 8527

    def test_level_prefix_strip(self) -> None:
        """'Level 2' strips prefix."""
        result = normalize_ordinal_value("Level 2", "NYHA")
        assert result is not None
        _, unit_cid = result
        assert unit_cid == 8527
