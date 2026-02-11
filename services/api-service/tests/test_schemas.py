"""Unit tests for Pydantic schemas: criteria extraction and entity extraction.

Tests validation behavior for structured output models used by
ChatVertexAI.with_structured_output() in the extraction pipeline.
"""

import pytest
from extraction_service.schemas.criteria import (
    AssertionStatus,
    ExtractedCriterion,
    ExtractionResult,
    NumericThreshold,
    TemporalConstraint,
)
from grounding_service.schemas.entities import (
    BatchEntityExtractionResult,
    EntityExtractionResult,
    EntityType,
    ExtractedEntity,
)
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Criteria schema tests (extraction-service)
# ---------------------------------------------------------------------------


class TestTemporalConstraint:
    """Tests for TemporalConstraint model."""

    def test_all_fields_none_by_default(self) -> None:
        tc = TemporalConstraint()
        assert tc.duration is None
        assert tc.relation is None
        assert tc.reference_point is None

    def test_with_all_fields(self) -> None:
        tc = TemporalConstraint(
            duration="6 months",
            relation="within",
            reference_point="screening",
        )
        assert tc.duration == "6 months"
        assert tc.relation == "within"
        assert tc.reference_point == "screening"


class TestNumericThreshold:
    """Tests for NumericThreshold model."""

    def test_valid_threshold(self) -> None:
        nt = NumericThreshold(value=8.0, unit="%", comparator="<")
        assert nt.value == 8.0
        assert nt.unit == "%"
        assert nt.comparator == "<"
        assert nt.upper_value is None

    def test_range_with_upper_value(self) -> None:
        nt = NumericThreshold(
            value=18.0, unit="years", comparator="range", upper_value=65.0
        )
        assert nt.upper_value == 65.0

    def test_missing_required_fields_raises(self) -> None:
        with pytest.raises(ValidationError):
            NumericThreshold(value=1.0)  # type: ignore[call-arg]


class TestAssertionStatus:
    """Tests for AssertionStatus enum."""

    @pytest.mark.parametrize(
        "status",
        ["PRESENT", "ABSENT", "HYPOTHETICAL", "HISTORICAL", "CONDITIONAL"],
    )
    def test_valid_values(self, status: str) -> None:
        assert AssertionStatus(status).value == status

    def test_invalid_value_raises(self) -> None:
        with pytest.raises(ValueError):
            AssertionStatus("INVALID")


class TestExtractedCriterion:
    """Tests for ExtractedCriterion model."""

    def test_valid_inclusion_criterion(self) -> None:
        ec = ExtractedCriterion(
            text="Age >= 18 years",
            criteria_type="inclusion",
            assertion_status=AssertionStatus.PRESENT,
            confidence=0.95,
        )
        assert ec.text == "Age >= 18 years"
        assert ec.criteria_type == "inclusion"
        assert ec.category is None
        assert ec.temporal_constraint is None
        assert ec.conditions == []
        assert ec.numeric_thresholds == []

    def test_valid_exclusion_criterion_with_all_fields(self) -> None:
        ec = ExtractedCriterion(
            text="HbA1c < 8% within 30 days of screening",
            criteria_type="exclusion",
            category="lab_values",
            temporal_constraint=TemporalConstraint(
                duration="30 days",
                relation="within",
                reference_point="screening",
            ),
            conditions=["if diabetic"],
            numeric_thresholds=[NumericThreshold(value=8.0, unit="%", comparator="<")],
            assertion_status=AssertionStatus.ABSENT,
            confidence=0.88,
            source_section="Exclusion Criteria",
        )
        assert ec.criteria_type == "exclusion"
        assert ec.temporal_constraint is not None
        assert ec.temporal_constraint.duration == "30 days"
        assert len(ec.numeric_thresholds) == 1
        assert ec.conditions == ["if diabetic"]

    def test_missing_required_fields_raises(self) -> None:
        with pytest.raises(ValidationError):
            ExtractedCriterion(text="test")  # type: ignore[call-arg]

    def test_confidence_out_of_range_raises(self) -> None:
        with pytest.raises(ValidationError):
            ExtractedCriterion(
                text="test",
                criteria_type="inclusion",
                assertion_status=AssertionStatus.PRESENT,
                confidence=1.5,
            )


class TestExtractionResult:
    """Tests for ExtractionResult model."""

    def test_with_criteria_list(self) -> None:
        criterion = ExtractedCriterion(
            text="Age >= 18",
            criteria_type="inclusion",
            assertion_status=AssertionStatus.PRESENT,
            confidence=0.9,
        )
        result = ExtractionResult(
            criteria=[criterion],
            protocol_summary="Phase III diabetes trial for adults",
        )
        assert len(result.criteria) == 1
        assert result.protocol_summary == "Phase III diabetes trial for adults"

    def test_empty_criteria_list(self) -> None:
        result = ExtractionResult(criteria=[], protocol_summary="No criteria found")
        assert result.criteria == []


# ---------------------------------------------------------------------------
# Entity schema tests (grounding-service)
# ---------------------------------------------------------------------------


class TestEntityType:
    """Tests for EntityType enum."""

    @pytest.mark.parametrize(
        "value",
        [
            "Condition",
            "Medication",
            "Procedure",
            "Lab_Value",
            "Demographic",
            "Biomarker",
        ],
    )
    def test_valid_entity_types(self, value: str) -> None:
        assert EntityType(value).value == value

    def test_invalid_entity_type_raises(self) -> None:
        with pytest.raises(ValueError):
            EntityType("InvalidType")


class TestExtractedEntity:
    """Tests for ExtractedEntity model."""

    def test_valid_entity(self) -> None:
        entity = ExtractedEntity(
            text="diabetes mellitus",
            entity_type=EntityType.CONDITION,
            span_start=0,
            span_end=18,
            context_window="Patient with diabetes mellitus type 2",
        )
        assert entity.text == "diabetes mellitus"
        assert entity.entity_type == EntityType.CONDITION
        assert entity.span_start == 0
        assert entity.span_end == 18

    def test_missing_required_fields_raises(self) -> None:
        with pytest.raises(ValidationError):
            ExtractedEntity(text="test")  # type: ignore[call-arg]


class TestEntityExtractionResult:
    """Tests for EntityExtractionResult model."""

    def test_with_entities(self) -> None:
        entity = ExtractedEntity(
            text="metformin",
            entity_type=EntityType.MEDICATION,
            span_start=10,
            span_end=19,
            context_window="taking metformin daily",
        )
        result = EntityExtractionResult(
            entities=[entity],
            criterion_id="crit-001",
        )
        assert len(result.entities) == 1
        assert result.criterion_id == "crit-001"

    def test_empty_entities(self) -> None:
        result = EntityExtractionResult(entities=[], criterion_id="crit-002")
        assert result.entities == []


class TestBatchEntityExtractionResult:
    """Tests for BatchEntityExtractionResult model."""

    def test_with_multiple_results(self) -> None:
        result1 = EntityExtractionResult(
            entities=[
                ExtractedEntity(
                    text="HbA1c",
                    entity_type=EntityType.LAB_VALUE,
                    span_start=0,
                    span_end=5,
                    context_window="HbA1c < 8%",
                )
            ],
            criterion_id="crit-001",
        )
        result2 = EntityExtractionResult(
            entities=[
                ExtractedEntity(
                    text="age",
                    entity_type=EntityType.DEMOGRAPHIC,
                    span_start=0,
                    span_end=3,
                    context_window="age >= 18 years",
                )
            ],
            criterion_id="crit-002",
        )
        batch = BatchEntityExtractionResult(results=[result1, result2])
        assert len(batch.results) == 2
        assert batch.results[0].criterion_id == "crit-001"
        assert batch.results[1].criterion_id == "crit-002"
