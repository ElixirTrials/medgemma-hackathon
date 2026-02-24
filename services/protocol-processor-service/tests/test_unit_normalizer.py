"""Tests for Unit and Value Normalizer (DB-backed).

Tests normalize_unit() and normalize_value() via mocked OMOP DB lookups.
Covers canonical forms, aliases, case insensitivity, whitespace, None/empty,
and unrecognized inputs.

Tests for normalize_ordinal_value() and propose_ordinal_mappings().
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from protocol_processor.tools.unit_normalizer import (
    _cached_ucum_lookup,
    _cached_value_lookup,
    normalize_ordinal_value,
    normalize_unit,
    normalize_value,
    propose_ordinal_mappings,
)

# ---------------------------------------------------------------------------
# Helpers — mock DB responses
# ---------------------------------------------------------------------------

# Simulated UCUM DB results: lowercased key -> (ucum_code, omop_concept_id)
_MOCK_UCUM: dict[str, tuple[str, int]] = {
    "%": ("%", 8554),
    "percent": ("%", 8554),
    "pct": ("%", 8554),
    "mg/dl": ("mg/dL", 8840),
    "mg/dL": ("mg/dL", 8840),
    "a": ("a", 9448),
    "years": ("a", 9448),
    "year": ("a", 9448),
    "yr": ("a", 9448),
    "yrs": ("a", 9448),
    "ml/min": ("mL/min", 8795),
    "mL/min": ("mL/min", 8795),
    "kg/m2": ("kg/m2", 9531),
    "mm[hg]": ("mm[Hg]", 8876),
    "mmhg": ("mm[Hg]", 8876),
    "mmol/l": ("mmol/L", 8753),
    "mmol/L": ("mmol/L", 8753),
    "ml/min/1.73m2": ("mL/min/1.73m2", 720870),
    "mL/min/1.73m2": ("mL/min/1.73m2", 720870),
    "10*3/ul": ("10*3/uL", 8848),
    "10*3/uL": ("10*3/uL", 8848),
    "10*9/l": ("10*9/L", 9444),
    "10*9/L": ("10*9/L", 9444),
    "{score}": ("{score}", 8527),
    "score": ("{score}", 8527),
    "points": ("{score}", 8527),
}

_MOCK_VALUES: dict[str, tuple[str, int]] = {
    "positive": ("positive", 45884084),
    "negative": ("negative", 45878583),
    "normal": ("normal", 45884153),
    "abnormal": ("abnormal", 45878745),
    "present": ("present", 45884084),
    "absent": ("absent", 45878583),
}


def _mock_lookup_ucum_unit(
    _engine: object, unit_text: str
) -> tuple[str | None, int | None]:
    key = unit_text.strip().lower()
    return _MOCK_UCUM.get(key, (None, None))


def _mock_lookup_value_concept(
    _engine: object, value_text: str
) -> tuple[str | None, int | None]:
    key = value_text.strip().lower()
    return _MOCK_VALUES.get(key, (None, None))


def _mock_lookup_ordinal_concept(
    _engine: object, scale_name: str, grade: str
) -> int | None:
    # Return None — ordinal DB lookup not populated in mock
    return None


def _patch_db():
    """Context manager that patches all DB access for unit_normalizer tests."""
    engine_mock = MagicMock()

    return (
        patch(
            "protocol_processor.tools.omop_mapper._get_omop_engine",
            return_value=engine_mock,
        ),
        patch(
            "protocol_processor.tools.omop_mapper._lookup_ucum_unit",
            side_effect=_mock_lookup_ucum_unit,
        ),
        patch(
            "protocol_processor.tools.omop_mapper._lookup_value_concept",
            side_effect=_mock_lookup_value_concept,
        ),
        patch(
            "protocol_processor.tools.omop_mapper._lookup_ordinal_concept",
            side_effect=_mock_lookup_ordinal_concept,
        ),
    )


def setup_function() -> None:
    """Clear LRU caches before each test function."""
    _cached_ucum_lookup.cache_clear()
    _cached_value_lookup.cache_clear()


# ===========================================================================
# normalize_unit() tests
# ===========================================================================


class TestNormalizeUnit:
    """Tests for normalize_unit() — UCUM code + OMOP unit_concept_id lookup."""

    def setup_method(self) -> None:
        _cached_ucum_lookup.cache_clear()
        _cached_value_lookup.cache_clear()

    def test_canonical_percent(self) -> None:
        """Canonical '%' resolves to OMOP 8554."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            ucum, omop_id = normalize_unit("%")
            assert ucum == "%"
            assert omop_id == 8554

    def test_alias_percent(self) -> None:
        """Alias 'percent' resolves to '%' / 8554."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            ucum, omop_id = normalize_unit("percent")
            assert ucum == "%"
            assert omop_id == 8554

    def test_canonical_mg_dl(self) -> None:
        """Canonical 'mg/dL' resolves to OMOP 8840."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            ucum, omop_id = normalize_unit("mg/dL")
            assert ucum == "mg/dL"
            assert omop_id == 8840

    def test_alias_mg_dl_lowercase(self) -> None:
        """Alias 'mg/dl' resolves to mg/dL / 8840."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            ucum, omop_id = normalize_unit("mg/dl")
            assert ucum == "mg/dL"
            assert omop_id == 8840

    def test_years_alias(self) -> None:
        """Alias 'years' resolves to 'a' / 9448."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            ucum, omop_id = normalize_unit("years")
            assert ucum == "a"
            assert omop_id == 9448

    def test_yr_alias(self) -> None:
        """Alias 'yr' resolves to 'a' / 9448."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            ucum, omop_id = normalize_unit("yr")
            assert ucum == "a"
            assert omop_id == 9448

    def test_ml_min(self) -> None:
        """'mL/min' resolves to OMOP 8795."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            ucum, omop_id = normalize_unit("mL/min")
            assert ucum == "mL/min"
            assert omop_id == 8795

    def test_kg_m2(self) -> None:
        """'kg/m2' resolves to OMOP 9531."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            ucum, omop_id = normalize_unit("kg/m2")
            assert ucum == "kg/m2"
            assert omop_id == 9531

    def test_mmhg_alias(self) -> None:
        """'mmHg' alias resolves to 'mm[Hg]' / 8876."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            ucum, omop_id = normalize_unit("mmHg")
            assert ucum == "mm[Hg]"
            assert omop_id == 8876

    def test_mmol_l(self) -> None:
        """'mmol/L' resolves to OMOP 8753."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            ucum, omop_id = normalize_unit("mmol/L")
            assert ucum == "mmol/L"
            assert omop_id == 8753

    def test_ml_min_173m2(self) -> None:
        """'mL/min/1.73m2' resolves to OMOP 720870."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            ucum, omop_id = normalize_unit("mL/min/1.73m2")
            assert ucum == "mL/min/1.73m2"
            assert omop_id == 720870

    def test_cell_count_10_3_ul(self) -> None:
        """'10*3/uL' resolves to OMOP 8848."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            ucum, omop_id = normalize_unit("10*3/uL")
            assert ucum == "10*3/uL"
            assert omop_id == 8848

    def test_cell_count_10_9_l(self) -> None:
        """'10*9/L' resolves to OMOP 9444."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            ucum, omop_id = normalize_unit("10*9/L")
            assert ucum == "10*9/L"
            assert omop_id == 9444

    def test_case_insensitive(self) -> None:
        """Lookup should be case-insensitive."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            ucum, omop_id = normalize_unit("MG/DL")
            assert ucum == "mg/dL"
            assert omop_id == 8840

    def test_whitespace_stripped(self) -> None:
        """Leading/trailing whitespace should be stripped."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            ucum, omop_id = normalize_unit("  %  ")
            assert ucum == "%"
            assert omop_id == 8554

    def test_none_input(self) -> None:
        """None input returns (None, None)."""
        assert normalize_unit(None) == (None, None)

    def test_empty_string(self) -> None:
        """Empty string returns (None, None)."""
        assert normalize_unit("") == (None, None)

    def test_whitespace_only(self) -> None:
        """Whitespace-only string returns (None, None)."""
        assert normalize_unit("   ") == (None, None)

    def test_unrecognized_unit(self) -> None:
        """Unrecognized unit returns (None, None)."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            assert normalize_unit("foobar_unit") == (None, None)


# ===========================================================================
# normalize_value() tests
# ===========================================================================


class TestNormalizeValue:
    """Tests for normalize_value() — categorical value normalization."""

    def setup_method(self) -> None:
        _cached_ucum_lookup.cache_clear()
        _cached_value_lookup.cache_clear()

    def test_positive(self) -> None:
        """'positive' resolves to 45884084."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            text, omop_id = normalize_value("positive")
            assert text == "positive"
            assert omop_id == 45884084

    def test_negative(self) -> None:
        """'negative' resolves to 45878583."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            text, omop_id = normalize_value("negative")
            assert text == "negative"
            assert omop_id == 45878583

    def test_normal(self) -> None:
        """'normal' resolves to 45884153."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            text, omop_id = normalize_value("normal")
            assert text == "normal"
            assert omop_id == 45884153

    def test_abnormal(self) -> None:
        """'abnormal' resolves to 45878745."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            text, omop_id = normalize_value("abnormal")
            assert text == "abnormal"
            assert omop_id == 45878745

    def test_present_maps_to_positive(self) -> None:
        """'present' maps to same concept as 'positive' (45884084)."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            text, omop_id = normalize_value("present")
            assert text == "present"
            assert omop_id == 45884084

    def test_absent_maps_to_negative(self) -> None:
        """'absent' maps to same concept as 'negative' (45878583)."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            text, omop_id = normalize_value("absent")
            assert text == "absent"
            assert omop_id == 45878583

    def test_case_insensitive(self) -> None:
        """Value lookup is case-insensitive."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            text, omop_id = normalize_value("POSITIVE")
            assert text == "positive"
            assert omop_id == 45884084

    def test_whitespace_stripped(self) -> None:
        """Leading/trailing whitespace is stripped."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            text, omop_id = normalize_value("  negative  ")
            assert text == "negative"
            assert omop_id == 45878583

    def test_none_input(self) -> None:
        """None input returns (None, None)."""
        assert normalize_value(None) == (None, None)

    def test_empty_string(self) -> None:
        """Empty string returns (None, None)."""
        assert normalize_value("") == (None, None)

    def test_unrecognized_value(self) -> None:
        """Unrecognized value returns (None, None)."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            assert normalize_value("borderline") == (None, None)


# ===========================================================================
# normalize_ordinal_value() tests
# ===========================================================================


class TestNormalizeOrdinalValue:
    """Tests for normalize_ordinal_value() — ordinal scale normalization."""

    def setup_method(self) -> None:
        _cached_ucum_lookup.cache_clear()
        _cached_value_lookup.cache_clear()

    # --- Entity matching ---

    def test_exact_alias_ecog(self) -> None:
        """Exact alias 'ECOG' matches the ecog scale."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            result = normalize_ordinal_value("2", "ECOG")
            assert result is not None
            _, unit_cid = result
            assert unit_cid == 8527

    def test_full_name_ecog(self) -> None:
        """Full name 'ECOG performance status' matches."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            result = normalize_ordinal_value("1", "ECOG performance status")
            assert result is not None
            _, unit_cid = result
            assert unit_cid == 8527

    def test_case_insensitive_ecog(self) -> None:
        """Case-insensitive matching: 'ecog' matches."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            result = normalize_ordinal_value("0", "ecog")
            assert result is not None
            _, unit_cid = result
            assert unit_cid == 8527

    def test_substring_ecog_ps(self) -> None:
        """Substring match: 'ECOG PS' is an alias."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            result = normalize_ordinal_value("3", "ECOG PS")
            assert result is not None
            _, unit_cid = result
            assert unit_cid == 8527

    def test_substring_entity_contains_alias(self) -> None:
        """Entity text containing an alias: 'Patient ECOG status'."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            result = normalize_ordinal_value("1", "Patient ECOG status")
            assert result is not None
            _, unit_cid = result
            assert unit_cid == 8527

    # --- ECOG grade recognition ---

    def test_ecog_grade_0(self) -> None:
        """ECOG grade 0 returns unit_concept_id=8527."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            result = normalize_ordinal_value("0", "ECOG")
            assert result is not None
            _, unit_cid = result
            assert unit_cid == 8527

    def test_ecog_grade_5(self) -> None:
        """ECOG grade 5 returns unit_concept_id=8527."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            result = normalize_ordinal_value("5", "ECOG")
            assert result is not None
            _, unit_cid = result
            assert unit_cid == 8527

    def test_ecog_all_grades_recognized(self) -> None:
        """All 6 ECOG grades (0-5) are recognized."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            for grade in range(6):
                result = normalize_ordinal_value(str(grade), "ECOG")
                assert result is not None, f"ECOG grade {grade} not recognized"
                _, unit_cid = result
                assert unit_cid == 8527

    # --- Value parsing edge cases ---

    def test_float_normalization(self) -> None:
        """'2.0' normalizes to '2' for grade lookup."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            result = normalize_ordinal_value("2.0", "ECOG")
            assert result is not None
            _, unit_cid = result
            assert unit_cid == 8527

    def test_grade_prefix_strip(self) -> None:
        """'Grade 2' strips prefix and matches grade 2."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            result = normalize_ordinal_value("Grade 2", "ECOG")
            assert result is not None
            _, unit_cid = result
            assert unit_cid == 8527

    def test_class_prefix_strip(self) -> None:
        """'Class 3' strips prefix for NYHA."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            result = normalize_ordinal_value("Class 3", "NYHA")
            assert result is not None
            _, unit_cid = result
            assert unit_cid == 8527

    def test_unknown_grade(self) -> None:
        """Unknown ECOG grade 7 returns (None, 8527)."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            result = normalize_ordinal_value("7", "ECOG")
            assert result is not None
            value_cid, unit_cid = result
            assert value_cid is None
            assert unit_cid == 8527

    # --- Non-ordinal entities ---

    def test_non_ordinal_entity(self) -> None:
        """Non-ordinal entity 'HbA1c' returns None (not a tuple)."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            result = normalize_ordinal_value("6.5", "HbA1c")
            assert result is None

    def test_none_entity(self) -> None:
        """None entity returns None."""
        result = normalize_ordinal_value("2", None)
        assert result is None

    def test_empty_entity(self) -> None:
        """Empty entity returns None."""
        result = normalize_ordinal_value("2", "")
        assert result is None

    # --- Karnofsky ---

    def test_karnofsky_match(self) -> None:
        """Karnofsky scale recognized with unit_concept_id=8527."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            result = normalize_ordinal_value("80", "KPS")
            assert result is not None
            _, unit_cid = result
            assert unit_cid == 8527

    # --- {score} unit via normalize_unit ---

    def test_score_unit(self) -> None:
        """'score' alias resolves to {score} / 8527."""
        p1, p2, p3, p4 = _patch_db()
        with p1, p2, p3, p4:
            ucum, omop_id = normalize_unit("score")
            assert ucum == "{score}"
            assert omop_id == 8527

    # --- propose_ordinal_mappings ---

    def test_propose_returns_empty(self) -> None:
        """propose_ordinal_mappings() returns empty list (DB-driven now)."""
        missing = propose_ordinal_mappings()
        assert isinstance(missing, list)
        assert len(missing) == 0
