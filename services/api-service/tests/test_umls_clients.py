"""Unit tests for ToolUniverse-backed terminology search endpoint.

Tests the /api/terminology/{system}/search endpoint using mocked ToolUniverse
calls. Verifies response format, error handling, and parameter passing.
"""

from unittest.mock import patch

import pytest
from protocol_processor.schemas.grounding import GroundingCandidate

# ---------------------------------------------------------------------------
# Helper: mock candidates
# ---------------------------------------------------------------------------


def _make_candidate(
    source_api: str = "umls",
    code: str = "C0011849",
    preferred_term: str = "Diabetes Mellitus",
    semantic_type: str | None = "Disease or Syndrome",
    score: float = 0.95,
) -> GroundingCandidate:
    return GroundingCandidate(
        source_api=source_api,
        code=code,
        preferred_term=preferred_term,
        semantic_type=semantic_type,
        score=score,
    )


# ---------------------------------------------------------------------------
# /api/terminology/{system}/search tests
# ---------------------------------------------------------------------------


class TestTerminologySearchEndpoint:
    """Tests for GET /api/terminology/{system}/search."""

    def test_invalid_system_returns_400(self, test_client) -> None:
        response = test_client.get(
            "/api/terminology/invalid/search", params={"q": "test"}
        )
        assert response.status_code == 400
        assert "Invalid terminology system" in response.json()["detail"]

    def test_query_too_short_returns_422(self, test_client) -> None:
        response = test_client.get("/api/terminology/icd10/search", params={"q": "ab"})
        assert response.status_code == 422

    def test_icd10_search_returns_200(self, test_client) -> None:
        mock_candidates = [
            _make_candidate(
                source_api="icd10",
                code="I10",
                preferred_term="Essential (primary) hypertension",
                semantic_type=None,
                score=1.0,
            )
        ]
        with patch(
            "api_service.terminology_search.tu_search",
            return_value=mock_candidates,
        ):
            response = test_client.get(
                "/api/terminology/icd10/search", params={"q": "hypertension"}
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["code"] == "I10"
        assert data[0]["display"] == "Essential (primary) hypertension"
        assert data[0]["system"] == "icd10"
        assert data[0]["confidence"] == 1.0

    def test_rxnorm_search_returns_200(self, test_client) -> None:
        mock_candidates = [
            _make_candidate(
                source_api="rxnorm",
                code="6809",
                preferred_term="Metformin",
                semantic_type=None,
                score=0.9,
            )
        ]
        with patch(
            "api_service.terminology_search.tu_search",
            return_value=mock_candidates,
        ):
            response = test_client.get(
                "/api/terminology/rxnorm/search", params={"q": "metformin"}
            )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["code"] == "6809"
        assert data[0]["system"] == "rxnorm"

    def test_snomed_search_returns_200(self, test_client) -> None:
        mock_candidates = [
            _make_candidate(
                source_api="snomed",
                code="C2733146",
                preferred_term="Type 2 Diabetes Mellitus",
                semantic_type="SNOMEDCT_US",
                score=0.95,
            )
        ]
        with patch(
            "api_service.terminology_search.tu_search",
            return_value=mock_candidates,
        ):
            response = test_client.get(
                "/api/terminology/snomed/search", params={"q": "diabetes"}
            )

        assert response.status_code == 200
        data = response.json()
        assert data[0]["code"] == "C2733146"
        assert data[0]["system"] == "snomed"

    def test_empty_results_returns_200_empty_list(self, test_client) -> None:
        with patch(
            "api_service.terminology_search.tu_search",
            return_value=[],
        ):
            response = test_client.get(
                "/api/terminology/hpo/search", params={"q": "xyzzy123"}
            )
        assert response.status_code == 200
        assert response.json() == []

    def test_exception_returns_502(self, test_client) -> None:
        with patch(
            "api_service.terminology_search.tu_search",
            side_effect=RuntimeError("ToolUniverse timeout"),
        ):
            response = test_client.get(
                "/api/terminology/loinc/search", params={"q": "glucose"}
            )
        assert response.status_code == 502
        assert "failed" in response.json()["detail"].lower()

    @pytest.mark.parametrize(
        "system", ["rxnorm", "icd10", "loinc", "hpo", "umls", "snomed"]
    )
    def test_all_valid_systems_accepted(self, test_client, system: str) -> None:
        with patch(
            "api_service.terminology_search.tu_search",
            return_value=[],
        ):
            response = test_client.get(
                f"/api/terminology/{system}/search", params={"q": "test"}
            )
        assert response.status_code == 200
