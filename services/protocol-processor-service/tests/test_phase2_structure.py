"""Tests for Phase 2: Expression Tree + Normalized Tables.

Covers:
1. Pydantic schema roundtrips (LogicNode, ExpressionNode, StructuredCriterionTree)
2. Logic detection (detect_logic_structure) with mocked Gemini
3. Expression tree building (build_expression_tree) with mocked session
4. Structure node behavior with mocked DB queries
5. Value parsing (numeric vs text)

All DB interactions and LLM calls are mocked — no live services required.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from protocol_processor.schemas.structure import (
    ExpressionNode,
    LogicDetectionResponse,
    LogicNode,
    StructuredCriterionTree,
)
from protocol_processor.tools.structure_builder import (
    _parse_value,
    _validate_logic_tree,
)

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
# TestLogicDetectionSchemas
# ===========================================================================


class TestLogicDetectionSchemas:
    """Pydantic roundtrip tests for logic tree schemas."""

    def test_atomic_node_roundtrip(self) -> None:
        """ATOMIC LogicNode roundtrips through model_dump/validate."""
        node = LogicNode(node_type="ATOMIC", field_mapping_index=0)
        dumped = node.model_dump()
        reconstructed = LogicNode.model_validate(dumped)
        assert reconstructed.node_type == "ATOMIC"
        assert reconstructed.field_mapping_index == 0
        assert reconstructed.children is None

    def test_and_node_with_children(self) -> None:
        """AND node with two ATOMIC children roundtrips."""
        node = LogicNode(
            node_type="AND",
            children=[
                LogicNode(node_type="ATOMIC", field_mapping_index=0),
                LogicNode(node_type="ATOMIC", field_mapping_index=1),
            ],
        )
        dumped = node.model_dump()
        reconstructed = LogicNode.model_validate(dumped)
        assert reconstructed.node_type == "AND"
        assert len(reconstructed.children) == 2
        assert reconstructed.children[0].field_mapping_index == 0
        assert reconstructed.children[1].field_mapping_index == 1

    def test_or_not_nested_tree(self) -> None:
        """OR(ATOMIC, NOT(ATOMIC)) nested tree roundtrips."""
        node = LogicNode(
            node_type="OR",
            children=[
                LogicNode(node_type="ATOMIC", field_mapping_index=0),
                LogicNode(
                    node_type="NOT",
                    children=[
                        LogicNode(node_type="ATOMIC", field_mapping_index=1),
                    ],
                ),
            ],
        )
        dumped = node.model_dump()
        reconstructed = LogicNode.model_validate(dumped)
        assert reconstructed.node_type == "OR"
        assert reconstructed.children[1].node_type == "NOT"
        assert reconstructed.children[1].children[0].field_mapping_index == 1

    def test_logic_detection_response_roundtrip(self) -> None:
        """Full LogicDetectionResponse roundtrips."""
        response = LogicDetectionResponse(
            root=LogicNode(node_type="ATOMIC", field_mapping_index=0),
            reasoning="Single condition, no logic needed.",
        )
        dumped = response.model_dump()
        reconstructed = LogicDetectionResponse.model_validate(dumped)
        assert reconstructed.root.node_type == "ATOMIC"
        assert reconstructed.reasoning == "Single condition, no logic needed."

    def test_expression_node_atomic(self) -> None:
        """ATOMIC ExpressionNode roundtrips with all fields."""
        node = ExpressionNode(
            type="ATOMIC",
            atomic_criterion_id="atom-001",
            entity="HbA1c",
            relation="<",
            value="7",
            unit="%",
            omop_concept_id="201826",
        )
        dumped = node.model_dump()
        reconstructed = ExpressionNode.model_validate(dumped)
        assert reconstructed.type == "ATOMIC"
        assert reconstructed.atomic_criterion_id == "atom-001"
        assert reconstructed.entity == "HbA1c"

    def test_expression_node_branch(self) -> None:
        """AND ExpressionNode with children roundtrips."""
        node = ExpressionNode(
            type="AND",
            children=[
                ExpressionNode(
                    type="ATOMIC",
                    atomic_criterion_id="atom-001",
                    entity="HbA1c",
                    relation="<",
                    value="7",
                    unit="%",
                ),
                ExpressionNode(
                    type="ATOMIC",
                    atomic_criterion_id="atom-002",
                    entity="eGFR",
                    relation=">",
                    value="30",
                    unit="mL/min",
                ),
            ],
        )
        dumped = node.model_dump()
        reconstructed = ExpressionNode.model_validate(dumped)
        assert reconstructed.type == "AND"
        assert len(reconstructed.children) == 2

    def test_structured_criterion_tree_roundtrip(self) -> None:
        """StructuredCriterionTree roundtrips with all fields."""
        tree = StructuredCriterionTree(
            root=ExpressionNode(
                type="ATOMIC",
                atomic_criterion_id="atom-001",
                entity="HbA1c",
                relation="<",
                value="7",
                unit="%",
            ),
            structure_confidence="llm",
            structure_model="gemini-2.0-flash",
        )
        dumped = tree.model_dump()
        reconstructed = StructuredCriterionTree.model_validate(dumped)
        assert reconstructed.structure_confidence == "llm"
        assert reconstructed.structure_model == "gemini-2.0-flash"
        assert reconstructed.root.type == "ATOMIC"


# ===========================================================================
# TestValidateLogicTree
# ===========================================================================


class TestValidateLogicTree:
    """Tests for _validate_logic_tree index validation."""

    def test_valid_atomic(self) -> None:
        """ATOMIC with valid index passes."""
        node = LogicNode(node_type="ATOMIC", field_mapping_index=0)
        assert _validate_logic_tree(node, 2) is True

    def test_invalid_atomic_out_of_range(self) -> None:
        """ATOMIC with out-of-range index fails."""
        node = LogicNode(node_type="ATOMIC", field_mapping_index=5)
        assert _validate_logic_tree(node, 2) is False

    def test_invalid_atomic_none_index(self) -> None:
        """ATOMIC with None index fails."""
        node = LogicNode(node_type="ATOMIC", field_mapping_index=None)
        assert _validate_logic_tree(node, 2) is False

    def test_valid_and_tree(self) -> None:
        """AND with two valid ATOMICs passes."""
        node = LogicNode(
            node_type="AND",
            children=[
                LogicNode(node_type="ATOMIC", field_mapping_index=0),
                LogicNode(node_type="ATOMIC", field_mapping_index=1),
            ],
        )
        assert _validate_logic_tree(node, 2) is True

    def test_invalid_child_fails_tree(self) -> None:
        """AND with one invalid child fails the whole tree."""
        node = LogicNode(
            node_type="AND",
            children=[
                LogicNode(node_type="ATOMIC", field_mapping_index=0),
                LogicNode(node_type="ATOMIC", field_mapping_index=99),
            ],
        )
        assert _validate_logic_tree(node, 2) is False

    def test_empty_children_fails(self) -> None:
        """AND with no children fails."""
        node = LogicNode(node_type="AND", children=None)
        assert _validate_logic_tree(node, 2) is False


# ===========================================================================
# TestParseValue
# ===========================================================================


class TestParseValue:
    """Tests for _parse_value numeric vs text parsing."""

    def test_integer_string(self) -> None:
        """Integer string parses to numeric."""
        numeric, text = _parse_value("7")
        assert numeric == 7.0
        assert text is None

    def test_float_string(self) -> None:
        """Float string parses to numeric."""
        numeric, text = _parse_value("7.5")
        assert numeric == 7.5
        assert text is None

    def test_text_string(self) -> None:
        """Non-numeric string parses to text."""
        numeric, text = _parse_value("positive")
        assert numeric is None
        assert text == "positive"

    def test_empty_string(self) -> None:
        """Empty string parses to text."""
        numeric, text = _parse_value("")
        assert numeric is None
        assert text == ""

    def test_none_value(self) -> None:
        """None parses to text."""
        numeric, text = _parse_value(None)  # type: ignore[arg-type]
        assert numeric is None
        assert text is None


# ===========================================================================
# TestDetectLogicStructure
# ===========================================================================


class TestDetectLogicStructure:
    """Tests for detect_logic_structure with mocked Gemini."""

    async def test_single_mapping_skips_llm(self) -> None:
        """Single field_mapping should return None (skip LLM)."""
        from protocol_processor.tools.structure_builder import (
            detect_logic_structure,
        )

        result = await detect_logic_structure("HbA1c < 7%", [_make_field_mapping()])
        assert result is None

    async def test_no_api_key_returns_none(self) -> None:
        """Missing GOOGLE_API_KEY returns None."""
        from protocol_processor.tools.structure_builder import (
            detect_logic_structure,
        )

        with patch.dict(os.environ, {}, clear=True):
            # Ensure no GOOGLE_API_KEY
            os.environ.pop("GOOGLE_API_KEY", None)
            result = await detect_logic_structure(
                "HbA1c < 7% AND eGFR > 30",
                [_make_field_mapping(), _make_field_mapping(entity="eGFR")],
            )
            assert result is None

    @patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"})
    @patch("langchain_google_genai.ChatGoogleGenerativeAI")
    async def test_successful_and_detection(self, mock_chat_cls: MagicMock) -> None:
        """Gemini returns valid AND tree -> LogicDetectionResponse."""
        from protocol_processor.tools.structure_builder import (
            detect_logic_structure,
        )

        response = LogicDetectionResponse(
            root=LogicNode(
                node_type="AND",
                children=[
                    LogicNode(node_type="ATOMIC", field_mapping_index=0),
                    LogicNode(node_type="ATOMIC", field_mapping_index=1),
                ],
            ),
            reasoning="Both conditions must be met.",
        )
        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(return_value=response)
        mock_instance = MagicMock()
        mock_instance.with_structured_output.return_value = mock_chain
        mock_chat_cls.return_value = mock_instance

        result = await detect_logic_structure(
            "HbA1c < 7% and eGFR > 30 mL/min",
            [
                _make_field_mapping(),
                _make_field_mapping(entity="eGFR", relation=">", value="30"),
            ],
        )

        assert result is not None
        assert result.root.node_type == "AND"
        assert len(result.root.children) == 2

    @patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"})
    @patch("langchain_google_genai.ChatGoogleGenerativeAI")
    async def test_invalid_indices_returns_none(self, mock_chat_cls: MagicMock) -> None:
        """Invalid field_mapping_index values -> returns None."""
        from protocol_processor.tools.structure_builder import (
            detect_logic_structure,
        )

        response = LogicDetectionResponse(
            root=LogicNode(
                node_type="AND",
                children=[
                    LogicNode(node_type="ATOMIC", field_mapping_index=0),
                    LogicNode(node_type="ATOMIC", field_mapping_index=99),
                ],
            ),
            reasoning="",
        )
        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(return_value=response)
        mock_instance = MagicMock()
        mock_instance.with_structured_output.return_value = mock_chain
        mock_chat_cls.return_value = mock_instance

        result = await detect_logic_structure(
            "HbA1c < 7% and eGFR > 30",
            [
                _make_field_mapping(),
                _make_field_mapping(entity="eGFR"),
            ],
        )

        assert result is None

    @patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"})
    @patch("langchain_google_genai.ChatGoogleGenerativeAI")
    async def test_llm_exception_returns_none(self, mock_chat_cls: MagicMock) -> None:
        """LLM exception -> returns None (triggers fallback)."""
        from protocol_processor.tools.structure_builder import (
            detect_logic_structure,
        )

        mock_instance = MagicMock()
        mock_instance.with_structured_output.side_effect = RuntimeError("API down")
        mock_chat_cls.return_value = mock_instance

        result = await detect_logic_structure(
            "HbA1c < 7% and eGFR > 30",
            [
                _make_field_mapping(),
                _make_field_mapping(entity="eGFR"),
            ],
        )

        assert result is None


# ===========================================================================
# TestBuildExpressionTree
# ===========================================================================


class TestBuildExpressionTree:
    """Tests for build_expression_tree with mocked session and LLM."""

    def _make_mock_session(self) -> MagicMock:
        """Create a mock session that tracks adds and flushes."""
        session = MagicMock()
        session.add = MagicMock()
        session.flush = MagicMock()
        return session

    async def test_single_mapping_produces_atomic_tree(self) -> None:
        """Single field_mapping -> ATOMIC root, no LLM call."""
        from protocol_processor.tools.structure_builder import (
            build_expression_tree,
        )

        session = self._make_mock_session()
        mappings = [_make_field_mapping()]

        tree = await build_expression_tree(
            criterion_text="HbA1c < 7%",
            field_mappings=mappings,
            criterion_id="crit-001",
            protocol_id="proto-001",
            inclusion_exclusion="inclusion",
            session=session,
        )

        assert tree.root.type == "ATOMIC"
        assert tree.structure_confidence == "fallback"
        assert tree.structure_model is None
        assert tree.root.entity == "HbA1c"
        assert tree.root.relation == "<"
        assert tree.root.value == "7"
        # AtomicCriterion should have been added to session
        assert session.add.called
        assert session.flush.called

    @patch(
        "protocol_processor.tools.structure_builder.detect_logic_structure",
        new_callable=AsyncMock,
    )
    async def test_multi_mapping_fallback_and(self, mock_detect: AsyncMock) -> None:
        """Multiple field_mappings + LLM failure -> AND fallback."""
        from protocol_processor.tools.structure_builder import (
            build_expression_tree,
        )

        mock_detect.return_value = None  # LLM fails

        session = self._make_mock_session()
        mappings = [
            _make_field_mapping(),
            _make_field_mapping(entity="eGFR", relation=">", value="30"),
        ]

        tree = await build_expression_tree(
            criterion_text="HbA1c < 7% and eGFR > 30",
            field_mappings=mappings,
            criterion_id="crit-002",
            protocol_id="proto-001",
            inclusion_exclusion="inclusion",
            session=session,
        )

        assert tree.root.type == "AND"
        assert tree.structure_confidence == "fallback"
        assert len(tree.root.children) == 2
        assert tree.root.children[0].entity == "HbA1c"
        assert tree.root.children[1].entity == "eGFR"

    @patch(
        "protocol_processor.tools.structure_builder.detect_logic_structure",
        new_callable=AsyncMock,
    )
    async def test_multi_mapping_llm_success(self, mock_detect: AsyncMock) -> None:
        """Multiple field_mappings + LLM success -> LLM tree."""
        from protocol_processor.tools.structure_builder import (
            build_expression_tree,
        )

        mock_detect.return_value = LogicDetectionResponse(
            root=LogicNode(
                node_type="OR",
                children=[
                    LogicNode(node_type="ATOMIC", field_mapping_index=0),
                    LogicNode(node_type="ATOMIC", field_mapping_index=1),
                ],
            ),
            reasoning="Either condition suffices.",
        )

        session = self._make_mock_session()
        mappings = [
            _make_field_mapping(),
            _make_field_mapping(entity="eGFR", relation=">", value="30"),
        ]

        tree = await build_expression_tree(
            criterion_text="HbA1c < 7% or eGFR > 30",
            field_mappings=mappings,
            criterion_id="crit-003",
            protocol_id="proto-001",
            inclusion_exclusion="inclusion",
            session=session,
        )

        assert tree.root.type == "OR"
        assert tree.structure_confidence == "llm"
        assert len(tree.root.children) == 2

    async def test_value_parsing_in_atomic(self) -> None:
        """Numeric values are stored as value_numeric, text as value_text."""
        from protocol_processor.tools.structure_builder import (
            build_expression_tree,
        )

        session = self._make_mock_session()

        # Track what gets added to session
        added_objects = []
        session.add.side_effect = lambda obj: added_objects.append(obj)

        mappings = [_make_field_mapping(value="7.5")]

        await build_expression_tree(
            criterion_text="HbA1c < 7.5%",
            field_mappings=mappings,
            criterion_id="crit-004",
            protocol_id="proto-001",
            inclusion_exclusion="inclusion",
            session=session,
        )

        # Find AtomicCriterion in added objects
        from shared.models import AtomicCriterion

        atomics = [o for o in added_objects if isinstance(o, AtomicCriterion)]
        assert len(atomics) == 1
        assert atomics[0].value_numeric == 7.5
        assert atomics[0].value_text is None


# ===========================================================================
# TestStructureNode
# ===========================================================================


class TestStructureNode:
    """Tests for structure_node pipeline node with mocked DB."""

    async def test_skip_on_error(self) -> None:
        """Node should return empty dict when state has fatal error."""
        from protocol_processor.nodes.structure import structure_node

        result = await structure_node(
            {  # type: ignore[arg-type]
                "error": "Previous node failed",
                "protocol_id": "proto-001",
                "batch_id": "batch-001",
                "errors": [],
            }
        )
        assert result == {}

    @patch("protocol_processor.nodes.structure.engine")
    @patch("protocol_processor.tracing.pipeline_span")
    async def test_skip_no_batch_id(
        self, mock_span_fn: MagicMock, mock_engine: MagicMock
    ) -> None:
        """Node should skip when batch_id is None."""
        # Import here to avoid import-time engine creation
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)
        mock_span.set_inputs = MagicMock()
        mock_span.set_outputs = MagicMock()
        mock_span_fn.return_value = mock_span

        from protocol_processor.nodes.structure import structure_node

        result = await structure_node(
            {  # type: ignore[arg-type]
                "error": None,
                "protocol_id": "proto-001",
                "batch_id": None,
                "errors": [],
            }
        )
        assert result["status"] == "completed"

    @patch("protocol_processor.nodes.structure.build_expression_tree")
    @patch("protocol_processor.nodes.structure.Session")
    @patch("protocol_processor.nodes.structure.engine")
    @patch("protocol_processor.tracing.pipeline_span")
    async def test_processes_qualifying_criteria(
        self,
        mock_span_fn: MagicMock,
        mock_engine: MagicMock,
        mock_session_cls: MagicMock,
        mock_build: MagicMock,
    ) -> None:
        """Node processes criteria with field_mappings and skips others."""
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)
        mock_span.set_inputs = MagicMock()
        mock_span.set_outputs = MagicMock()
        mock_span_fn.return_value = mock_span

        # Mock criteria: one with field_mappings, one without
        crit_with = MagicMock()
        crit_with.id = "crit-with"
        crit_with.text = "HbA1c < 7%"
        crit_with.criteria_type = "inclusion"
        crit_with.conditions = {
            "field_mappings": [
                {"entity": "HbA1c", "relation": "<", "value": "7", "unit": "%"}
            ]
        }

        crit_without = MagicMock()
        crit_without.id = "crit-without"
        crit_without.text = "Informed consent"
        crit_without.conditions = None

        # Session mock
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.exec.return_value.all.return_value = [crit_with, crit_without]
        mock_session_cls.return_value = mock_session

        # build_expression_tree mock
        mock_tree = StructuredCriterionTree(
            root=ExpressionNode(
                type="ATOMIC",
                atomic_criterion_id="atom-001",
                entity="HbA1c",
            ),
            structure_confidence="fallback",
        )
        mock_build.return_value = mock_tree

        from protocol_processor.nodes.structure import structure_node

        result = await structure_node(
            {  # type: ignore[arg-type]
                "error": None,
                "protocol_id": "proto-001",
                "batch_id": "batch-001",
                "errors": [],
            }
        )

        assert result["status"] == "completed"
        # build_expression_tree should have been called once (only for crit_with)
        mock_build.assert_called_once()

    @patch("protocol_processor.nodes.structure.build_expression_tree")
    @patch("protocol_processor.nodes.structure.Session")
    @patch("protocol_processor.nodes.structure.engine")
    @patch("protocol_processor.tracing.pipeline_span")
    async def test_error_accumulation(
        self,
        mock_span_fn: MagicMock,
        mock_engine: MagicMock,
        mock_session_cls: MagicMock,
        mock_build: MagicMock,
    ) -> None:
        """Criterion failures are accumulated, not fatal."""
        mock_span = MagicMock()
        mock_span.__enter__ = MagicMock(return_value=mock_span)
        mock_span.__exit__ = MagicMock(return_value=False)
        mock_span.set_inputs = MagicMock()
        mock_span.set_outputs = MagicMock()
        mock_span_fn.return_value = mock_span

        crit1 = MagicMock()
        crit1.id = "crit-fail"
        crit1.text = "will fail"
        crit1.criteria_type = "inclusion"
        crit1.conditions = {"field_mappings": [_make_field_mapping()]}

        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.exec.return_value.all.return_value = [crit1]
        mock_session_cls.return_value = mock_session

        mock_build.side_effect = RuntimeError("LLM exploded")

        from protocol_processor.nodes.structure import structure_node

        result = await structure_node(
            {  # type: ignore[arg-type]
                "error": None,
                "protocol_id": "proto-001",
                "batch_id": "batch-001",
                "errors": ["previous error"],
            }
        )

        assert result["status"] == "completed"
        # Should have the previous error + new error
        assert len(result["errors"]) >= 2
        assert "previous error" in result["errors"]
        assert any("Structure build failed" in e for e in result["errors"])
