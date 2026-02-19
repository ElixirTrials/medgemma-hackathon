"""Tests for the ordinal_resolve node and ordinal_resolver tool.

Unit tests mock the LLM. E2E tests use in-memory SQLite with mocked LLM
to verify the full flow from AtomicCriterion query through DB update.
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
from protocol_processor.tools.ordinal_resolver import resolve_ordinal_candidates

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


def _setup_parent(session: Session) -> tuple[str, str]:
    """Create Protocol + CriteriaBatch, return (protocol_id, batch_id)."""
    protocol = Protocol(title="NCT-ORDINAL-TEST", file_uri="local://test.pdf")
    session.add(protocol)
    session.flush()
    batch = CriteriaBatch(protocol_id=protocol.id)
    session.add(batch)
    session.flush()
    return protocol.id, batch.id


def _make_criterion(
    session: Session, batch_id: str, text: str, criteria_type: str = "inclusion"
) -> Criteria:
    crit = Criteria(batch_id=batch_id, criteria_type=criteria_type, text=text)
    session.add(crit)
    session.flush()
    return crit


def _make_atomic(
    session: Session,
    criterion_id: str,
    protocol_id: str,
    *,
    original_text: str,
    relation_operator: str = "<=",
    value_numeric: float | None = None,
    value_text: str | None = None,
    unit_text: str | None = None,
    unit_concept_id: int | None = None,
) -> AtomicCriterion:
    atomic = AtomicCriterion(
        criterion_id=criterion_id,
        protocol_id=protocol_id,
        inclusion_exclusion="inclusion",
        relation_operator=relation_operator,
        value_numeric=value_numeric,
        value_text=value_text,
        unit_text=unit_text,
        unit_concept_id=unit_concept_id,
        original_text=original_text,
    )
    session.add(atomic)
    session.flush()
    return atomic


def _build_mock_response(
    proposals: list[dict[str, Any]],
) -> OrdinalResolutionResponse:
    """Build a mock OrdinalResolutionResponse."""
    return OrdinalResolutionResponse(
        proposals=[OrdinalScaleProposal(**p) for p in proposals]
    )


# ── Unit tests: resolve_ordinal_candidates() ─────────────────────────


class TestResolveOrdinalCandidatesUnit:
    """Unit tests for the LLM tool function."""

    async def test_no_candidates_skips_llm(self) -> None:
        """Empty candidate list returns None without calling LLM."""
        result = await resolve_ordinal_candidates([])
        assert result is None

    async def test_no_api_key_returns_none(self) -> None:
        """Missing GOOGLE_API_KEY returns None gracefully."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_API_KEY", None)
            candidate = {
                "entity_text": "Child-Pugh score",
                "value_numeric": 6,
                "relation_operator": "<=",
            }
            result = await resolve_ordinal_candidates([candidate])
        assert result is None

    async def test_successful_resolution(self) -> None:
        """Mock Gemini confirms Child-Pugh as ordinal → returns proposal."""
        mock_response = _build_mock_response(
            [
                {
                    "entity_text": "Child-Pugh score",
                    "is_ordinal_scale": True,
                    "confidence": 0.95,
                    "scale_name": "child_pugh",
                    "entity_aliases": [
                        "Child-Pugh",
                        "Child-Pugh classification",
                    ],
                    "loinc_code": "75622-1",
                },
            ]
        )

        candidate = {
            "entity_text": "Child-Pugh score",
            "value_numeric": 6,
            "relation_operator": "<=",
        }

        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}):
            with patch("langchain_google_genai.ChatGoogleGenerativeAI") as mock_cls:
                mock_model = mock_cls.return_value
                mock_structured = mock_model.with_structured_output.return_value
                mock_structured.invoke.return_value = mock_response

                result = await resolve_ordinal_candidates(
                    [candidate],
                )

        assert result is not None
        assert len(result.proposals) == 1
        assert result.proposals[0].entity_text == "Child-Pugh score"
        assert result.proposals[0].is_ordinal_scale is True
        assert result.proposals[0].scale_name == "child_pugh"

    async def test_non_ordinal_rejected(self) -> None:
        """Mock Gemini says 'HIV status' is NOT ordinal → filtered out."""
        mock_response = _build_mock_response(
            [
                {
                    "entity_text": "HIV status",
                    "is_ordinal_scale": False,
                    "confidence": 0.9,
                    "reasoning": "Binary condition, not a scoring system",
                },
            ]
        )

        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}):
            with patch("langchain_google_genai.ChatGoogleGenerativeAI") as mock_cls:
                mock_model = mock_cls.return_value
                mock_structured = mock_model.with_structured_output.return_value
                mock_structured.invoke.return_value = mock_response

                candidate = {
                    "entity_text": "HIV status",
                    "value_numeric": 1,
                    "relation_operator": "is",
                }
                result = await resolve_ordinal_candidates(
                    [candidate],
                )

        assert result is not None
        assert len(result.proposals) == 0

    async def test_low_confidence_rejected(self) -> None:
        """Confidence < 0.7 → filtered out even if is_ordinal_scale=True."""
        mock_response = _build_mock_response(
            [
                {
                    "entity_text": "Custom Score",
                    "is_ordinal_scale": True,
                    "confidence": 0.5,
                    "reasoning": "Might be ordinal but unclear",
                },
            ]
        )

        candidate = {
            "entity_text": "Custom Score",
            "value_numeric": 3,
            "relation_operator": ">=",
        }

        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}):
            with patch("langchain_google_genai.ChatGoogleGenerativeAI") as mock_cls:
                mock_model = mock_cls.return_value
                mock_structured = mock_model.with_structured_output.return_value
                mock_structured.invoke.return_value = mock_response

                result = await resolve_ordinal_candidates(
                    [candidate],
                )

        assert result is not None
        assert len(result.proposals) == 0

    async def test_llm_failure_graceful(self) -> None:
        """Exception during LLM call → returns None."""
        candidate = {
            "entity_text": "GCS",
            "value_numeric": 13,
            "relation_operator": ">=",
        }

        with patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}):
            with patch("langchain_google_genai.ChatGoogleGenerativeAI") as mock_cls:
                mock_model = mock_cls.return_value
                mock_structured = mock_model.with_structured_output.return_value
                mock_structured.invoke.side_effect = RuntimeError("API down")

                result = await resolve_ordinal_candidates(
                    [candidate],
                )

        assert result is None


# ── E2E tests: ordinal_resolve_node() with DB ────────────────────────


class TestOrdinalResolveNodeE2E:
    """E2E tests using in-memory SQLite and mocked LLM."""

    async def test_child_pugh_gets_resolved(self, engine, session) -> None:
        """Child-Pugh criterion with mocked LLM → unit_concept_id updated to 8527."""
        protocol_id, batch_id = _setup_parent(session)
        crit = _make_criterion(session, batch_id, "Child-Pugh score <= 6 (class A)")
        atomic = _make_atomic(
            session,
            crit.id,
            protocol_id,
            original_text="Child-Pugh score <= 6 (class A)",
            relation_operator="<=",
            value_numeric=6.0,
            unit_text=None,
            unit_concept_id=None,
        )
        session.commit()

        mock_response = _build_mock_response(
            [
                {
                    "entity_text": "Child-Pugh score",
                    "is_ordinal_scale": True,
                    "confidence": 0.95,
                    "scale_name": "child_pugh",
                    "entity_aliases": ["Child-Pugh"],
                    "loinc_code": "75622-1",
                },
            ]
        )

        from protocol_processor.nodes.ordinal_resolve import ordinal_resolve_node

        state = {
            "protocol_id": protocol_id,
            "batch_id": batch_id,
            "error": None,
            "errors": [],
        }

        with (
            patch("protocol_processor.nodes.ordinal_resolve.engine", engine),
            patch("langchain_google_genai.ChatGoogleGenerativeAI") as mock_cls,
            patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}),
        ):
            mock_model = mock_cls.return_value
            mock_structured = mock_model.with_structured_output.return_value
            mock_structured.invoke.return_value = mock_response

            result = await ordinal_resolve_node(state)  # type: ignore[arg-type]

        assert result["status"] == "completed"

        # Verify the AtomicCriterion was updated
        session.expire_all()
        updated = session.get(AtomicCriterion, atomic.id)
        assert updated is not None
        assert updated.unit_concept_id == 8527

    async def test_known_scales_not_rechecked(self, engine, session) -> None:
        """ECOG (already 8527 from YAML) is NOT sent to LLM."""
        protocol_id, batch_id = _setup_parent(session)
        crit = _make_criterion(session, batch_id, "ECOG <= 2")
        _make_atomic(
            session,
            crit.id,
            protocol_id,
            original_text="ECOG <= 2",
            relation_operator="<=",
            value_numeric=2.0,
            unit_text=None,
            unit_concept_id=8527,  # Already resolved by YAML
        )
        session.commit()

        from protocol_processor.nodes.ordinal_resolve import ordinal_resolve_node

        state = {
            "protocol_id": protocol_id,
            "batch_id": batch_id,
            "error": None,
            "errors": [],
        }

        mock_resolve = AsyncMock(return_value=None)
        with (
            patch("protocol_processor.nodes.ordinal_resolve.engine", engine),
            patch(
                "protocol_processor.nodes.ordinal_resolve.resolve_ordinal_candidates",
                mock_resolve,
            ),
        ):
            result = await ordinal_resolve_node(state)  # type: ignore[arg-type]

        assert result["status"] == "completed"
        # resolve_ordinal_candidates should NOT be called (no candidates)
        mock_resolve.assert_not_called()

    async def test_mixed_batch(self, engine, session) -> None:
        """Batch with ECOG + Child-Pugh + HbA1c → only Child-Pugh sent to LLM."""
        protocol_id, batch_id = _setup_parent(session)

        # ECOG: already resolved (unit_concept_id=8527)
        crit1 = _make_criterion(session, batch_id, "ECOG <= 2")
        _make_atomic(
            session,
            crit1.id,
            protocol_id,
            original_text="ECOG <= 2",
            relation_operator="<=",
            value_numeric=2.0,
            unit_concept_id=8527,
        )

        # HbA1c: has a physical unit (not ordinal candidate)
        crit2 = _make_criterion(session, batch_id, "HbA1c <= 7.0%")
        _make_atomic(
            session,
            crit2.id,
            protocol_id,
            original_text="HbA1c <= 7.0%",
            relation_operator="<=",
            value_numeric=7.0,
            unit_text="%",
            unit_concept_id=8554,
        )

        # Child-Pugh: unresolved ordinal candidate
        crit3 = _make_criterion(session, batch_id, "Child-Pugh score <= 6")
        child_pugh_atomic = _make_atomic(
            session,
            crit3.id,
            protocol_id,
            original_text="Child-Pugh score <= 6",
            relation_operator="<=",
            value_numeric=6.0,
            unit_text=None,
            unit_concept_id=None,
        )
        session.commit()

        mock_response = _build_mock_response(
            [
                {
                    "entity_text": "Child-Pugh score",
                    "is_ordinal_scale": True,
                    "confidence": 0.95,
                    "scale_name": "child_pugh",
                },
            ]
        )

        from protocol_processor.nodes.ordinal_resolve import ordinal_resolve_node

        state = {
            "protocol_id": protocol_id,
            "batch_id": batch_id,
            "error": None,
            "errors": [],
        }

        with (
            patch("protocol_processor.nodes.ordinal_resolve.engine", engine),
            patch("langchain_google_genai.ChatGoogleGenerativeAI") as mock_cls,
            patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}),
        ):
            mock_model = mock_cls.return_value
            mock_structured = mock_model.with_structured_output.return_value
            mock_structured.invoke.return_value = mock_response

            result = await ordinal_resolve_node(state)  # type: ignore[arg-type]

        assert result["status"] == "completed"

        # Only Child-Pugh should have been updated
        session.expire_all()
        updated = session.get(AtomicCriterion, child_pugh_atomic.id)
        assert updated is not None
        assert updated.unit_concept_id == 8527

        # Verify the LLM was called with only the Child-Pugh entity
        call_args = mock_structured.invoke.call_args
        prompt_text = call_args[0][0]
        assert "Child-Pugh score" in prompt_text
        # Extract the entities section (after "Entities to evaluate:")
        entities_section = prompt_text.split(
            "Entities to evaluate:",
        )[-1]
        # ECOG and HbA1c should NOT appear in the entities section
        assert "ECOG" not in entities_section
        assert "HbA1c" not in entities_section

    async def test_audit_log_written(self, engine, session) -> None:
        """AuditLog entry with proposals is created."""
        protocol_id, batch_id = _setup_parent(session)
        crit = _make_criterion(session, batch_id, "GCS >= 13")
        _make_atomic(
            session,
            crit.id,
            protocol_id,
            original_text="GCS >= 13",
            relation_operator=">=",
            value_numeric=13.0,
            unit_text=None,
            unit_concept_id=None,
        )
        session.commit()

        mock_response = _build_mock_response(
            [
                {
                    "entity_text": "GCS",
                    "is_ordinal_scale": True,
                    "confidence": 0.9,
                    "scale_name": "gcs",
                },
            ]
        )

        from protocol_processor.nodes.ordinal_resolve import ordinal_resolve_node

        state = {
            "protocol_id": protocol_id,
            "batch_id": batch_id,
            "error": None,
            "errors": [],
        }

        with (
            patch("protocol_processor.nodes.ordinal_resolve.engine", engine),
            patch("langchain_google_genai.ChatGoogleGenerativeAI") as mock_cls,
            patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}),
        ):
            mock_model = mock_cls.return_value
            mock_structured = mock_model.with_structured_output.return_value
            mock_structured.invoke.return_value = mock_response

            await ordinal_resolve_node(state)  # type: ignore[arg-type]

        # Check AuditLog was written
        session.expire_all()
        audits = session.exec(
            select(AuditLog).where(AuditLog.event_type == "ordinal_scale_proposed")
        ).all()
        assert len(audits) == 1
        audit = audits[0]
        assert audit.target_id == batch_id
        assert audit.actor_id == "system:pipeline"
        assert "proposals" in audit.details
        assert len(audit.details["proposals"]) == 1
        assert audit.details["proposals"][0]["scale_name"] == "gcs"

    async def test_proposals_in_state(self, engine, session) -> None:
        """ordinal_proposals_json populated in returned state."""
        protocol_id, batch_id = _setup_parent(session)
        crit = _make_criterion(session, batch_id, "APACHE II score < 25")
        _make_atomic(
            session,
            crit.id,
            protocol_id,
            original_text="APACHE II score < 25",
            relation_operator="<",
            value_numeric=25.0,
            unit_text=None,
            unit_concept_id=None,
        )
        session.commit()

        mock_response = _build_mock_response(
            [
                {
                    "entity_text": "APACHE II score",
                    "is_ordinal_scale": True,
                    "confidence": 0.88,
                    "scale_name": "apache_ii",
                },
            ]
        )

        from protocol_processor.nodes.ordinal_resolve import ordinal_resolve_node

        state = {
            "protocol_id": protocol_id,
            "batch_id": batch_id,
            "error": None,
            "errors": [],
        }

        with (
            patch("protocol_processor.nodes.ordinal_resolve.engine", engine),
            patch("langchain_google_genai.ChatGoogleGenerativeAI") as mock_cls,
            patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"}),
        ):
            mock_model = mock_cls.return_value
            mock_structured = mock_model.with_structured_output.return_value
            mock_structured.invoke.return_value = mock_response

            result = await ordinal_resolve_node(state)  # type: ignore[arg-type]

        assert result.get("ordinal_proposals_json") is not None
        proposals = json.loads(result["ordinal_proposals_json"])
        assert len(proposals) == 1
        assert proposals[0]["scale_name"] == "apache_ii"

    async def test_no_candidates_no_llm_call(self, engine, session) -> None:
        """No unresolved ordinal candidates → no LLM call, no proposals."""
        protocol_id, batch_id = _setup_parent(session)
        # All atomics have unit_concept_id set
        crit = _make_criterion(session, batch_id, "ECOG <= 2")
        _make_atomic(
            session,
            crit.id,
            protocol_id,
            original_text="ECOG <= 2",
            relation_operator="<=",
            value_numeric=2.0,
            unit_concept_id=8527,
        )
        session.commit()

        from protocol_processor.nodes.ordinal_resolve import ordinal_resolve_node

        state = {
            "protocol_id": protocol_id,
            "batch_id": batch_id,
            "error": None,
            "errors": [],
        }

        mock_resolve = AsyncMock(return_value=None)
        with (
            patch("protocol_processor.nodes.ordinal_resolve.engine", engine),
            patch(
                "protocol_processor.nodes.ordinal_resolve.resolve_ordinal_candidates",
                mock_resolve,
            ),
        ):
            result = await ordinal_resolve_node(state)  # type: ignore[arg-type]

        assert result["status"] == "completed"
        mock_resolve.assert_not_called()
        assert result.get("ordinal_proposals_json") is None

    async def test_error_state_short_circuits(self) -> None:
        """Node returns empty dict when state has fatal error."""
        from protocol_processor.nodes.ordinal_resolve import ordinal_resolve_node

        state = {
            "protocol_id": "test",
            "batch_id": "test-batch",
            "error": "upstream failure",
            "errors": [],
        }
        result = await ordinal_resolve_node(state)  # type: ignore[arg-type]
        assert result == {}

    async def test_no_batch_id_skips(self) -> None:
        """Node skips gracefully when batch_id is missing."""
        from protocol_processor.nodes.ordinal_resolve import ordinal_resolve_node

        state = {
            "protocol_id": "test",
            "batch_id": None,
            "error": None,
            "errors": [],
        }
        result = await ordinal_resolve_node(state)  # type: ignore[arg-type]
        assert result["status"] == "completed"
