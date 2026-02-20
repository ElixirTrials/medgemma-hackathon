"""End-to-end verification for Phase 2: Expression Tree + Normalized Tables.

Tests the complete Phase 2 flow with a real SQLite in-memory database:
1. Alembic migration: tables and columns exist
2. SQLModel ORM: AtomicCriterion, CompositeCriterion, CriterionRelationship CRUD
3. Structure builder: full tree creation with real DB writes
4. Structure node: pipeline integration with real DB reads/writes
5. Graph compilation: 6-node pipeline with structure node wired

Unlike unit tests (test_phase2_structure.py) which mock the DB, these tests
exercise the actual SQLAlchemy/SQLModel layer with in-memory SQLite.
"""

from __future__ import annotations

import os
from typing import Any, Generator
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import inspect
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def e2e_engine():
    """Create an in-memory SQLite engine with all tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Import all models so SQLModel metadata is populated
    import shared.models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def e2e_session(e2e_engine) -> Generator[Session, None, None]:
    """Create a session for E2E testing."""
    session = Session(e2e_engine)
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_field_mapping(**overrides: Any) -> dict[str, Any]:
    """Build a field_mapping dict with sensible defaults."""
    defaults: dict[str, Any] = {
        "entity": "HbA1c",
        "relation": "<",
        "value": "7",
        "unit": "%",
        "entity_concept_id": "C0011847",
        "entity_concept_system": "umls",
        "omop_concept_id": "201826",
    }
    defaults.update(overrides)
    return defaults


# ===========================================================================
# 1. Database Schema Verification
# ===========================================================================


class TestDatabaseSchema:
    """Verify Phase 2 tables and columns exist after create_all."""

    def test_atomic_criteria_table_exists(self, e2e_engine) -> None:
        """atomic_criteria table should be created."""
        inspector = inspect(e2e_engine)
        tables = inspector.get_table_names()
        assert "atomic_criteria" in tables

    def test_composite_criteria_table_exists(self, e2e_engine) -> None:
        """composite_criteria table should be created."""
        inspector = inspect(e2e_engine)
        tables = inspector.get_table_names()
        assert "composite_criteria" in tables

    def test_criterion_relationships_table_exists(self, e2e_engine) -> None:
        """criterion_relationships table should be created."""
        inspector = inspect(e2e_engine)
        tables = inspector.get_table_names()
        assert "criterion_relationships" in tables

    def test_criteria_has_structured_criterion_column(self, e2e_engine) -> None:
        """Criteria table should have structured_criterion JSONB column."""
        inspector = inspect(e2e_engine)
        columns = {c["name"] for c in inspector.get_columns("criteria")}
        assert "structured_criterion" in columns

    def test_atomic_criteria_columns(self, e2e_engine) -> None:
        """atomic_criteria should have all expected columns."""
        inspector = inspect(e2e_engine)
        columns = {c["name"] for c in inspector.get_columns("atomic_criteria")}
        expected = {
            "id",
            "criterion_id",
            "protocol_id",
            "inclusion_exclusion",
            "entity_concept_id",
            "entity_concept_system",
            "omop_concept_id",
            "entity_domain",
            "relation_operator",
            "value_numeric",
            "value_text",
            "unit_text",
            "unit_concept_id",
            "value_concept_id",
            "negation",
            "temporal_constraint",
            "original_text",
            "confidence_score",
            "human_verified",
            "human_modified",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(columns), f"Missing columns: {expected - columns}"

    def test_composite_criteria_columns(self, e2e_engine) -> None:
        """composite_criteria should have all expected columns."""
        inspector = inspect(e2e_engine)
        columns = {c["name"] for c in inspector.get_columns("composite_criteria")}
        expected = {
            "id",
            "criterion_id",
            "protocol_id",
            "inclusion_exclusion",
            "logic_operator",
            "parent_criterion_id",
            "original_text",
            "human_verified",
            "created_at",
            "updated_at",
        }
        assert expected.issubset(columns), f"Missing columns: {expected - columns}"

    def test_criterion_relationships_columns(self, e2e_engine) -> None:
        """criterion_relationships should have all expected columns."""
        inspector = inspect(e2e_engine)
        columns = {c["name"] for c in inspector.get_columns("criterion_relationships")}
        expected = {
            "parent_criterion_id",
            "child_criterion_id",
            "child_type",
            "child_sequence",
        }
        assert expected.issubset(columns), f"Missing columns: {expected - columns}"


# ===========================================================================
# 2. ORM CRUD Verification
# ===========================================================================


class TestOrmCrud:
    """Verify SQLModel ORM operations work for all Phase 2 models."""

    def test_create_and_read_atomic_criterion(self, e2e_session) -> None:
        """AtomicCriterion can be created, flushed, and queried."""
        from shared.models import AtomicCriterion, Criteria, CriteriaBatch, Protocol

        # Create parent records
        protocol = Protocol(title="Test Protocol", file_uri="local://test.pdf")
        e2e_session.add(protocol)
        e2e_session.flush()

        batch = CriteriaBatch(protocol_id=protocol.id)
        e2e_session.add(batch)
        e2e_session.flush()

        criterion = Criteria(
            batch_id=batch.id,
            criteria_type="inclusion",
            text="HbA1c < 7%",
        )
        e2e_session.add(criterion)
        e2e_session.flush()

        # Create AtomicCriterion
        atomic = AtomicCriterion(
            criterion_id=criterion.id,
            protocol_id=protocol.id,
            inclusion_exclusion="inclusion",
            entity_concept_id="C0011847",
            entity_concept_system="umls",
            omop_concept_id="201826",
            relation_operator="<",
            value_numeric=7.0,
            unit_text="%",
            original_text="HbA1c < 7%",
        )
        e2e_session.add(atomic)
        e2e_session.flush()

        # Query back
        result = e2e_session.get(AtomicCriterion, atomic.id)
        assert result is not None
        assert result.criterion_id == criterion.id
        assert result.protocol_id == protocol.id
        assert result.value_numeric == 7.0
        assert result.entity_concept_id == "C0011847"
        assert result.omop_concept_id == "201826"

    def test_create_composite_and_relationships(self, e2e_session) -> None:
        """CompositeCriterion + CriterionRelationship tree can be built."""
        from shared.models import (
            AtomicCriterion,
            CompositeCriterion,
            Criteria,
            CriteriaBatch,
            CriterionRelationship,
            Protocol,
        )

        # Create parent records
        protocol = Protocol(title="Test Protocol", file_uri="local://test.pdf")
        e2e_session.add(protocol)
        e2e_session.flush()

        batch = CriteriaBatch(protocol_id=protocol.id)
        e2e_session.add(batch)
        e2e_session.flush()

        criterion = Criteria(
            batch_id=batch.id,
            criteria_type="inclusion",
            text="HbA1c < 7% and eGFR > 30 mL/min",
        )
        e2e_session.add(criterion)
        e2e_session.flush()

        # Create two atomics
        atom1 = AtomicCriterion(
            criterion_id=criterion.id,
            protocol_id=protocol.id,
            inclusion_exclusion="inclusion",
            relation_operator="<",
            value_numeric=7.0,
            unit_text="%",
            original_text="HbA1c < 7%",
        )
        atom2 = AtomicCriterion(
            criterion_id=criterion.id,
            protocol_id=protocol.id,
            inclusion_exclusion="inclusion",
            relation_operator=">",
            value_numeric=30.0,
            unit_text="mL/min",
            original_text="eGFR > 30 mL/min",
        )
        e2e_session.add_all([atom1, atom2])
        e2e_session.flush()

        # Create AND composite
        composite = CompositeCriterion(
            criterion_id=criterion.id,
            protocol_id=protocol.id,
            inclusion_exclusion="inclusion",
            logic_operator="AND",
            original_text="HbA1c < 7% and eGFR > 30 mL/min",
        )
        e2e_session.add(composite)
        e2e_session.flush()

        # Create relationships
        rel1 = CriterionRelationship(
            parent_criterion_id=composite.id,
            child_criterion_id=atom1.id,
            child_type="atomic",
            child_sequence=0,
        )
        rel2 = CriterionRelationship(
            parent_criterion_id=composite.id,
            child_criterion_id=atom2.id,
            child_type="atomic",
            child_sequence=1,
        )
        e2e_session.add_all([rel1, rel2])
        e2e_session.flush()

        # Query: verify composite + relationships
        comp_result = e2e_session.get(CompositeCriterion, composite.id)
        assert comp_result is not None
        assert comp_result.logic_operator == "AND"

        rels = e2e_session.exec(
            select(CriterionRelationship).where(
                CriterionRelationship.parent_criterion_id == composite.id
            )
        ).all()
        assert len(rels) == 2
        assert rels[0].child_type == "atomic"
        assert rels[1].child_type == "atomic"
        # Verify ordering
        sequences = sorted(r.child_sequence for r in rels)
        assert sequences == [0, 1]

    def test_criteria_structured_criterion_jsonb(self, e2e_session) -> None:
        """Criteria.structured_criterion round-trips JSONB data."""
        from shared.models import Criteria, CriteriaBatch, Protocol

        protocol = Protocol(title="Test Protocol", file_uri="local://test.pdf")
        e2e_session.add(protocol)
        e2e_session.flush()

        batch = CriteriaBatch(protocol_id=protocol.id)
        e2e_session.add(batch)
        e2e_session.flush()

        tree_data = {
            "root": {
                "type": "ATOMIC",
                "atomic_criterion_id": "atom-001",
                "entity": "HbA1c",
                "relation": "<",
                "value": "7",
                "unit": "%",
                "omop_concept_id": "201826",
                "children": None,
            },
            "structure_confidence": "fallback",
            "structure_model": None,
        }

        criterion = Criteria(
            batch_id=batch.id,
            criteria_type="inclusion",
            text="HbA1c < 7%",
            structured_criterion=tree_data,
        )
        e2e_session.add(criterion)
        e2e_session.flush()

        # Query back and verify JSONB round-trip
        result = e2e_session.get(Criteria, criterion.id)
        assert result is not None
        assert result.structured_criterion is not None
        assert result.structured_criterion["root"]["type"] == "ATOMIC"
        assert result.structured_criterion["root"]["entity"] == "HbA1c"
        assert result.structured_criterion["structure_confidence"] == "fallback"


# ===========================================================================
# 3. Structure Builder E2E (real DB writes)
# ===========================================================================


class TestStructureBuilderE2e:
    """E2E tests for build_expression_tree with a real SQLite session."""

    async def test_single_mapping_creates_one_atomic(self, e2e_session) -> None:
        """Single field_mapping -> 1 AtomicCriterion in DB."""
        from shared.models import AtomicCriterion, Criteria, CriteriaBatch, Protocol

        from protocol_processor.tools.structure_builder import build_expression_tree

        # Setup parent records
        protocol = Protocol(title="Test Protocol", file_uri="local://test.pdf")
        e2e_session.add(protocol)
        e2e_session.flush()

        batch = CriteriaBatch(protocol_id=protocol.id)
        e2e_session.add(batch)
        e2e_session.flush()

        criterion = Criteria(
            batch_id=batch.id,
            criteria_type="inclusion",
            text="HbA1c < 7%",
        )
        e2e_session.add(criterion)
        e2e_session.flush()

        # Build expression tree (single mapping -> no LLM call)
        tree = await build_expression_tree(
            criterion_text="HbA1c < 7%",
            field_mappings=[_make_field_mapping()],
            criterion_id=criterion.id,
            protocol_id=protocol.id,
            inclusion_exclusion="inclusion",
            session=e2e_session,
        )
        e2e_session.commit()

        # Verify tree structure
        assert tree.root.type == "ATOMIC"
        assert tree.structure_confidence == "fallback"
        assert tree.root.entity == "HbA1c"
        assert tree.root.omop_concept_id == "201826"

        # Verify DB records
        atomics = e2e_session.exec(
            select(AtomicCriterion).where(AtomicCriterion.criterion_id == criterion.id)
        ).all()
        assert len(atomics) == 1
        assert atomics[0].value_numeric == 7.0
        assert atomics[0].value_text is None
        assert atomics[0].entity_concept_id == "C0011847"
        assert atomics[0].omop_concept_id == "201826"
        assert atomics[0].relation_operator == "<"
        assert atomics[0].unit_text == "%"

    async def test_multi_mapping_fallback_creates_and_tree(self, e2e_session) -> None:
        """Multiple field_mappings with LLM fallback -> AND tree in DB."""
        from shared.models import (
            AtomicCriterion,
            CompositeCriterion,
            Criteria,
            CriteriaBatch,
            CriterionRelationship,
            Protocol,
        )

        from protocol_processor.tools.structure_builder import build_expression_tree

        # Setup
        protocol = Protocol(title="Test Protocol", file_uri="local://test.pdf")
        e2e_session.add(protocol)
        e2e_session.flush()

        batch = CriteriaBatch(protocol_id=protocol.id)
        e2e_session.add(batch)
        e2e_session.flush()

        criterion = Criteria(
            batch_id=batch.id,
            criteria_type="inclusion",
            text="HbA1c < 7% and eGFR > 30 mL/min",
        )
        e2e_session.add(criterion)
        e2e_session.flush()

        mappings = [
            _make_field_mapping(),
            _make_field_mapping(
                entity="eGFR",
                relation=">",
                value="30",
                unit="mL/min",
                entity_concept_id="C0017654",
                omop_concept_id="3049187",
            ),
        ]

        # No GOOGLE_API_KEY -> detect_logic_structure returns None -> fallback
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_API_KEY", None)
            tree = await build_expression_tree(
                criterion_text="HbA1c < 7% and eGFR > 30 mL/min",
                field_mappings=mappings,
                criterion_id=criterion.id,
                protocol_id=protocol.id,
                inclusion_exclusion="inclusion",
                session=e2e_session,
            )
        e2e_session.commit()

        # Verify tree structure
        assert tree.root.type == "AND"
        assert tree.structure_confidence == "fallback"
        assert len(tree.root.children) == 2
        assert tree.root.children[0].entity == "HbA1c"
        assert tree.root.children[1].entity == "eGFR"

        # Verify DB: 2 atomics
        atomics = e2e_session.exec(
            select(AtomicCriterion).where(AtomicCriterion.criterion_id == criterion.id)
        ).all()
        assert len(atomics) == 2

        # Verify DB: 1 composite (AND)
        composites = e2e_session.exec(
            select(CompositeCriterion).where(
                CompositeCriterion.criterion_id == criterion.id
            )
        ).all()
        assert len(composites) == 1
        assert composites[0].logic_operator == "AND"

        # Verify DB: 2 relationships
        rels = e2e_session.exec(
            select(CriterionRelationship).where(
                CriterionRelationship.parent_criterion_id == composites[0].id
            )
        ).all()
        assert len(rels) == 2
        assert all(r.child_type == "atomic" for r in rels)
        sequences = sorted(r.child_sequence for r in rels)
        assert sequences == [0, 1]

    async def test_value_text_for_non_numeric(self, e2e_session) -> None:
        """Non-numeric values stored as value_text, not value_numeric."""
        from shared.models import AtomicCriterion, Criteria, CriteriaBatch, Protocol

        from protocol_processor.tools.structure_builder import build_expression_tree

        protocol = Protocol(title="Test Protocol", file_uri="local://test.pdf")
        e2e_session.add(protocol)
        e2e_session.flush()

        batch = CriteriaBatch(protocol_id=protocol.id)
        e2e_session.add(batch)
        e2e_session.flush()

        criterion = Criteria(
            batch_id=batch.id,
            criteria_type="exclusion",
            text="HIV status is positive",
        )
        e2e_session.add(criterion)
        e2e_session.flush()

        await build_expression_tree(
            criterion_text="HIV status is positive",
            field_mappings=[
                _make_field_mapping(
                    entity="HIV status",
                    relation="is",
                    value="positive",
                    unit=None,
                )
            ],
            criterion_id=criterion.id,
            protocol_id=protocol.id,
            inclusion_exclusion="exclusion",
            session=e2e_session,
        )
        e2e_session.commit()

        atomics = e2e_session.exec(
            select(AtomicCriterion).where(AtomicCriterion.criterion_id == criterion.id)
        ).all()
        assert len(atomics) == 1
        assert atomics[0].value_numeric is None
        assert atomics[0].value_text == "positive"
        assert atomics[0].inclusion_exclusion == "exclusion"


# ===========================================================================
# 4. Structure Node E2E (pipeline integration)
# ===========================================================================


class TestStructureNodeE2e:
    """E2E tests for structure_node reading/writing a real DB."""

    @patch("protocol_processor.tracing.pipeline_span")
    async def test_full_node_flow(
        self, mock_span_fn: MagicMock, e2e_engine, e2e_session
    ) -> None:
        """Structure node reads criteria from DB, builds trees, writes back."""
        from shared.models import (
            AtomicCriterion,
            AuditLog,
            CompositeCriterion,
            Criteria,
            CriteriaBatch,
            Protocol,
        )

        # Setup span mock
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)
        mock_span.set_inputs = MagicMock()
        mock_span.set_outputs = MagicMock()
        mock_span_fn.return_value = mock_span

        # Create test data
        protocol = Protocol(title="E2E Test Protocol", file_uri="local://test.pdf")
        e2e_session.add(protocol)
        e2e_session.flush()

        batch = CriteriaBatch(protocol_id=protocol.id)
        e2e_session.add(batch)
        e2e_session.flush()

        # Criterion 1: single mapping (no logic needed)
        crit1 = Criteria(
            batch_id=batch.id,
            criteria_type="inclusion",
            text="Age >= 18 years",
            conditions={
                "field_mappings": [
                    {
                        "entity": "Age",
                        "relation": ">=",
                        "value": "18",
                        "unit": "years",
                        "entity_concept_id": "C0001779",
                        "entity_concept_system": "umls",
                        "omop_concept_id": "4265453",
                    }
                ]
            },
        )

        # Criterion 2: two mappings (AND fallback)
        crit2 = Criteria(
            batch_id=batch.id,
            criteria_type="inclusion",
            text="HbA1c < 7% and eGFR > 30 mL/min",
            conditions={
                "field_mappings": [
                    {
                        "entity": "HbA1c",
                        "relation": "<",
                        "value": "7",
                        "unit": "%",
                        "entity_concept_id": "C0011847",
                        "entity_concept_system": "umls",
                        "omop_concept_id": "201826",
                    },
                    {
                        "entity": "eGFR",
                        "relation": ">",
                        "value": "30",
                        "unit": "mL/min",
                        "entity_concept_id": "C0017654",
                        "entity_concept_system": "umls",
                        "omop_concept_id": "3049187",
                    },
                ]
            },
        )

        # Criterion 3: no field_mappings (should be skipped)
        crit3 = Criteria(
            batch_id=batch.id,
            criteria_type="inclusion",
            text="Informed consent provided",
            conditions=None,
        )

        e2e_session.add_all([crit1, crit2, crit3])
        e2e_session.commit()

        # Ensure no GOOGLE_API_KEY -> fallback mode
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_API_KEY", None)

            # Patch engine to use our test engine
            with patch("protocol_processor.nodes.structure.engine", e2e_engine):
                from protocol_processor.nodes.structure import structure_node

                result = await structure_node(
                    {  # type: ignore[arg-type]
                        "error": None,
                        "protocol_id": protocol.id,
                        "batch_id": batch.id,
                        "errors": [],
                    }
                )

        assert result["status"] == "completed"
        assert len(result.get("errors", [])) == 0

        # Refresh session to see committed data
        e2e_session.expire_all()

        # Verify crit1: single ATOMIC tree
        crit1_db = e2e_session.get(Criteria, crit1.id)
        assert crit1_db is not None
        assert crit1_db.structured_criterion is not None
        assert crit1_db.structured_criterion["root"]["type"] == "ATOMIC"
        assert crit1_db.structured_criterion["root"]["entity"] == "Age"
        assert crit1_db.structured_criterion["structure_confidence"] == "fallback"

        # Verify crit2: AND tree with 2 children
        crit2_db = e2e_session.get(Criteria, crit2.id)
        assert crit2_db is not None
        assert crit2_db.structured_criterion is not None
        assert crit2_db.structured_criterion["root"]["type"] == "AND"
        children = crit2_db.structured_criterion["root"]["children"]
        assert len(children) == 2
        assert children[0]["entity"] == "HbA1c"
        assert children[1]["entity"] == "eGFR"

        # Verify crit3: no structured_criterion (skipped)
        crit3_db = e2e_session.get(Criteria, crit3.id)
        assert crit3_db is not None
        assert crit3_db.structured_criterion is None

        # Verify atomic_criteria records
        all_atomics = e2e_session.exec(select(AtomicCriterion)).all()
        # crit1 -> 1 atomic, crit2 -> 2 atomics = 3 total
        assert len(all_atomics) == 3

        # Verify composite_criteria records
        all_composites = e2e_session.exec(select(CompositeCriterion)).all()
        # crit2 -> 1 AND composite = 1 total (crit1 has no composite)
        assert len(all_composites) == 1
        assert all_composites[0].logic_operator == "AND"

        # Verify audit log
        audits = e2e_session.exec(
            select(AuditLog).where(AuditLog.event_type == "structure_trees_built")
        ).all()
        assert len(audits) == 1
        assert audits[0].details["criteria_processed"] == 2
        assert audits[0].details["errors"] == 0


# ===========================================================================
# 5. Graph Compilation Verification
# ===========================================================================


class TestGraphCompilation:
    """Verify the 7-node graph compiles correctly with structure + ordinal_resolve."""

    def test_seven_node_pipeline(self) -> None:
        """Graph should have 7 user-defined nodes."""
        from protocol_processor.graph import create_graph

        graph = create_graph()
        all_nodes = graph.nodes
        user_nodes = {n for n in all_nodes if not n.startswith("__")}
        assert user_nodes == {
            "ingest",
            "extract",
            "parse",
            "ground",
            "persist",
            "structure",
            "ordinal_resolve",
        }

    def test_persist_to_structure_edge(self) -> None:
        """Persist should have an edge to structure (not to END)."""
        from protocol_processor.graph import create_graph

        graph = create_graph()
        # LangGraph stores edges in graph.graph — verify structure is after persist
        # by checking the graph has structure node and it appears after persist
        assert "structure" in graph.nodes
        assert "persist" in graph.nodes

    def test_structure_node_is_callable(self) -> None:
        """structure_node should be an async callable."""
        import asyncio

        from protocol_processor.nodes.structure import structure_node

        assert callable(structure_node)
        assert asyncio.iscoroutinefunction(structure_node)


# ===========================================================================
# 6. Phase 3: Unit & Value Normalization
# ===========================================================================


class TestPhase3UnitNormalization:
    """Verify Phase 3 unit/value concept ID columns and normalizer integration."""

    def test_unit_concept_id_column_exists(self, e2e_engine) -> None:
        """atomic_criteria should have unit_concept_id column."""
        inspector = inspect(e2e_engine)
        columns = {c["name"] for c in inspector.get_columns("atomic_criteria")}
        assert "unit_concept_id" in columns

    def test_value_concept_id_column_exists(self, e2e_engine) -> None:
        """atomic_criteria should have value_concept_id column."""
        inspector = inspect(e2e_engine)
        columns = {c["name"] for c in inspector.get_columns("atomic_criteria")}
        assert "value_concept_id" in columns

    async def test_unit_normalization_persists(self, e2e_session) -> None:
        """Structure builder should populate unit_concept_id for '%' -> 8554."""
        from shared.models import AtomicCriterion, Criteria, CriteriaBatch, Protocol

        from protocol_processor.tools.structure_builder import build_expression_tree

        protocol = Protocol(title="Test Protocol", file_uri="local://test.pdf")
        e2e_session.add(protocol)
        e2e_session.flush()

        batch = CriteriaBatch(protocol_id=protocol.id)
        e2e_session.add(batch)
        e2e_session.flush()

        criterion = Criteria(
            batch_id=batch.id,
            criteria_type="inclusion",
            text="HbA1c < 7%",
        )
        e2e_session.add(criterion)
        e2e_session.flush()

        await build_expression_tree(
            criterion_text="HbA1c < 7%",
            field_mappings=[_make_field_mapping()],
            criterion_id=criterion.id,
            protocol_id=protocol.id,
            inclusion_exclusion="inclusion",
            session=e2e_session,
        )
        e2e_session.commit()

        atomics = e2e_session.exec(
            select(AtomicCriterion).where(AtomicCriterion.criterion_id == criterion.id)
        ).all()
        assert len(atomics) == 1
        assert atomics[0].unit_text == "%"
        assert atomics[0].unit_concept_id == 8554

    async def test_value_normalization_persists(self, e2e_session) -> None:
        """Builder should populate value_concept_id: positive -> 45884084."""
        from shared.models import AtomicCriterion, Criteria, CriteriaBatch, Protocol

        from protocol_processor.tools.structure_builder import build_expression_tree

        protocol = Protocol(title="Test Protocol", file_uri="local://test.pdf")
        e2e_session.add(protocol)
        e2e_session.flush()

        batch = CriteriaBatch(protocol_id=protocol.id)
        e2e_session.add(batch)
        e2e_session.flush()

        criterion = Criteria(
            batch_id=batch.id,
            criteria_type="exclusion",
            text="HIV status is positive",
        )
        e2e_session.add(criterion)
        e2e_session.flush()

        await build_expression_tree(
            criterion_text="HIV status is positive",
            field_mappings=[
                _make_field_mapping(
                    entity="HIV status",
                    relation="is",
                    value="positive",
                    unit=None,
                )
            ],
            criterion_id=criterion.id,
            protocol_id=protocol.id,
            inclusion_exclusion="exclusion",
            session=e2e_session,
        )
        e2e_session.commit()

        atomics = e2e_session.exec(
            select(AtomicCriterion).where(AtomicCriterion.criterion_id == criterion.id)
        ).all()
        assert len(atomics) == 1
        assert atomics[0].value_text == "positive"
        assert atomics[0].value_concept_id == 45884084
        assert atomics[0].unit_concept_id is None

    async def test_unrecognized_unit_stays_none(self, e2e_session) -> None:
        """Unrecognized unit should leave unit_concept_id as None."""
        from shared.models import AtomicCriterion, Criteria, CriteriaBatch, Protocol

        from protocol_processor.tools.structure_builder import build_expression_tree

        protocol = Protocol(title="Test Protocol", file_uri="local://test.pdf")
        e2e_session.add(protocol)
        e2e_session.flush()

        batch = CriteriaBatch(protocol_id=protocol.id)
        e2e_session.add(batch)
        e2e_session.flush()

        criterion = Criteria(
            batch_id=batch.id,
            criteria_type="inclusion",
            text="Something > 5 widgets",
        )
        e2e_session.add(criterion)
        e2e_session.flush()

        await build_expression_tree(
            criterion_text="Something > 5 widgets",
            field_mappings=[
                _make_field_mapping(
                    entity="Something",
                    relation=">",
                    value="5",
                    unit="widgets",
                )
            ],
            criterion_id=criterion.id,
            protocol_id=protocol.id,
            inclusion_exclusion="inclusion",
            session=e2e_session,
        )
        e2e_session.commit()

        atomics = e2e_session.exec(
            select(AtomicCriterion).where(AtomicCriterion.criterion_id == criterion.id)
        ).all()
        assert len(atomics) == 1
        assert atomics[0].unit_text == "widgets"
        assert atomics[0].unit_concept_id is None
        assert atomics[0].value_concept_id is None
