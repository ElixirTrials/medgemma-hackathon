"""Full-cycle E2E test: Lookup → Agent → Approve → Persist.

Demonstrates the complete ordinal resolution lifecycle:

Run 1 (unknown scale):
  1. Child-Pugh criterion through build_expression_tree
     → normalize_ordinal_value() returns None (not in alias dict)
     → AtomicCriterion.unit_concept_id = None
  2. ordinal_resolve_node fires → LLM (mocked) confirms ordinal
     → unit_concept_id updated to 8527
     → AuditLog proposal written for human review

Simulated approval:
  3. Add Child-Pugh to ordinal scale aliases (simulates human approval)

Run 2 (known scale):
  4. New Child-Pugh criterion through build_expression_tree
     → normalize_ordinal_value() NOW matches (in alias dict)
     → AtomicCriterion.unit_concept_id = 8527 at creation time
  5. ordinal_resolve_node finds no candidates → no LLM call
"""

from __future__ import annotations

import json
import os
from typing import Any, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from shared.models import (
    AtomicCriterion,
    AuditLog,
    Criteria,
    CriteriaBatch,
    Protocol,
)
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from protocol_processor.schemas.ordinal import (
    OrdinalResolutionResponse,
    OrdinalScaleProposal,
)
from protocol_processor.tools.structure_builder import (
    build_expression_tree,
)
from protocol_processor.tools.unit_normalizer import (
    ORDINAL_SCALE_ALIASES,
    _cached_ucum_lookup,
    _cached_value_lookup,
    normalize_ordinal_value,
)

# ---------------------------------------------------------------------------
# Mock DB data
# ---------------------------------------------------------------------------

_MOCK_UCUM: dict[str, tuple[str, int]] = {
    "%": ("%", 8554),
    "mg/dl": ("mg/dL", 8840),
    "{score}": ("{score}", 8527),
    "score": ("{score}", 8527),
}

_MOCK_VALUES: dict[str, tuple[str, int]] = {
    "positive": ("positive", 45884084),
}


def _mock_lookup_ucum_unit(
    _engine: object, unit_text: str
) -> tuple[str | None, int | None]:
    key = unit_text.strip().lower()
    return _MOCK_UCUM.get(key, (None, None))


def _mock_lookup_value_concept(
    _engine: object, value_text: str
) -> tuple[str | None, int | None]:
    key = value_text.strip().lower()
    return _MOCK_VALUES.get(key, (None, None))


def _mock_lookup_ordinal_concept(
    _engine: object, scale_name: str, grade: str
) -> int | None:
    return None


def _patch_db():
    engine_mock = MagicMock()
    return (
        patch(
            "protocol_processor.tools.omop_mapper._get_omop_engine",
            return_value=engine_mock,
        ),
        patch(
            "protocol_processor.tools.omop_mapper._lookup_ucum_unit",
            side_effect=_mock_lookup_ucum_unit,
        ),
        patch(
            "protocol_processor.tools.omop_mapper._lookup_value_concept",
            side_effect=_mock_lookup_value_concept,
        ),
        patch(
            "protocol_processor.tools.omop_mapper._lookup_ordinal_concept",
            side_effect=_mock_lookup_ordinal_concept,
        ),
    )


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_caches():
    """Clear LRU caches before each test."""
    _cached_ucum_lookup.cache_clear()
    _cached_value_lookup.cache_clear()
    yield
    _cached_ucum_lookup.cache_clear()
    _cached_value_lookup.cache_clear()


@pytest.fixture()
def engine():
    eng = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
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


# ── Helpers ───────────────────────────────────────────────────────────


def _setup(session: Session) -> tuple[str, str]:
    protocol = Protocol(
        title="NCT-FULL-CYCLE",
        file_uri="local://test.pdf",
    )
    session.add(protocol)
    session.flush()
    batch = CriteriaBatch(protocol_id=protocol.id)
    session.add(batch)
    session.flush()
    return protocol.id, batch.id


def _make_crit(
    session: Session,
    batch_id: str,
    text: str,
) -> Criteria:
    c = Criteria(
        batch_id=batch_id,
        criteria_type="inclusion",
        text=text,
    )
    session.add(c)
    session.flush()
    return c


# ── Full Cycle Test ───────────────────────────────────────────────────


class TestOrdinalFullCycle:
    """Full Lookup → Agent → Approve → Persist cycle."""

    async def test_full_cycle_child_pugh(
        self,
        engine,
        session,
    ) -> None:
        """Child-Pugh: unknown → LLM resolve → approve → static lookup."""
        protocol_id, batch_id = _setup(session)

        p1, p2, p3, p4 = _patch_db()

        # ── Phase 1: Static Lookup (MISS) ─────────────────────────
        # Child-Pugh is NOT in the alias dict
        with p1, p2, p3, p4:
            assert normalize_ordinal_value("6", "Child-Pugh score") is None

        # Build expression tree — creates AtomicCriterion with
        # unit_concept_id=None (no alias match, no physical unit)
        crit1 = _make_crit(
            session,
            batch_id,
            "Child-Pugh score <= 6",
        )
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4, patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_API_KEY", None)
            await build_expression_tree(
                criterion_text="Child-Pugh score <= 6",
                field_mappings=[
                    {
                        "entity": "Child-Pugh score",
                        "relation": "<=",
                        "value": "6",
                        "unit": None,
                    }
                ],
                criterion_id=crit1.id,
                protocol_id=protocol_id,
                inclusion_exclusion="inclusion",
                session=session,
            )
        session.flush()

        atomic1 = session.exec(
            select(AtomicCriterion).where(
                AtomicCriterion.criterion_id == crit1.id,
            )
        ).first()
        assert atomic1 is not None
        assert atomic1.unit_concept_id is None, (
            "Before LLM resolve: unit_concept_id should be None"
        )
        assert atomic1.value_numeric == pytest.approx(6.0)
        session.commit()

        # ── Phase 2: Agent Resolve (LLM) ──────────────────────────
        mock_response = OrdinalResolutionResponse(
            proposals=[
                OrdinalScaleProposal(
                    entity_text="Child-Pugh score",
                    is_ordinal_scale=True,
                    confidence=0.95,
                    scale_name="child_pugh",
                    entity_aliases=[
                        "Child-Pugh",
                        "Child-Pugh classification",
                    ],
                    loinc_code="75622-1",
                ),
            ],
        )

        from protocol_processor.nodes.ordinal_resolve import (
            ordinal_resolve_node,
        )

        state: dict[str, Any] = {
            "protocol_id": protocol_id,
            "batch_id": batch_id,
            "error": None,
            "errors": [],
        }

        with (
            patch(
                "protocol_processor.nodes.ordinal_resolve.engine",
                engine,
            ),
            patch(
                "langchain_google_genai.ChatGoogleGenerativeAI",
            ) as mock_cls,
            patch.dict(
                os.environ,
                {"GOOGLE_API_KEY": "test-key"},
            ),
        ):
            mock_model = mock_cls.return_value
            mock_structured = mock_model.with_structured_output.return_value
            mock_structured.ainvoke = AsyncMock(return_value=mock_response)

            result = await ordinal_resolve_node(
                state,  # type: ignore[arg-type]
            )

        assert result["status"] == "completed"

        # Verify: unit_concept_id updated to 8527
        session.expire_all()
        atomic1_updated = session.get(AtomicCriterion, atomic1.id)
        assert atomic1_updated is not None
        assert atomic1_updated.unit_concept_id == 8527, (
            "After LLM resolve: unit_concept_id should be 8527"
        )

        # Verify: AuditLog proposal written
        audits = session.exec(
            select(AuditLog).where(
                AuditLog.event_type == "ordinal_scale_proposed",
            )
        ).all()
        assert len(audits) == 1
        assert audits[0].details["proposals"][0]["scale_name"] == ("child_pugh")

        # Verify: proposals in state
        assert result.get("ordinal_proposals_json") is not None
        proposals = json.loads(result["ordinal_proposals_json"])
        assert proposals[0]["entity_text"] == "Child-Pugh score"

        # ── Phase 3: Simulate Approval ────────────────────────────
        # Simulate adding Child-Pugh to the alias dict
        augmented_aliases = dict(ORDINAL_SCALE_ALIASES)
        augmented_aliases["child-pugh"] = "child_pugh"
        augmented_aliases["child-pugh score"] = "child_pugh"
        augmented_aliases["child-pugh classification"] = "child_pugh"
        augmented_aliases["ctp score"] = "child_pugh"

        # ── Phase 4: Static Lookup (HIT) ──────────────────────────
        # Now Child-Pugh is in the alias dict → static lookup succeeds
        p1, p2, p3, p4 = _patch_db()
        with (
            p1,
            p2,
            p3,
            p4,
            patch(
                "protocol_processor.tools.unit_normalizer.ORDINAL_SCALE_ALIASES",
                augmented_aliases,
            ),
        ):
            result_ordinal = normalize_ordinal_value(
                "6",
                "Child-Pugh score",
            )
            assert result_ordinal is not None, (
                "After approval: normalize_ordinal_value should match"
            )
            value_concept_id, unit_concept_id = result_ordinal
            assert unit_concept_id == 8527

            # Create a new criterion in a new batch
            batch2 = CriteriaBatch(protocol_id=protocol_id)
            session.add(batch2)
            session.flush()

            crit2 = _make_crit(
                session,
                batch2.id,
                "Child-Pugh score <= 7",
            )
            # Patch structure_builder's normalizer import too
            with patch(
                "protocol_processor.tools.structure_builder.normalize_ordinal_value",
                side_effect=lambda v, e: normalize_ordinal_value(
                    v,
                    e,
                ),
            ):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("GOOGLE_API_KEY", None)
                    await build_expression_tree(
                        criterion_text="Child-Pugh score <= 7",
                        field_mappings=[
                            {
                                "entity": "Child-Pugh score",
                                "relation": "<=",
                                "value": "7",
                                "unit": None,
                            }
                        ],
                        criterion_id=crit2.id,
                        protocol_id=protocol_id,
                        inclusion_exclusion="inclusion",
                        session=session,
                    )
            session.flush()

            atomic2 = session.exec(
                select(AtomicCriterion).where(
                    AtomicCriterion.criterion_id == crit2.id,
                )
            ).first()
            assert atomic2 is not None
            assert atomic2.unit_concept_id == 8527, (
                "After approval: new criteria get 8527 from alias dict"
            )
            assert atomic2.value_numeric == pytest.approx(7.0)

        # ── Phase 5: No LLM Call Needed ───────────────────────────
        state2: dict[str, Any] = {
            "protocol_id": protocol_id,
            "batch_id": batch2.id,
            "error": None,
            "errors": [],
        }
        session.commit()

        mock_resolve = AsyncMock(return_value=None)
        with (
            patch(
                "protocol_processor.nodes.ordinal_resolve.engine",
                engine,
            ),
            patch(
                "protocol_processor.nodes.ordinal_resolve.resolve_ordinal_candidates",
                mock_resolve,
            ),
        ):
            result2 = await ordinal_resolve_node(
                state2,  # type: ignore[arg-type]
            )

        assert result2["status"] == "completed"
        mock_resolve.assert_not_called()
