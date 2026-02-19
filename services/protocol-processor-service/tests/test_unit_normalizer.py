"""Tests for Phase 3: Unit and Value Normalizer.

Tests normalize_unit() and normalize_value() from the UCUM YAML lookup.
Covers canonical forms, aliases, case insensitivity, whitespace, None/empty,
and unrecognized inputs.
"""

from __future__ import annotations

from protocol_processor.tools.unit_normalizer import normalize_unit, normalize_value

# ===========================================================================
# normalize_unit() tests
# ===========================================================================


class TestNormalizeUnit:
    """Tests for normalize_unit() — UCUM code + OMOP unit_concept_id lookup."""

    def test_canonical_percent(self) -> None:
        """Canonical '%' resolves to OMOP 8554."""
        ucum, omop_id = normalize_unit("%")
        assert ucum == "%"
        assert omop_id == 8554

    def test_alias_percent(self) -> None:
        """Alias 'percent' resolves to '%' / 8554."""
        ucum, omop_id = normalize_unit("percent")
        assert ucum == "%"
        assert omop_id == 8554

    def test_canonical_mg_dl(self) -> None:
        """Canonical 'mg/dL' resolves to OMOP 8840."""
        ucum, omop_id = normalize_unit("mg/dL")
        assert ucum == "mg/dL"
        assert omop_id == 8840

    def test_alias_mg_dl_lowercase(self) -> None:
        """Alias 'mg/dl' resolves to mg/dL / 8840."""
        ucum, omop_id = normalize_unit("mg/dl")
        assert ucum == "mg/dL"
        assert omop_id == 8840

    def test_years_alias(self) -> None:
        """Alias 'years' resolves to 'a' / 9448."""
        ucum, omop_id = normalize_unit("years")
        assert ucum == "a"
        assert omop_id == 9448

    def test_yr_alias(self) -> None:
        """Alias 'yr' resolves to 'a' / 9448."""
        ucum, omop_id = normalize_unit("yr")
        assert ucum == "a"
        assert omop_id == 9448

    def test_ml_min(self) -> None:
        """'mL/min' resolves to OMOP 8795."""
        ucum, omop_id = normalize_unit("mL/min")
        assert ucum == "mL/min"
        assert omop_id == 8795

    def test_kg_m2(self) -> None:
        """'kg/m2' resolves to OMOP 9531."""
        ucum, omop_id = normalize_unit("kg/m2")
        assert ucum == "kg/m2"
        assert omop_id == 9531

    def test_mmhg_alias(self) -> None:
        """'mmHg' alias resolves to 'mm[Hg]' / 8876."""
        ucum, omop_id = normalize_unit("mmHg")
        assert ucum == "mm[Hg]"
        assert omop_id == 8876

    def test_mmol_l(self) -> None:
        """'mmol/L' resolves to OMOP 8753."""
        ucum, omop_id = normalize_unit("mmol/L")
        assert ucum == "mmol/L"
        assert omop_id == 8753

    def test_ml_min_173m2(self) -> None:
        """'mL/min/1.73m2' resolves to OMOP 720870."""
        ucum, omop_id = normalize_unit("mL/min/1.73m2")
        assert ucum == "mL/min/1.73m2"
        assert omop_id == 720870

    def test_cell_count_10_3_ul(self) -> None:
        """'10*3/uL' resolves to OMOP 8848."""
        ucum, omop_id = normalize_unit("10*3/uL")
        assert ucum == "10*3/uL"
        assert omop_id == 8848

    def test_cell_count_10_9_l(self) -> None:
        """'10*9/L' resolves to OMOP 9444."""
        ucum, omop_id = normalize_unit("10*9/L")
        assert ucum == "10*9/L"
        assert omop_id == 9444

    def test_case_insensitive(self) -> None:
        """Lookup should be case-insensitive."""
        ucum, omop_id = normalize_unit("MG/DL")
        assert ucum == "mg/dL"
        assert omop_id == 8840

    def test_whitespace_stripped(self) -> None:
        """Leading/trailing whitespace should be stripped."""
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
        assert normalize_unit("foobar_unit") == (None, None)


# ===========================================================================
# normalize_value() tests
# ===========================================================================


class TestNormalizeValue:
    """Tests for normalize_value() — categorical value normalization."""

    def test_positive(self) -> None:
        """'positive' resolves to 45884084."""
        text, omop_id = normalize_value("positive")
        assert text == "positive"
        assert omop_id == 45884084

    def test_negative(self) -> None:
        """'negative' resolves to 45878583."""
        text, omop_id = normalize_value("negative")
        assert text == "negative"
        assert omop_id == 45878583

    def test_normal(self) -> None:
        """'normal' resolves to 45884153."""
        text, omop_id = normalize_value("normal")
        assert text == "normal"
        assert omop_id == 45884153

    def test_abnormal(self) -> None:
        """'abnormal' resolves to 45878745."""
        text, omop_id = normalize_value("abnormal")
        assert text == "abnormal"
        assert omop_id == 45878745

    def test_present_maps_to_positive(self) -> None:
        """'present' maps to same concept as 'positive' (45884084)."""
        text, omop_id = normalize_value("present")
        assert text == "present"
        assert omop_id == 45884084

    def test_absent_maps_to_negative(self) -> None:
        """'absent' maps to same concept as 'negative' (45878583)."""
        text, omop_id = normalize_value("absent")
        assert text == "absent"
        assert omop_id == 45878583

    def test_case_insensitive(self) -> None:
        """Value lookup is case-insensitive."""
        text, omop_id = normalize_value("POSITIVE")
        assert text == "positive"
        assert omop_id == 45884084

    def test_whitespace_stripped(self) -> None:
        """Leading/trailing whitespace is stripped."""
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
        assert normalize_value("borderline") == (None, None)
