"""Tests for field_mapper output format normalization.

Verifies that _normalize_relation() maps legacy operators correctly and
that generate_field_mappings() produces the expected typed value format
with correct key names.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from protocol_processor.schemas.grounding import EntityGroundingResult
from protocol_processor.tools.field_mapper import (
    FieldMappingItem,
    FieldMappingResponse,
    FieldMappingValue,
    _normalize_relation,
    generate_field_mappings,
)

# --- _normalize_relation tests ---


class TestNormalizeRelation:
    """Test the _normalize_relation() mapping function."""

    def test_has_maps_to_contains(self) -> None:
        assert _normalize_relation("has") == "contains"

    def test_is_maps_to_equals(self) -> None:
        assert _normalize_relation("is") == "="

    def test_not_maps_to_not_contains(self) -> None:
        assert _normalize_relation("not") == "not_contains"

    def test_double_equals_maps_to_equals(self) -> None:
        assert _normalize_relation("==") == "="

    def test_range_maps_to_within(self) -> None:
        assert _normalize_relation("range") == "within"

    def test_passthrough_standard_operators(self) -> None:
        for op in [
            "=",
            "!=",
            ">",
            ">=",
            "<",
            "<=",
            "within",
            "not_in_last",
            "contains",
            "not_contains",
        ]:
            assert _normalize_relation(op) == op

    def test_passthrough_unknown_operator(self) -> None:
        assert _normalize_relation("custom_op") == "custom_op"

    def test_empty_string_passthrough(self) -> None:
        assert _normalize_relation("") == ""


# --- generate_field_mappings output format tests ---


def _make_entity(**overrides: object) -> EntityGroundingResult:
    """Create a minimal EntityGroundingResult for testing."""
    defaults = {
        "entity_text": "HbA1c",
        "entity_type": "Lab_Value",
        "selected_code": "C0019018",
        "selected_system": "umls",
        "preferred_term": "Hemoglobin A1c",
        "confidence": 0.95,
        "omop_concept_id": "3004410",
    }
    defaults.update(overrides)
    return EntityGroundingResult(**defaults)


def _make_mapping_response(*items: FieldMappingItem) -> FieldMappingResponse:
    return FieldMappingResponse(mappings=list(items))


class TestGenerateFieldMappingsFormat:
    """Test that generate_field_mappings produces correctly formatted output."""

    @pytest.mark.asyncio
    async def test_output_has_typed_value_object(self) -> None:
        """Value should be a dict with 'type' discriminator, not a flat string."""
        entity = _make_entity()
        response = _make_mapping_response(
            FieldMappingItem(
                entity="HbA1c",
                relation="<",
                value=FieldMappingValue(type="standard", value="7", unit="%"),
            )
        )

        with (
            patch(
                "protocol_processor.tools.field_mapper.create_structured_llm"
            ) as mock_llm_factory,
            patch(
                "protocol_processor.tools.field_mapper.parse_structured_output",
                return_value=response,
            ),
        ):
            mock_llm = AsyncMock()
            mock_llm_factory.return_value = mock_llm

            result = await generate_field_mappings(entity, "HbA1c < 7%")

        assert len(result) == 1
        mapping = result[0]
        assert isinstance(mapping["value"], dict)
        assert mapping["value"]["type"] == "standard"
        assert mapping["value"]["value"] == "7"
        assert mapping["value"]["unit"] == "%"

    @pytest.mark.asyncio
    async def test_output_has_correct_key_names(self) -> None:
        """Should use entity_code/entity_system, not entity_concept_id."""
        entity = _make_entity()
        response = _make_mapping_response(
            FieldMappingItem(
                entity="HbA1c",
                relation="<",
                value=FieldMappingValue(type="standard", value="7", unit="%"),
            )
        )

        with (
            patch(
                "protocol_processor.tools.field_mapper.create_structured_llm"
            ) as mock_llm_factory,
            patch(
                "protocol_processor.tools.field_mapper.parse_structured_output",
                return_value=response,
            ),
        ):
            mock_llm = AsyncMock()
            mock_llm_factory.return_value = mock_llm

            result = await generate_field_mappings(entity, "HbA1c < 7%")

        mapping = result[0]
        assert "entity_code" in mapping
        assert "entity_system" in mapping
        assert "entity_concept_id" not in mapping
        assert "entity_concept_system" not in mapping
        assert mapping["entity_code"] == "C0019018"
        assert mapping["entity_system"] == "umls"

    @pytest.mark.asyncio
    async def test_output_includes_omop_concept_id(self) -> None:
        entity = _make_entity(omop_concept_id="3004410")
        response = _make_mapping_response(
            FieldMappingItem(
                entity="HbA1c",
                relation="<",
                value=FieldMappingValue(type="standard", value="7", unit="%"),
            )
        )

        with (
            patch(
                "protocol_processor.tools.field_mapper.create_structured_llm"
            ) as mock_llm_factory,
            patch(
                "protocol_processor.tools.field_mapper.parse_structured_output",
                return_value=response,
            ),
        ):
            mock_llm = AsyncMock()
            mock_llm_factory.return_value = mock_llm

            result = await generate_field_mappings(entity, "HbA1c < 7%")

        assert result[0]["omop_concept_id"] == "3004410"

    @pytest.mark.asyncio
    async def test_relation_is_normalized(self) -> None:
        """Legacy relation 'has' should be normalized to 'contains'."""
        entity = _make_entity()
        response = _make_mapping_response(
            FieldMappingItem(
                entity="Diabetes",
                relation="has",
                value=FieldMappingValue(type="standard", value="confirmed", unit=""),
            )
        )

        with (
            patch(
                "protocol_processor.tools.field_mapper.create_structured_llm"
            ) as mock_llm_factory,
            patch(
                "protocol_processor.tools.field_mapper.parse_structured_output",
                return_value=response,
            ),
        ):
            mock_llm = AsyncMock()
            mock_llm_factory.return_value = mock_llm

            result = await generate_field_mappings(entity, "Has diabetes")

        assert result[0]["relation"] == "contains"

    @pytest.mark.asyncio
    async def test_range_value_excludes_none_fields(self) -> None:
        """model_dump(exclude_none=True) should omit unused fields."""
        entity = _make_entity()
        response = _make_mapping_response(
            FieldMappingItem(
                entity="Age",
                relation="within",
                value=FieldMappingValue(type="range", min="18", max="65", unit="years"),
            )
        )

        with (
            patch(
                "protocol_processor.tools.field_mapper.create_structured_llm"
            ) as mock_llm_factory,
            patch(
                "protocol_processor.tools.field_mapper.parse_structured_output",
                return_value=response,
            ),
        ):
            mock_llm = AsyncMock()
            mock_llm_factory.return_value = mock_llm

            result = await generate_field_mappings(entity, "Age 18-65")

        val = result[0]["value"]
        assert val["type"] == "range"
        assert val["min"] == "18"
        assert val["max"] == "65"
        assert val["unit"] == "years"
        # Standard/temporal fields should not be present
        assert "value" not in val or val.get("value") is None
        assert "duration" not in val

    @pytest.mark.asyncio
    async def test_empty_criterion_text_returns_empty(self) -> None:
        entity = _make_entity()
        result = await generate_field_mappings(entity, "")
        assert result == []

    @pytest.mark.asyncio
    async def test_llm_unavailable_returns_empty(self) -> None:
        entity = _make_entity()
        with patch(
            "protocol_processor.tools.field_mapper.create_structured_llm",
            return_value=None,
        ):
            result = await generate_field_mappings(entity, "HbA1c < 7%")
        assert result == []
