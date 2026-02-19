"""Tests for Phase 1b changes: concept ID wiring, criterion_id lookup, accumulation.

Covers:
1. Field mapping concept ID enrichment (field_mapper.py)
2. Criterion ID-based direct lookup (persist.py)
3. Field mapping accumulation (persist.py)
4. EntityGroundingResult schema fields (grounding.py)

All DB interactions are mocked -- no live database required.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock, patch

from protocol_processor.schemas.grounding import EntityGroundingResult
from protocol_processor.tools.field_mapper import (
    FieldMappingItem,
    FieldMappingResponse,
    generate_field_mappings,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_entity(**overrides: Any) -> EntityGroundingResult:
    """Build an EntityGroundingResult with sensible defaults."""
    defaults: dict[str, Any] = {
        "entity_text": "type 2 diabetes",
        "entity_type": "Condition",
        "selected_code": None,
        "selected_system": None,
        "preferred_term": None,
        "confidence": 0.9,
        "candidates": [],
        "reasoning": "",
    }
    defaults.update(overrides)
    return EntityGroundingResult(**defaults)


def _make_criteria_mock(**overrides: Any) -> MagicMock:
    """Build a mock Criteria record with mutable .conditions."""
    mock = MagicMock()
    mock.id = overrides.get("id", "crit-001")
    mock.batch_id = overrides.get("batch_id", "batch-001")
    mock.text = overrides.get("text", "HbA1c < 7%")
    mock.conditions = overrides.get("conditions", None)
    return mock


# ===========================================================================
# TestFieldMappingConceptIds
# ===========================================================================


class TestFieldMappingConceptIds:
    """Test that field_mapper includes concept IDs in mapping dicts."""

    @patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"})
    @patch("langchain_google_genai.ChatGoogleGenerativeAI")
    async def test_mappings_include_concept_ids(self, mock_chat_cls: MagicMock) -> None:
        """Mapping dicts should contain all three concept ID keys."""
        response = FieldMappingResponse(
            mappings=[
                FieldMappingItem(entity="HbA1c", relation="<", value="7", unit="%")
            ]
        )
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = response
        mock_instance = MagicMock()
        mock_instance.with_structured_output.return_value = mock_chain
        mock_chat_cls.return_value = mock_instance

        entity = _make_entity(
            entity_text="HbA1c",
            selected_code="C0011847",
            selected_system="umls",
            preferred_term="Hemoglobin A1c",
            omop_concept_id="201826",
        )

        mappings = await generate_field_mappings(entity, "HbA1c < 7%")

        assert len(mappings) == 1
        assert mappings[0]["entity_concept_id"] == "C0011847"
        assert mappings[0]["entity_concept_system"] == "umls"
        assert mappings[0]["omop_concept_id"] == "201826"

    @patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"})
    @patch("langchain_google_genai.ChatGoogleGenerativeAI")
    async def test_mappings_with_null_omop(self, mock_chat_cls: MagicMock) -> None:
        """Missing omop_concept_id yields None in mapping."""
        response = FieldMappingResponse(
            mappings=[
                FieldMappingItem(entity="eGFR", relation=">", value="30", unit="mL/min")
            ]
        )
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = response
        mock_instance = MagicMock()
        mock_instance.with_structured_output.return_value = mock_chain
        mock_chat_cls.return_value = mock_instance

        entity = _make_entity(
            entity_text="eGFR",
            selected_code="C0017654",
            selected_system="umls",
            preferred_term="Glomerular Filtration Rate",
            omop_concept_id=None,
        )

        mappings = await generate_field_mappings(entity, "eGFR > 30 mL/min")

        assert len(mappings) == 1
        assert mappings[0]["entity_concept_id"] == "C0017654"
        assert mappings[0]["entity_concept_system"] == "umls"
        assert mappings[0]["omop_concept_id"] is None

    @patch.dict(os.environ, {"GOOGLE_API_KEY": "test-key"})
    @patch("langchain_google_genai.ChatGoogleGenerativeAI")
    async def test_mappings_with_null_code(self, mock_chat_cls: MagicMock) -> None:
        """No selected_code means concept ID fields are None."""
        response = FieldMappingResponse(
            mappings=[
                FieldMappingItem(entity="BMI", relation="<", value="40", unit="kg/m2")
            ]
        )
        mock_chain = MagicMock()
        mock_chain.invoke.return_value = response
        mock_instance = MagicMock()
        mock_instance.with_structured_output.return_value = mock_chain
        mock_chat_cls.return_value = mock_instance

        entity = _make_entity(
            entity_text="BMI",
            selected_code=None,
            selected_system=None,
            preferred_term=None,
            omop_concept_id=None,
        )

        mappings = await generate_field_mappings(entity, "BMI < 40 kg/m2")

        assert len(mappings) == 1
        assert mappings[0]["entity_concept_id"] is None
        assert mappings[0]["entity_concept_system"] is None
        assert mappings[0]["omop_concept_id"] is None


# ===========================================================================
# TestCriterionIdLookup
# ===========================================================================


class TestCriterionIdLookup:
    """Test criterion_id-based direct lookup in persist."""

    def test_direct_lookup_by_criterion_id(self) -> None:
        """When criterion_id is provided, session.get() is used."""
        from protocol_processor.nodes.persist import (
            _find_criterion_and_update_mappings,
        )

        mock_session = MagicMock()
        mock_criterion = _make_criteria_mock(id="crit-direct", conditions=None)
        mock_session.get.return_value = mock_criterion

        result = _find_criterion_and_update_mappings(
            session=mock_session,
            batch_id="batch-001",
            entity_text="diabetes",
            field_mappings=None,
            criterion_id="crit-direct",
        )

        assert result == "crit-direct"
        mock_session.get.assert_called_once()
        # Should NOT have done a substring search
        mock_session.exec.assert_not_called()

    @patch("sqlmodel.select")
    def test_fallback_to_substring_when_no_criterion_id(
        self, mock_select: MagicMock
    ) -> None:
        """When criterion_id is None, falls back to substring search."""
        from protocol_processor.nodes.persist import (
            _find_criterion_and_update_mappings,
        )

        mock_session = MagicMock()
        mock_criterion = _make_criteria_mock(id="crit-fallback")
        mock_session.exec.return_value.all.return_value = [mock_criterion]

        result = _find_criterion_and_update_mappings(
            session=mock_session,
            batch_id="batch-001",
            entity_text="diabetes",
            field_mappings=None,
            criterion_id=None,
        )

        assert result == "crit-fallback"
        # session.get should not have been called
        mock_session.get.assert_not_called()
        # Should have used exec() for substring search
        mock_session.exec.assert_called_once()

    @patch("sqlmodel.select")
    def test_fallback_to_substring_when_criterion_id_not_found(
        self, mock_select: MagicMock
    ) -> None:
        """session.get returns None -> falls back to substring search."""
        from protocol_processor.nodes.persist import (
            _find_criterion_and_update_mappings,
        )

        mock_session = MagicMock()
        # Direct lookup returns None
        mock_session.get.return_value = None
        # Substring fallback finds a match
        mock_criterion = _make_criteria_mock(id="crit-substr")
        mock_session.exec.return_value.all.return_value = [mock_criterion]

        result = _find_criterion_and_update_mappings(
            session=mock_session,
            batch_id="batch-001",
            entity_text="diabetes",
            field_mappings=None,
            criterion_id="crit-nonexistent",
        )

        assert result == "crit-substr"
        # Should have tried direct lookup first
        mock_session.get.assert_called_once()
        # Then fallen back to substring search
        mock_session.exec.assert_called_once()


# ===========================================================================
# TestFieldMappingAccumulation
# ===========================================================================


class TestFieldMappingAccumulation:
    """Test that field_mappings accumulate, not overwrite (Gap 2 fix)."""

    def test_new_mappings_extend_existing(self) -> None:
        """New field_mappings should be appended to existing ones."""
        from protocol_processor.nodes.persist import (
            _find_criterion_and_update_mappings,
        )

        existing_mappings = [
            {
                "entity": "HbA1c",
                "relation": "<",
                "value": "7",
                "unit": "%",
            }
        ]
        mock_criterion = _make_criteria_mock(
            id="crit-accum",
            conditions={"field_mappings": existing_mappings},
        )
        mock_session = MagicMock()
        mock_session.get.return_value = mock_criterion

        new_mappings = [
            {
                "entity": "eGFR",
                "relation": ">",
                "value": "30",
                "unit": "mL/min",
            }
        ]

        _find_criterion_and_update_mappings(
            session=mock_session,
            batch_id="batch-001",
            entity_text="eGFR",
            field_mappings=new_mappings,
            criterion_id="crit-accum",
        )

        final = mock_criterion.conditions["field_mappings"]
        assert len(final) == 2
        entities = [m["entity"] for m in final]
        assert "HbA1c" in entities
        assert "eGFR" in entities

    def test_first_entity_creates_list(self) -> None:
        """Empty conditions gets field_mappings set directly."""
        from protocol_processor.nodes.persist import (
            _find_criterion_and_update_mappings,
        )

        mock_criterion = _make_criteria_mock(id="crit-new", conditions={})
        mock_session = MagicMock()
        mock_session.get.return_value = mock_criterion

        new_mappings = [
            {
                "entity": "HbA1c",
                "relation": "<",
                "value": "7",
                "unit": "%",
            }
        ]

        _find_criterion_and_update_mappings(
            session=mock_session,
            batch_id="batch-001",
            entity_text="HbA1c",
            field_mappings=new_mappings,
            criterion_id="crit-new",
        )

        final = mock_criterion.conditions["field_mappings"]
        assert len(final) == 1
        assert final[0]["entity"] == "HbA1c"

    def test_multiple_calls_accumulate(self) -> None:
        """Three calls should accumulate all mappings."""
        from protocol_processor.nodes.persist import (
            _find_criterion_and_update_mappings,
        )

        mock_criterion = _make_criteria_mock(id="crit-multi", conditions={})
        mock_session = MagicMock()
        mock_session.get.return_value = mock_criterion

        entities_and_mappings = [
            (
                "HbA1c",
                [{"entity": "HbA1c", "relation": "<", "value": "7", "unit": "%"}],
            ),
            (
                "eGFR",
                [{"entity": "eGFR", "relation": ">", "value": "30", "unit": "mL/min"}],
            ),
            (
                "BMI",
                [{"entity": "BMI", "relation": "<", "value": "40", "unit": "kg/m2"}],
            ),
        ]

        for entity_text, mappings in entities_and_mappings:
            _find_criterion_and_update_mappings(
                session=mock_session,
                batch_id="batch-001",
                entity_text=entity_text,
                field_mappings=mappings,
                criterion_id="crit-multi",
            )

        final = mock_criterion.conditions["field_mappings"]
        assert len(final) == 3
        entities = [m["entity"] for m in final]
        assert entities == ["HbA1c", "eGFR", "BMI"]


# ===========================================================================
# TestEntityGroundingResultHasCriterionId
# ===========================================================================


class TestEntityGroundingResultHasCriterionId:
    """Schema tests for Phase 1b fields on EntityGroundingResult."""

    def test_criterion_id_field_exists(self) -> None:
        """criterion_id round-trips through model_dump."""
        entity = _make_entity(criterion_id="test-id")
        dumped = entity.model_dump()

        assert dumped["criterion_id"] == "test-id"
        # Round-trip: reconstruct from dump
        reconstructed = EntityGroundingResult(**dumped)
        assert reconstructed.criterion_id == "test-id"

    def test_omop_fields_exist(self) -> None:
        """omop_concept_id and reconciliation_status are accepted."""
        entity = _make_entity(
            omop_concept_id="201826",
            reconciliation_status="agree",
        )
        dumped = entity.model_dump()

        assert dumped["omop_concept_id"] == "201826"
        assert dumped["reconciliation_status"] == "agree"

    def test_criterion_id_defaults_to_none(self) -> None:
        """criterion_id should default to None when not provided."""
        entity = _make_entity()
        assert entity.criterion_id is None

    def test_omop_fields_default_to_none(self) -> None:
        """OMOP and reconciliation fields default to None."""
        entity = _make_entity()
        assert entity.omop_concept_id is None
        assert entity.reconciliation_status is None
