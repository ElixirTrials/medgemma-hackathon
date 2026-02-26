"""Tests for grounding fixes across the codebase.

Covers:
- FieldMappingItem Literal relation validation and legacy operator normalization
- _is_likely_acronym detection logic and allowlist
- TerminologyRouter smart acronym routing (UMLS injection)
- OMOP mapper domain filtering and primary domain scoring bonus
- entity_decompose.jinja2 compound-concept rules in the prompt template
- FieldMappingItem value_concept_id / value_concept_system optional fields
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pydantic
import pytest

from protocol_processor.tools.field_mapper import (
    FieldMappingItem,
    FieldMappingValue,
)
from protocol_processor.tools.omop_mapper import (
    PRIMARY_DOMAIN_BONUS,
    _score_candidates,
    _sync_lookup,
)
from protocol_processor.tools.terminology_router import (
    TerminologyRouter,
    _is_likely_acronym,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PROMPTS_DIR = Path(__file__).parent.parent / "src" / "protocol_processor" / "prompts"

_ENTITY_DECOMPOSE_TEMPLATE = _PROMPTS_DIR / "entity_decompose.jinja2"


def _make_candidate(
    match_text: str, domain_id: str = "Condition", **extra: object
) -> dict:
    """Build a minimal candidate dict suitable for _score_candidates."""
    base: dict = {
        "concept_id": "99999",
        "concept_name": match_text,
        "domain_id": domain_id,
        "vocabulary_id": "SNOMED",
        "match_text": match_text,
        "match_method": "concept_name",
    }
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# Test 1 — FieldMappingItem rejects invalid relation literal
# ---------------------------------------------------------------------------


class TestRelationLiteralRejectsInvalid:
    """FieldMappingItem.relation must be one of the accepted RelationOperator values."""

    def test_relation_literal_rejects_invalid(self) -> None:
        """'has_value' is not a valid RelationOperator — raises ValidationError."""
        with pytest.raises(pydantic.ValidationError):
            FieldMappingItem(
                entity="x",
                relation="has_value",
                value=FieldMappingValue(
                    type="standard",
                    value="1",
                    unit=None,
                    min=None,
                    max=None,
                    duration=None,
                ),
                unit=None,
                value_concept_id=None,
                value_concept_system=None,
            )


# ---------------------------------------------------------------------------
# Test 2 — @field_validator normalizes legacy operators before Literal check
# ---------------------------------------------------------------------------


class TestRelationNormalizerMapsLegacy:
    """The @field_validator on FieldMappingItem.relation normalizes legacy operators."""

    @pytest.mark.parametrize(
        ("legacy_op", "expected"),
        [
            ("has", "contains"),
            ("is", "="),
            ("==", "="),
            ("not", "not_contains"),
            ("range", "within"),
        ],
    )
    def test_normalizer_maps_legacy(self, legacy_op: str, expected: str) -> None:
        """Each legacy operator maps to the canonical frontend operator."""
        item = FieldMappingItem(
            entity="glucose",
            relation=legacy_op,  # type: ignore[arg-type]
            value=FieldMappingValue(
                type="standard",
                value="100",
                unit="mg/dL",
                min=None,
                max=None,
                duration=None,
            ),
            unit=None,
            value_concept_id=None,
            value_concept_system=None,
        )
        assert item.relation == expected


# ---------------------------------------------------------------------------
# Test 3 — _is_likely_acronym detection
# ---------------------------------------------------------------------------


class TestIsLikelyAcronym:
    """_is_likely_acronym returns True for short all-caps tokens not in allowlist."""

    @pytest.mark.parametrize("text", ["HTN", "MI", "CKD", "COPD", "DM", "AF"])
    def test_true_for_medical_acronyms(self, text: str) -> None:
        """Common medical acronyms should be detected as acronyms."""
        assert _is_likely_acronym(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "BMI",  # short all-caps — detected as acronym (redundant UMLS is OK)
            "AST",  # short all-caps — detected as acronym
        ],
    )
    def test_true_for_short_allcaps(self, text: str) -> None:
        """Short all-caps tokens are acronyms (no allowlist)."""
        assert _is_likely_acronym(text) is True

    @pytest.mark.parametrize(
        "text",
        [
            "age",  # not all-caps
            "metformin",  # not all-caps, longer
            "body mass index",  # has spaces
            "sex",  # not all-caps
        ],
    )
    def test_false_for_non_acronyms(self, text: str) -> None:
        """Non-acronyms (lowercase, spaces) return False."""
        assert _is_likely_acronym(text) is False


# ---------------------------------------------------------------------------
# Test 4 — Acronym routing adds UMLS to the API list
# ---------------------------------------------------------------------------


class TestAcronymRoutingAddsUmls:
    """TerminologyRouter.route_entity injects 'umls' when entity looks like acronym."""

    @pytest.fixture()
    def custom_router(self, tmp_path: Path) -> TerminologyRouter:
        """TerminologyRouter with a TestType rule that does NOT include umls."""
        import yaml

        config = {
            "routing_rules": {
                "TestType": ["icd10"],
            },
            "api_configs": {
                "icd10": {"source": "tooluniverse", "tool_name": "ICD10_search_codes"},
                "umls": {"source": "tooluniverse", "tool_name": "umls_search_concepts"},
            },
        }
        config_path = tmp_path / "routing.yaml"
        config_path.write_text(yaml.dump(config))
        return TerminologyRouter(config_path=config_path)

    def test_get_apis_for_entity_does_not_include_umls(
        self, custom_router: TerminologyRouter
    ) -> None:
        """Baseline: TestType routing only has icd10, NOT umls."""
        apis = custom_router.get_apis_for_entity("TestType")
        assert apis == ["icd10"]
        assert "umls" not in apis

    def test_is_likely_acronym_htn_is_true(self) -> None:
        """HTN is recognized as an acronym (prerequisite for routing logic)."""
        assert _is_likely_acronym("HTN") is True

    async def test_route_entity_calls_query_tooluniverse_with_umls(
        self, custom_router: TerminologyRouter
    ) -> None:
        """route_entity for an acronym calls _query_tooluniverse with 'umls'."""
        with patch.object(
            custom_router,
            "_query_tooluniverse",
            return_value=[],
        ) as mock_query:
            await custom_router.route_entity("HTN", "TestType")

        # Collect all api_name args passed to _query_tooluniverse
        called_apis = [call.args[0] for call in mock_query.call_args_list]
        assert "umls" in called_apis, (
            f"Expected 'umls' in called APIs for acronym 'HTN', got: {called_apis}"
        )
        assert "icd10" in called_apis


# ---------------------------------------------------------------------------
# Test 5 — OMOP acronym lookup drops the domain filter for synonyms
# ---------------------------------------------------------------------------


class TestOmopAcronymDropsDomainFilter:
    """_sync_lookup passes skip_domain_filter=True when is_acronym=True."""

    @patch("protocol_processor.tools.omop_mapper._get_omop_engine")
    @patch("protocol_processor.tools.omop_mapper._query_synonym_table")
    @patch("protocol_processor.tools.omop_mapper._query_concept_table")
    def test_acronym_skips_domain_filter_in_synonym_query(
        self,
        mock_concept: MagicMock,
        mock_synonym: MagicMock,
        mock_engine: MagicMock,
    ) -> None:
        """When is_acronym=True, synonym query receives skip_domain_filter=True."""
        mock_engine.return_value = MagicMock()
        mock_concept.return_value = []
        mock_synonym.return_value = []

        _sync_lookup("HTN", ["Condition", "Observation"], is_acronym=True)

        mock_synonym.assert_called_once()
        _, kwargs = mock_synonym.call_args
        assert kwargs.get("skip_domain_filter") is True, (
            f"Expected skip_domain_filter=True, got: {kwargs}"
        )


# ---------------------------------------------------------------------------
# Test 6 — OMOP multi-domain query passes all domain_ids
# ---------------------------------------------------------------------------


class TestOmopMultiDomainQuery:
    """_sync_lookup calls _query_concept_table with the full domain_ids list."""

    @patch("protocol_processor.tools.omop_mapper._get_omop_engine")
    @patch("protocol_processor.tools.omop_mapper._query_synonym_table")
    @patch("protocol_processor.tools.omop_mapper._query_concept_table")
    def test_multi_domain_query_passes_all_domains(
        self,
        mock_concept: MagicMock,
        mock_synonym: MagicMock,
        mock_engine: MagicMock,
    ) -> None:
        """_query_concept_table receives all provided domain_ids."""
        mock_engine.return_value = MagicMock()
        mock_concept.return_value = []
        mock_synonym.return_value = []

        _sync_lookup("pregnancy", ["Condition", "Observation"])

        mock_concept.assert_called_once()
        _, _, domain_ids_arg = mock_concept.call_args.args
        assert domain_ids_arg == ["Condition", "Observation"], (
            f"Expected ['Condition', 'Observation'], got: {domain_ids_arg}"
        )


# ---------------------------------------------------------------------------
# Test 7 — Primary domain candidate gets PRIMARY_DOMAIN_BONUS
# ---------------------------------------------------------------------------


class TestOmopPrimaryDomainScoredHigher:
    """Candidates in the primary domain receive PRIMARY_DOMAIN_BONUS after scoring."""

    @patch("protocol_processor.tools.omop_mapper._get_omop_engine")
    @patch("protocol_processor.tools.omop_mapper._query_synonym_table")
    @patch("protocol_processor.tools.omop_mapper._query_concept_table")
    def test_primary_domain_candidate_ranked_higher(
        self,
        mock_concept: MagicMock,
        mock_synonym: MagicMock,
        mock_engine: MagicMock,
    ) -> None:
        """Condition candidate (primary domain) should rank above Observation."""
        mock_engine.return_value = MagicMock()
        mock_synonym.return_value = []

        # Both candidates have the same match_text; domain differentiates them.
        condition_candidate = _make_candidate(
            "diabetes mellitus",
            domain_id="Condition",
            concept_id="111",
        )
        observation_candidate = _make_candidate(
            "diabetes mellitus",
            domain_id="Observation",
            concept_id="222",
        )
        mock_concept.return_value = [condition_candidate, observation_candidate]

        result = _sync_lookup("diabetes mellitus", ["Condition", "Observation"])

        # Primary domain is "Condition" — winning concept_id should be from Condition
        assert result.omop_concept_id == "111", (
            f"Expected Condition concept '111' to win, got: {result.omop_concept_id}"
        )

    def test_primary_domain_bonus_constant_is_correct(self) -> None:
        """PRIMARY_DOMAIN_BONUS must equal 0.05."""
        assert PRIMARY_DOMAIN_BONUS == pytest.approx(0.05)

    def test_score_candidates_does_not_apply_domain_bonus(self) -> None:
        """_score_candidates does NOT apply the domain bonus (done in _sync_lookup)."""
        candidates = [
            _make_candidate("diabetes mellitus", domain_id="Condition"),
            _make_candidate("diabetes mellitus", domain_id="Observation"),
        ]
        scored = _score_candidates("diabetes mellitus", candidates)
        # Without the domain bonus, both should have identical scores
        assert scored[0]["score"] == pytest.approx(scored[1]["score"])


# ---------------------------------------------------------------------------
# Test 8 — entity_decompose.jinja2 contains compound-concept anti-decompose rules
# ---------------------------------------------------------------------------


class TestDecomposeKeepsCompoundConcepts:
    """entity_decompose.jinja2 must contain anti-decomposition guidance."""

    def test_template_contains_do_not_separate(self) -> None:
        """Template instructs the model NOT to separate anatomical modifiers."""
        content = _ENTITY_DECOMPOSE_TEMPLATE.read_text()
        assert "Do NOT separate anatomical modifiers" in content

    def test_template_contains_tricompartmental_example(self) -> None:
        """Template includes 'tricompartmental knee replacement' as an example."""
        content = _ENTITY_DECOMPOSE_TEMPLATE.read_text()
        assert "tricompartmental knee replacement" in content

    def test_template_contains_non_small_cell_lung_cancer(self) -> None:
        """Template includes 'non-small cell lung cancer' as a compound example."""
        content = _ENTITY_DECOMPOSE_TEMPLATE.read_text()
        assert "non-small cell lung cancer" in content


# ---------------------------------------------------------------------------
# Test 9 — entity_decompose.jinja2 contains comorbidity split rules
# ---------------------------------------------------------------------------


class TestDecomposeSplitsComorbidities:
    """entity_decompose.jinja2 must contain guidance to split distinct comorbidities."""

    def test_template_contains_do_separate(self) -> None:
        """Template instructs the model to DO separate distinct comorbidities."""
        content = _ENTITY_DECOMPOSE_TEMPLATE.read_text()
        assert "DO separate distinct comorbidities" in content

    def test_template_contains_type2_diabetes_example(self) -> None:
        """Template includes 'Type 2 diabetes' in the comorbidity split example."""
        content = _ENTITY_DECOMPOSE_TEMPLATE.read_text()
        assert "Type 2 diabetes" in content

    def test_template_contains_nephropathy_example(self) -> None:
        """Template includes 'nephropathy' in the comorbidity split example."""
        content = _ENTITY_DECOMPOSE_TEMPLATE.read_text()
        assert "nephropathy" in content


# ---------------------------------------------------------------------------
# Test 10 — FieldMappingItem accepts value_concept_id and value_concept_system
# ---------------------------------------------------------------------------


class TestValueConceptFieldsOnFieldMappingItem:
    """FieldMappingItem supports optional value_concept_id and value_concept_system."""

    def test_value_concept_id_accepted(self) -> None:
        """value_concept_id is accepted as an optional string field."""
        item = FieldMappingItem(
            entity="severity",
            relation="=",
            value=FieldMappingValue(
                type="standard",
                value="Severe",
                unit=None,
                min=None,
                max=None,
                duration=None,
            ),
            unit=None,
            value_concept_id="4298817",
            value_concept_system=None,
        )
        assert item.value_concept_id == "4298817"

    def test_value_concept_system_accepted(self) -> None:
        """value_concept_system is accepted as an optional string field."""
        item = FieldMappingItem(
            entity="severity",
            relation="=",
            value=FieldMappingValue(
                type="standard",
                value="Severe",
                unit=None,
                min=None,
                max=None,
                duration=None,
            ),
            unit=None,
            value_concept_id=None,
            value_concept_system="SNOMED",
        )
        assert item.value_concept_system == "SNOMED"

    def test_both_value_concept_fields_accepted_together(self) -> None:
        """Both value_concept_id and value_concept_system can be set simultaneously."""
        item = FieldMappingItem(
            entity="severity",
            relation="=",
            value=FieldMappingValue(
                type="standard",
                value="Stage IV",
                unit=None,
                min=None,
                max=None,
                duration=None,
            ),
            unit=None,
            value_concept_id="4298817",
            value_concept_system="OMOP",
        )
        assert item.value_concept_id == "4298817"
        assert item.value_concept_system == "OMOP"

    def test_value_concept_fields_default_to_none(self) -> None:
        """value_concept_id and value_concept_system default to None when omitted."""
        item = FieldMappingItem(
            entity="glucose",
            relation="<",
            value=FieldMappingValue(
                type="standard",
                value="126",
                unit="mg/dL",
                min=None,
                max=None,
                duration=None,
            ),
            unit=None,
            value_concept_id=None,
            value_concept_system=None,
        )
        assert item.value_concept_id is None
        assert item.value_concept_system is None


# ---------------------------------------------------------------------------
# Test 11 — _lookup_ucum_unit DB query
# ---------------------------------------------------------------------------


class TestLookupUcumUnit:
    """_lookup_ucum_unit queries UCUM vocabulary for unit codes."""

    def test_exact_concept_name_match(self) -> None:
        """Exact concept_name match returns (ucum_code, concept_id)."""
        from protocol_processor.tools.omop_mapper import _lookup_ucum_unit

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        # First query (exact concept_name) returns a row
        mock_conn.execute.return_value.fetchone.return_value = (8840, "mg/dL")

        result = _lookup_ucum_unit(mock_engine, "mg/dL")
        assert result == ("mg/dL", 8840)

    def test_no_match_returns_none(self) -> None:
        """No match returns (None, None)."""
        from protocol_processor.tools.omop_mapper import _lookup_ucum_unit

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.fetchone.return_value = None

        result = _lookup_ucum_unit(mock_engine, "unknown_unit")
        assert result == (None, None)

    def test_empty_string_returns_none(self) -> None:
        """Empty string returns (None, None) without querying DB."""
        from protocol_processor.tools.omop_mapper import _lookup_ucum_unit

        mock_engine = MagicMock()
        result = _lookup_ucum_unit(mock_engine, "  ")
        assert result == (None, None)


# ---------------------------------------------------------------------------
# Test 12 — _lookup_value_concept DB query
# ---------------------------------------------------------------------------


class TestLookupValueConcept:
    """_lookup_value_concept queries Meas Value domain for qualifiers."""

    def test_exact_match_returns_normalized(self) -> None:
        """Exact match returns (lowercased_name, concept_id)."""
        from protocol_processor.tools.omop_mapper import _lookup_value_concept

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.fetchone.return_value = (45884084, "Positive")

        result = _lookup_value_concept(mock_engine, "positive")
        assert result == ("positive", 45884084)

    def test_empty_string_returns_none(self) -> None:
        """Empty string returns (None, None) without querying DB."""
        from protocol_processor.tools.omop_mapper import _lookup_value_concept

        mock_engine = MagicMock()
        result = _lookup_value_concept(mock_engine, "  ")
        assert result == (None, None)


# ---------------------------------------------------------------------------
# Test 13 — _lookup_ordinal_concept DB query
# ---------------------------------------------------------------------------


class TestLookupOrdinalConcept:
    """_lookup_ordinal_concept queries for scale+grade combos."""

    def test_match_returns_concept_id(self) -> None:
        """Matching pattern returns concept_id."""
        from protocol_processor.tools.omop_mapper import _lookup_ordinal_concept

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        # First concept query returns a row
        mock_conn.execute.return_value.fetchone.return_value = (4174241,)

        result = _lookup_ordinal_concept(mock_engine, "ecog", "2")
        assert result == 4174241

    def test_no_match_returns_none(self) -> None:
        """No match returns None."""
        from protocol_processor.tools.omop_mapper import _lookup_ordinal_concept

        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.fetchone.return_value = None

        result = _lookup_ordinal_concept(mock_engine, "ecog", "99")
        assert result is None
