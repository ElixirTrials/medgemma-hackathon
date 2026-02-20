"""Unit tests for Pydantic schemas: grounding and entity schemas.

Tests validation behavior for structured output models used by the
protocol-processor-service grounding pipeline.
"""

import pytest
from protocol_processor.schemas.grounding import (
    EntityGroundingResult,
    GroundingBatchResult,
    GroundingCandidate,
)
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# GroundingCandidate schema tests
# ---------------------------------------------------------------------------


class TestGroundingCandidate:
    """Tests for GroundingCandidate model."""

    def test_valid_umls_candidate(self) -> None:
        candidate = GroundingCandidate(
            source_api="umls",
            code="C0011849",
            preferred_term="Diabetes Mellitus",
            semantic_type="Disease or Syndrome",
            score=0.95,
        )
        assert candidate.code == "C0011849"
        assert candidate.source_api == "umls"
        assert candidate.preferred_term == "Diabetes Mellitus"
        assert candidate.semantic_type == "Disease or Syndrome"
        assert candidate.score == 0.95

    def test_valid_rxnorm_candidate_no_semantic_type(self) -> None:
        candidate = GroundingCandidate(
            source_api="rxnorm",
            code="6809",
            preferred_term="Metformin",
            score=0.9,
        )
        assert candidate.semantic_type is None

    def test_valid_icd10_candidate(self) -> None:
        candidate = GroundingCandidate(
            source_api="icd10",
            code="I10",
            preferred_term="Essential (primary) hypertension",
            score=1.0,
        )
        assert candidate.code == "I10"

    def test_valid_hpo_candidate(self) -> None:
        candidate = GroundingCandidate(
            source_api="hpo",
            code="HP:0002069",
            preferred_term="Bilateral tonic-clonic seizure",
            score=0.8,
        )
        assert candidate.code == "HP:0002069"

    def test_score_below_zero_raises(self) -> None:
        with pytest.raises(ValidationError):
            GroundingCandidate(
                source_api="umls",
                code="C0011849",
                preferred_term="Test",
                score=-0.1,
            )

    def test_score_above_one_raises(self) -> None:
        with pytest.raises(ValidationError):
            GroundingCandidate(
                source_api="umls",
                code="C0011849",
                preferred_term="Test",
                score=1.1,
            )

    def test_missing_required_fields_raises(self) -> None:
        with pytest.raises(ValidationError):
            GroundingCandidate(code="C0011849", preferred_term="Test")  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# EntityGroundingResult schema tests
# ---------------------------------------------------------------------------


class TestEntityGroundingResult:
    """Tests for EntityGroundingResult model."""

    def test_valid_successful_grounding(self) -> None:
        candidate = GroundingCandidate(
            source_api="icd10",
            code="E11.9",
            preferred_term="Type 2 diabetes mellitus without complications",
            score=0.98,
        )
        result = EntityGroundingResult(
            entity_text="type 2 diabetes mellitus",
            entity_type="Condition",
            selected_code="E11.9",
            selected_system="icd10",
            preferred_term="Type 2 diabetes mellitus without complications",
            confidence=0.98,
            candidates=[candidate],
            reasoning="Exact match for type 2 diabetes mellitus in ICD-10",
        )
        assert result.selected_code == "E11.9"
        assert result.selected_system == "icd10"
        assert result.confidence == 0.98
        assert len(result.candidates) == 1

    def test_failed_grounding_defaults(self) -> None:
        result = EntityGroundingResult(
            entity_text="consent",
            entity_type="Consent",
            confidence=0.0,
        )
        assert result.selected_code is None
        assert result.selected_system is None
        assert result.preferred_term is None
        assert result.candidates == []
        assert result.field_mappings is None

    def test_confidence_out_of_range_raises(self) -> None:
        with pytest.raises(ValidationError):
            EntityGroundingResult(
                entity_text="test",
                entity_type="Condition",
                confidence=1.5,
            )

    def test_with_field_mappings(self) -> None:
        result = EntityGroundingResult(
            entity_text="metformin",
            entity_type="Medication",
            selected_code="6809",
            selected_system="rxnorm",
            preferred_term="Metformin",
            confidence=0.95,
            field_mappings=[{"Entity": "metformin", "Code": "6809"}],
        )
        assert result.field_mappings is not None
        assert result.field_mappings[0]["Entity"] == "metformin"

    def test_missing_required_entity_text_raises(self) -> None:
        with pytest.raises(ValidationError):
            EntityGroundingResult(entity_type="Condition", confidence=0.5)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# GroundingBatchResult schema tests
# ---------------------------------------------------------------------------


class TestGroundingBatchResult:
    """Tests for GroundingBatchResult model."""

    def test_empty_batch(self) -> None:
        batch = GroundingBatchResult()
        assert batch.results == []
        assert batch.errors == []

    def test_batch_with_results(self) -> None:
        result1 = EntityGroundingResult(
            entity_text="hypertension",
            entity_type="Condition",
            selected_code="I10",
            selected_system="icd10",
            preferred_term="Essential (primary) hypertension",
            confidence=0.99,
        )
        result2 = EntityGroundingResult(
            entity_text="age",
            entity_type="Demographic",
            confidence=0.0,
            reasoning="No candidates found for demographic entity",
        )
        batch = GroundingBatchResult(results=[result1, result2])
        assert len(batch.results) == 2
        assert batch.results[0].entity_text == "hypertension"
        assert batch.results[1].entity_text == "age"

    def test_batch_with_errors(self) -> None:
        batch = GroundingBatchResult(
            results=[],
            errors=["Entity 'xyz' failed: timeout", "Entity 'abc' failed: auth error"],
        )
        assert len(batch.errors) == 2
        assert "timeout" in batch.errors[0]
