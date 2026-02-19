"""Tests for OMOP mapper tool and dual grounding reconciliation logic.

Tests cover:
- _score_candidates: fuzzy scoring with exact/substring bonuses
- _get_domain_filter: entity type to OMOP domain mapping
- lookup_omop_concept: async entry point with mocked DB layer
- _reconcile_dual_grounding: TerminologyRouter + OMOP reconciliation

All tests run without a live database. DB calls are mocked/patched.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from protocol_processor.nodes.ground import _reconcile_dual_grounding
from protocol_processor.schemas.grounding import EntityGroundingResult
from protocol_processor.tools.omop_mapper import (
    ENTITY_TYPE_TO_OMOP_DOMAIN,
    OmopLookupResult,
    _get_domain_filter,
    _score_candidates,
    lookup_omop_concept,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_candidate(match_text: str, **extra: object) -> dict:
    """Build a minimal candidate dict for _score_candidates."""
    base = {
        "concept_id": "12345",
        "concept_name": match_text,
        "domain_id": "Condition",
        "vocabulary_id": "SNOMED",
        "match_text": match_text,
        "match_method": "concept_name",
    }
    base.update(extra)
    return base


def _make_grounding_result(**overrides: object) -> EntityGroundingResult:
    """Build an EntityGroundingResult with sensible defaults."""
    defaults: dict = {
        "entity_text": "type 2 diabetes",
        "entity_type": "Condition",
        "selected_code": None,
        "selected_system": None,
        "preferred_term": None,
        "confidence": 0.0,
        "candidates": [],
        "reasoning": "",
    }
    defaults.update(overrides)
    return EntityGroundingResult(**defaults)


# ===========================================================================
# TestScoreCandidates
# ===========================================================================


class TestScoreCandidates:
    """Tests for _score_candidates fuzzy scoring logic."""

    def test_exact_match_gets_highest_score(self) -> None:
        """An exact case-insensitive match should receive a 0.25 bonus."""
        candidates = [_make_candidate("Type 2 Diabetes Mellitus")]
        scored = _score_candidates("type 2 diabetes mellitus", candidates)
        # SequenceMatcher ratio for identical strings is 1.0
        # bonus for exact match is 0.25, but capped at 1.0
        assert scored[0]["score"] == 1.0

    def test_substring_containment_gets_bonus(self) -> None:
        """Substring containment (either direction) should add a 0.15 bonus."""
        candidates = [_make_candidate("Type 2 Diabetes Mellitus")]
        scored = _score_candidates("diabetes", candidates)
        # "diabetes" is a substring of "type 2 diabetes mellitus"
        # So bonus should be 0.15 (not 0.25, since not exact)
        assert scored[0]["score"] > 0.0
        # Verify by computing what the score would be without bonus
        from difflib import SequenceMatcher

        base = SequenceMatcher(
            None, "diabetes", "type 2 diabetes mellitus"
        ).ratio()
        assert scored[0]["score"] == pytest.approx(base + 0.15, abs=1e-6)

    def test_non_matching_gets_only_base_score(self) -> None:
        """A candidate with no substring overlap gets only the base score."""
        candidates = [_make_candidate("Hypertension")]
        scored = _score_candidates("metformin", candidates)
        from difflib import SequenceMatcher

        expected_base = SequenceMatcher(
            None, "metformin", "hypertension"
        ).ratio()
        assert scored[0]["score"] == pytest.approx(expected_base, abs=1e-6)

    def test_candidates_sorted_descending(self) -> None:
        """Candidates must be sorted by score in descending order."""
        candidates = [
            _make_candidate("Hypertension"),
            _make_candidate("Type 2 Diabetes Mellitus"),
            _make_candidate("Diabetes"),
        ]
        scored = _score_candidates("diabetes", candidates)
        scores = [c["score"] for c in scored]
        assert scores == sorted(scores, reverse=True)

    def test_empty_candidates_returns_empty(self) -> None:
        """An empty candidate list should return an empty list."""
        scored = _score_candidates("diabetes", [])
        assert scored == []

    def test_score_capped_at_one(self) -> None:
        """Score must never exceed 1.0 even with bonus."""
        # Exact match: base=1.0 + bonus=0.25 should be capped to 1.0
        candidates = [_make_candidate("metformin")]
        scored = _score_candidates("metformin", candidates)
        assert scored[0]["score"] <= 1.0

    def test_case_insensitive_matching(self) -> None:
        """Scoring should be case-insensitive."""
        candidates = [_make_candidate("METFORMIN")]
        scored = _score_candidates("metformin", candidates)
        # Exact case-insensitive match
        assert scored[0]["score"] == 1.0

    def test_whitespace_stripped(self) -> None:
        """Leading/trailing whitespace should not affect scoring."""
        candidates = [_make_candidate("  metformin  ")]
        scored = _score_candidates("  metformin  ", candidates)
        assert scored[0]["score"] == 1.0


# ===========================================================================
# TestGetDomainFilter
# ===========================================================================


class TestGetDomainFilter:
    """Tests for _get_domain_filter entity type to OMOP domain mapping."""

    def test_condition_maps_to_condition(self) -> None:
        """'Condition' entity type maps to 'Condition' OMOP domain."""
        assert _get_domain_filter("Condition") == "Condition"

    def test_medication_maps_to_drug(self) -> None:
        """'Medication' entity type maps to 'Drug' OMOP domain."""
        assert _get_domain_filter("Medication") == "Drug"

    def test_lab_value_maps_to_measurement(self) -> None:
        """'Lab_Value' entity type maps to 'Measurement' OMOP domain."""
        assert _get_domain_filter("Lab_Value") == "Measurement"

    def test_procedure_maps_to_procedure(self) -> None:
        """'Procedure' entity type maps to 'Procedure' OMOP domain."""
        assert _get_domain_filter("Procedure") == "Procedure"

    def test_demographic_maps_to_observation(self) -> None:
        """'Demographic' entity type maps to 'Observation' OMOP domain."""
        assert _get_domain_filter("Demographic") == "Observation"

    def test_unknown_type_falls_back_to_observation(self) -> None:
        """Unknown entity types should fall back to 'Observation'."""
        assert _get_domain_filter("UnknownEntityType") == "Observation"

    def test_all_mapped_types_present(self) -> None:
        """All documented entity types must be present in the mapping dict."""
        expected_keys = {
            "Condition", "Medication", "Lab_Value",
            "Procedure", "Demographic",
        }
        assert expected_keys == set(ENTITY_TYPE_TO_OMOP_DOMAIN.keys())


# ===========================================================================
# TestLookupOmopConcept
# ===========================================================================


class TestLookupOmopConcept:
    """Tests for the async lookup_omop_concept entry point."""

    async def test_empty_entity_text_returns_empty_result(self) -> None:
        """Empty entity_text should short-circuit and return empty result."""
        result = await lookup_omop_concept("", "Condition")
        assert result.omop_concept_id is None
        assert result.match_score == 0.0

    async def test_whitespace_entity_text_returns_empty_result(self) -> None:
        """Whitespace-only entity_text should return empty result."""
        result = await lookup_omop_concept("   ", "Condition")
        assert result.omop_concept_id is None
        assert result.match_score == 0.0

    @patch("protocol_processor.tools.omop_mapper._sync_lookup")
    async def test_valid_lookup_returns_result(
        self, mock_sync_lookup: AsyncMock
    ) -> None:
        """A successful lookup should return the OmopLookupResult from _sync_lookup."""
        expected = OmopLookupResult(
            omop_concept_id="201826",
            omop_concept_name="Type 2 diabetes mellitus",
            omop_vocabulary_id="SNOMED",
            omop_domain_id="Condition",
            match_score=0.95,
            match_method="concept_name",
        )
        mock_sync_lookup.return_value = expected

        result = await lookup_omop_concept("type 2 diabetes", "Condition")

        assert result.omop_concept_id == "201826"
        assert result.omop_concept_name == "Type 2 diabetes mellitus"
        assert result.match_score == 0.95
        # Verify domain_id was correctly resolved and passed
        mock_sync_lookup.assert_called_once_with("type 2 diabetes", "Condition")

    @patch("protocol_processor.tools.omop_mapper._sync_lookup")
    async def test_medication_passes_drug_domain(
        self, mock_sync_lookup: AsyncMock
    ) -> None:
        """Medication entity type should resolve to 'Drug' domain_id."""
        mock_sync_lookup.return_value = OmopLookupResult()

        await lookup_omop_concept("metformin", "Medication")

        mock_sync_lookup.assert_called_once_with("metformin", "Drug")

    @patch("protocol_processor.tools.omop_mapper._sync_lookup")
    async def test_unknown_type_passes_observation_domain(
        self, mock_sync_lookup: AsyncMock
    ) -> None:
        """Unknown entity type should fall back to 'Observation' domain."""
        mock_sync_lookup.return_value = OmopLookupResult()

        await lookup_omop_concept("some entity", "WeirdType")

        mock_sync_lookup.assert_called_once_with("some entity", "Observation")


# ===========================================================================
# TestReconcileDualGrounding
# ===========================================================================


class TestReconcileDualGrounding:
    """Tests for _reconcile_dual_grounding from ground.py."""

    def test_both_succeed_matching_terms_agree(self) -> None:
        """Both TU and OMOP succeed with overlapping terms: status = 'agree'."""
        result = _make_grounding_result(
            selected_code="C0011847",
            preferred_term="Type 2 Diabetes Mellitus",
        )
        omop_result = OmopLookupResult(
            omop_concept_id="201826",
            omop_concept_name="Type 2 Diabetes Mellitus",
            match_score=0.95,
        )

        reconciled = _reconcile_dual_grounding(result, omop_result)

        assert reconciled.reconciliation_status == "agree"
        assert reconciled.omop_concept_id == "201826"

    def test_both_succeed_substring_match_agree(self) -> None:
        """Substring containment (TU term in OMOP term) counts as agreement."""
        result = _make_grounding_result(
            selected_code="C0011847",
            preferred_term="Diabetes",
        )
        omop_result = OmopLookupResult(
            omop_concept_id="201826",
            omop_concept_name="Type 2 Diabetes Mellitus",
            match_score=0.90,
        )

        reconciled = _reconcile_dual_grounding(result, omop_result)

        assert reconciled.reconciliation_status == "agree"

    def test_both_succeed_non_matching_terms_disagreement(self) -> None:
        """Both succeed but terms don't overlap: status = 'disagreement'."""
        result = _make_grounding_result(
            selected_code="C0011847",
            preferred_term="Type 2 Diabetes Mellitus",
        )
        omop_result = OmopLookupResult(
            omop_concept_id="999999",
            omop_concept_name="Hypertension",
            match_score=0.80,
        )

        reconciled = _reconcile_dual_grounding(result, omop_result)

        assert reconciled.reconciliation_status == "disagreement"
        assert reconciled.omop_concept_id == "999999"

    def test_only_tu_succeeds_omop_missing(self) -> None:
        """Only TerminologyRouter succeeds: status = 'omop_missing'."""
        result = _make_grounding_result(
            selected_code="C0011847",
            preferred_term="Type 2 Diabetes Mellitus",
        )
        omop_result = OmopLookupResult()  # empty — no match

        reconciled = _reconcile_dual_grounding(result, omop_result)

        assert reconciled.reconciliation_status == "omop_missing"
        assert reconciled.omop_concept_id is None

    def test_only_omop_succeeds_tooluniverse_missing(self) -> None:
        """Only OMOP succeeds: status = 'tooluniverse_missing'."""
        result = _make_grounding_result(
            selected_code=None,
            preferred_term=None,
        )
        omop_result = OmopLookupResult(
            omop_concept_id="201826",
            omop_concept_name="Type 2 Diabetes Mellitus",
            match_score=0.90,
        )

        reconciled = _reconcile_dual_grounding(result, omop_result)

        assert reconciled.reconciliation_status == "tooluniverse_missing"
        assert reconciled.omop_concept_id == "201826"

    def test_neither_succeeds_no_status_set(self) -> None:
        """Neither source succeeds: reconciliation_status stays None."""
        result = _make_grounding_result(
            selected_code=None,
            preferred_term=None,
        )
        omop_result = OmopLookupResult()  # empty

        reconciled = _reconcile_dual_grounding(result, omop_result)

        assert reconciled.reconciliation_status is None
        assert reconciled.omop_concept_id is None

    def test_result_is_mutated_in_place(self) -> None:
        """_reconcile_dual_grounding should mutate and return the same object."""
        result = _make_grounding_result(
            selected_code="C0011847",
            preferred_term="Diabetes",
        )
        omop_result = OmopLookupResult(
            omop_concept_id="201826",
            omop_concept_name="Diabetes",
            match_score=0.95,
        )

        returned = _reconcile_dual_grounding(result, omop_result)

        assert returned is result

    def test_agreement_is_case_insensitive(self) -> None:
        """Agreement check should be case-insensitive."""
        result = _make_grounding_result(
            selected_code="C0011847",
            preferred_term="METFORMIN",
        )
        omop_result = OmopLookupResult(
            omop_concept_id="1503297",
            omop_concept_name="metformin",
            match_score=0.95,
        )

        reconciled = _reconcile_dual_grounding(result, omop_result)

        assert reconciled.reconciliation_status == "agree"
