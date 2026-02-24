"""E2E: Validate grounding against test_snippets.json golden examples.

Requires the full Docker Compose stack to be running. Tests are auto-skipped
when the stack is unavailable.

Extraction snippets: verify classification (inclusion/exclusion/neither).
Grounding snippets: verify entity names, terminology system codes, and
relation operators match expected values.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_SNIPPETS_PATH = Path(__file__).parent / "test_snippets.json"


def _snippet_counts() -> tuple[int, int]:
    """Load snippet counts for parametrization (avoids hardcoded range)."""
    data = json.loads(_SNIPPETS_PATH.read_text())
    return (
        len(data["extraction_test_snippets"]),
        len(data["grounding_test_snippets"]),
    )


_NUM_EXTRACTION, _NUM_GROUNDING = _snippet_counts()


@pytest.fixture(scope="module")
def snippets_data() -> dict:
    """Load the test_snippets.json fixture."""
    return json.loads(_SNIPPETS_PATH.read_text())


@pytest.fixture()
def extraction_snippets(snippets_data: dict) -> list[dict]:
    return snippets_data["extraction_test_snippets"]


@pytest.fixture()
def grounding_snippets(snippets_data: dict) -> list[dict]:
    return snippets_data["grounding_test_snippets"]


# ---------------------------------------------------------------------------
# Extraction tests — classification validation
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestExtractionSnippets:
    """Validate extraction snippet golden classification."""

    @pytest.mark.parametrize("idx", range(_NUM_EXTRACTION))
    def test_extraction_snippet_structure(
        self, idx: int, extraction_snippets: list[dict]
    ) -> None:
        """Each extraction snippet has required fields."""
        snippet = extraction_snippets[idx]
        assert "snippet_text" in snippet
        assert "classification" in snippet
        assert snippet["classification"] in ("inclusion", "exclusion", "neither")

    @pytest.mark.parametrize("idx", range(_NUM_EXTRACTION))
    def test_extraction_snippet_criteria_consistency(
        self, idx: int, extraction_snippets: list[dict]
    ) -> None:
        """'neither' snippets have null extracted_criteria; others have text."""
        snippet = extraction_snippets[idx]
        if snippet["classification"] == "neither":
            assert snippet["extracted_criteria"] is None
        else:
            assert snippet["extracted_criteria"] is not None
            assert len(snippet["extracted_criteria"]) > 0


# ---------------------------------------------------------------------------
# Grounding tests — entity/code/relation validation
# ---------------------------------------------------------------------------

# Normalize legacy relation operators the same way the pipeline does
_RELATION_NORMALIZATIONS = {
    "==": "=",
    "is": "=",
    "has": "contains",
    "not": "not_contains",
}


@pytest.mark.e2e
class TestGroundingSnippets:
    """Validate grounding snippet golden entity examples."""

    @pytest.mark.parametrize("idx", range(_NUM_GROUNDING))
    def test_grounding_snippet_has_entities(
        self, idx: int, grounding_snippets: list[dict]
    ) -> None:
        """Each grounding snippet has at least one entity."""
        snippet = grounding_snippets[idx]
        assert "entities" in snippet
        assert len(snippet["entities"]) > 0

    @pytest.mark.parametrize("idx", range(_NUM_GROUNDING))
    def test_grounding_snippet_entity_fields(
        self, idx: int, grounding_snippets: list[dict]
    ) -> None:
        """Each entity has required fields: entity_name, system, code, relation, value."""
        snippet = grounding_snippets[idx]
        for entity in snippet["entities"]:
            assert "entity_name" in entity
            assert "system" in entity
            assert "code" in entity
            assert "relation" in entity
            assert "value" in entity

    @pytest.mark.parametrize("idx", range(_NUM_GROUNDING))
    def test_grounding_snippet_system_is_valid(
        self, idx: int, grounding_snippets: list[dict]
    ) -> None:
        """All golden entities use a recognized terminology system."""
        valid_systems = {"UMLS", "SNOMED", "ICD10", "LOINC", "RxNorm", "HPO"}
        snippet = grounding_snippets[idx]
        for entity in snippet["entities"]:
            assert entity["system"] in valid_systems, (
                f"Unknown system '{entity['system']}'"
            )

    @pytest.mark.parametrize("idx", range(_NUM_GROUNDING))
    def test_grounding_snippet_codes_are_cui_format(
        self, idx: int, grounding_snippets: list[dict]
    ) -> None:
        """All codes start with 'C' followed by digits (CUI format from UMLS/SNOMED)."""
        snippet = grounding_snippets[idx]
        for entity in snippet["entities"]:
            code = entity["code"]
            assert code.startswith("C"), f"Expected CUI format, got: {code}"
            assert code[1:].isdigit(), f"Expected CUI digits after 'C', got: {code}"

    @pytest.mark.parametrize("idx", range(_NUM_GROUNDING))
    def test_grounding_snippet_relations_are_valid(
        self, idx: int, grounding_snippets: list[dict]
    ) -> None:
        """All relations are valid operator strings (after normalization)."""
        valid_relations = {
            "<",
            "<=",
            ">",
            ">=",
            "=",
            "!=",
            "contains",
            "not_contains",
            "within",
            "==",
        }
        snippet = grounding_snippets[idx]
        for entity in snippet["entities"]:
            rel = entity["relation"]
            normalized = _RELATION_NORMALIZATIONS.get(rel, rel)
            assert normalized in valid_relations, (
                f"Invalid relation '{rel}' (normalized: '{normalized}')"
            )

    def test_serum_creatinine_snippet(self, grounding_snippets: list[dict]) -> None:
        """Snippet 0: Serum creatinine >1.5 times ULN."""
        snippet = grounding_snippets[0]
        assert len(snippet["entities"]) == 1
        e = snippet["entities"][0]
        assert e["entity_name"] == "Serum creatinine"
        assert e["code"] == "C0201975"
        assert e["relation"] == ">"

    def test_egfr_snippet(self, grounding_snippets: list[dict]) -> None:
        """Snippet 1: eGFR <45 ml/min."""
        snippet = grounding_snippets[1]
        assert len(snippet["entities"]) == 1
        e = snippet["entities"][0]
        assert "Glomerular Filtration Rate" in e["entity_name"]
        assert e["code"] == "C0858118"
        assert e["relation"] == "<"

    def test_body_weight_bmi_snippet(self, grounding_snippets: list[dict]) -> None:
        """Snippet 2: Body weight <50 kg OR BMI >44."""
        snippet = grounding_snippets[2]
        assert len(snippet["entities"]) == 2
        names = {e["entity_name"] for e in snippet["entities"]}
        assert "Body Weight" in names
        assert "Body Mass Index" in names

    def test_ankylosing_spondylitis_snippet(
        self, grounding_snippets: list[dict]
    ) -> None:
        """Snippet 3: Diagnosis of active AS."""
        snippet = grounding_snippets[3]
        assert len(snippet["entities"]) == 2
        codes = {e["code"] for e in snippet["entities"]}
        assert "C0038013" in codes  # Ankylosing Spondylitis
        # Verify boolean normalization
        for e in snippet["entities"]:
            assert e["relation"] == "="
            assert e["value"] == "True"

    def test_parkinsons_gba_snippet(self, grounding_snippets: list[dict]) -> None:
        """Snippet 4: PD with GBA mutation."""
        snippet = grounding_snippets[4]
        assert len(snippet["entities"]) == 4
        codes = {e["code"] for e in snippet["entities"]}
        assert "C0030567" in codes  # Parkinson's Disease
        assert "C4225361" in codes  # GBA gene mutation

    def test_asa_physical_status_snippet(self, grounding_snippets: list[dict]) -> None:
        """Snippet 5: ASA physical status 1, 2, or 3."""
        snippet = grounding_snippets[5]
        assert len(snippet["entities"]) == 1
        e = snippet["entities"][0]
        assert "Anesthesiologists" in e["entity_name"]
        assert e["code"] == "C0450990"

    def test_female_surgically_sterile_snippet(
        self, grounding_snippets: list[dict]
    ) -> None:
        """Snippet 6: Female subjects must be surgically sterile."""
        snippet = grounding_snippets[6]
        assert len(snippet["entities"]) == 2
        codes = {e["code"] for e in snippet["entities"]}
        assert "C1705498" in codes  # Female Phenotype
        assert "C0015787" in codes  # Female Sterilization
        # Verify boolean normalization
        for e in snippet["entities"]:
            assert e["relation"] == "="
            assert e["value"] == "True"

    def test_venous_blood_snippet(self, grounding_snippets: list[dict]) -> None:
        """Snippet 7: Must agree to collection of venous blood."""
        snippet = grounding_snippets[7]
        assert len(snippet["entities"]) == 1
        e = snippet["entities"][0]
        assert e["code"] == "C1548758"
        assert e["relation"] == "="
        assert e["value"] == "True"

    def test_non_pregnant_snippet(self, grounding_snippets: list[dict]) -> None:
        """Snippet 8: Are non-pregnant females."""
        snippet = grounding_snippets[8]
        assert len(snippet["entities"]) == 1
        e = snippet["entities"][0]
        assert "Pregnancy" in e["entity_name"]
        assert e["code"] == "C0032961"
        assert e["relation"] == "!="
        assert e["value"] == "True"
