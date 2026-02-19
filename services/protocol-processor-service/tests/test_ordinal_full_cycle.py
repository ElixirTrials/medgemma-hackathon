"""Full-cycle E2E test: Lookup → Agent → Approve → Persist.

Demonstrates the complete ordinal resolution lifecycle:

Run 1 (unknown scale):
  1. Child-Pugh criterion through build_expression_tree
     → normalize_ordinal_value() returns None (not in YAML)
     → AtomicCriterion.unit_concept_id = None
  2. ordinal_resolve_node fires → LLM (mocked) confirms ordinal
     → unit_concept_id updated to 8527
     → AuditLog proposal written for human review

Simulated approval:
  3. Add Child-Pugh to ordinal_scales config (simulates human approval)

Run 2 (known scale):
  4. New Child-Pugh criterion through build_expression_tree
     → normalize_ordinal_value() NOW matches (in YAML)
     → AtomicCriterion.unit_concept_id = 8527 at creation time
  5. ordinal_resolve_node finds no candidates → no LLM call
"""

from __future__ import annotations

import json
import os
from typing import Any, Generator
from unittest.mock import AsyncMock, patch

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
    _load_ordinal_scales,
    normalize_ordinal_value,
)

# ── Fixtures ──────────────────────────────────────────────────────────


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
    with Session(engine) as s:
        yield s


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


CHILD_PUGH_APPROVED_CONFIG: dict[str, Any] = {
    "entity_aliases": [
        "Child-Pugh",
        "Child-Pugh score",
        "Child-Pugh classification",
        "CTP score",
    ],
    "loinc_code": "75622-1",
    "unit_concept_id": 8527,
    "values": {
        "5": {"description": "Class A (best)"},
        "6": {"description": "Class A"},
        "7": {"description": "Class B"},
        "8": {"description": "Class B"},
        "9": {"description": "Class B"},
        "10": {"description": "Class C"},
        "11": {"description": "Class C"},
        "12": {"description": "Class C"},
        "13": {"description": "Class C"},
        "14": {"description": "Class C"},
        "15": {"description": "Class C (worst)"},
    },
}


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

        # ── Phase 1: Static Lookup (MISS) ─────────────────────────
        # Child-Pugh is NOT in the YAML config
        assert normalize_ordinal_value("6", "Child-Pugh score") is None

        # Build expression tree — creates AtomicCriterion with
        # unit_concept_id=None (no YAML match, no physical unit)
        crit1 = _make_crit(
            session,
            batch_id,
            "Child-Pugh score <= 6",
        )
        with patch.dict(os.environ, {}, clear=False):
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
        # ordinal_resolve_node queries AtomicCriterion where
        # unit_concept_id IS NULL + value_numeric IS NOT NULL +
        # unit_text IS NULL → finds our Child-Pugh record
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
            mock_structured.invoke.return_value = mock_response

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
        # Human reviews the AuditLog proposal and approves it.
        # This adds Child-Pugh to the ordinal_scales YAML config.
        # We simulate this by patching _load_ordinal_scales.
        _load_ordinal_scales.cache_clear()

        # Build the augmented config that includes Child-Pugh
        original_alias_to_scale, original_scale_defs = _load_ordinal_scales()
        augmented_scale_defs = {
            **original_scale_defs,
            "child_pugh": CHILD_PUGH_APPROVED_CONFIG,
        }
        augmented_alias_to_scale = dict(original_alias_to_scale)
        for alias in CHILD_PUGH_APPROVED_CONFIG["entity_aliases"]:
            augmented_alias_to_scale[alias.lower()] = "child_pugh"

        # ── Phase 4: Static Lookup (HIT) ──────────────────────────
        # Now Child-Pugh is in the config → static lookup succeeds
        with patch(
            "protocol_processor.tools.unit_normalizer._load_ordinal_scales",
            return_value=(
                augmented_alias_to_scale,
                augmented_scale_defs,
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
            # value_concept_id may be None (no omop_value_concept_id
            # in our test config) — that's fine

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
                "After approval: new criteria get 8527 from YAML"
            )
            assert atomic2.value_numeric == pytest.approx(7.0)

        # ── Phase 5: No LLM Call Needed ───────────────────────────
        # ordinal_resolve_node should find no candidates for batch2
        # because unit_concept_id is already set
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

        # Clean up the lru_cache
        _load_ordinal_scales.cache_clear()
