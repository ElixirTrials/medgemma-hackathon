"""Tests for UMLS search proxy endpoint."""

from unittest.mock import MagicMock, patch

import pytest
from umls_mcp_server.umls_api import SnomedCandidate, UmlsApiError


@pytest.fixture
def mock_umls_client():
    """Create a mock UmlsClient for testing."""
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=None)
    return mock_client


def test_search_too_short(test_client):
    """GET /api/umls/search?q=ab returns 400 (query too short)."""
    response = test_client.get("/api/umls/search", params={"q": "ab"})
    assert response.status_code == 422  # FastAPI validation error
    assert "at least 3 characters" in response.json()["detail"][0]["msg"]


def test_search_success(test_client, mock_umls_client):
    """GET /api/umls/search?q=diabetes returns 200 with concept results."""
    # Mock UMLS client to return sample candidates
    mock_umls_client.search_snomed.return_value = [
        SnomedCandidate(
            cui="C0011849",
            code="73211009",
            display="Diabetes mellitus",
            ontology="SNOMEDCT_US",
            confidence=0.95,
        ),
        SnomedCandidate(
            cui="C0011854",
            code="44054006",
            display="Diabetes mellitus type 2",
            ontology="SNOMEDCT_US",
            confidence=0.90,
        ),
    ]

    with patch(
        "api_service.umls_search.get_umls_client",
        return_value=mock_umls_client,
    ):
        response = test_client.get("/api/umls/search", params={"q": "diabetes"})

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    # Verify first result structure
    assert data[0]["cui"] == "C0011849"
    assert data[0]["snomed_code"] == "73211009"
    assert data[0]["preferred_term"] == "Diabetes mellitus"
    assert data[0]["semantic_type"] == "Clinical Finding"
    assert data[0]["confidence"] == 0.95

    # Verify second result
    assert data[1]["cui"] == "C0011854"
    assert data[1]["snomed_code"] == "44054006"


def test_search_empty_results(test_client, mock_umls_client):
    """GET /api/umls/search with no results returns 200 with empty list."""
    mock_umls_client.search_snomed.return_value = []

    with patch(
        "api_service.umls_search.get_umls_client",
        return_value=mock_umls_client,
    ):
        response = test_client.get("/api/umls/search", params={"q": "xyz"})

    assert response.status_code == 200
    assert response.json() == []


def test_search_umls_error(test_client, mock_umls_client):
    """GET /api/umls/search returns 502 when UMLS API fails."""
    mock_umls_client.search_snomed.side_effect = UmlsApiError(
        message="UMLS API timeout",
        status_code=500,
    )

    with patch(
        "api_service.umls_search.get_umls_client",
        return_value=mock_umls_client,
    ):
        response = test_client.get("/api/umls/search", params={"q": "test"})

    assert response.status_code == 502
    assert "UMLS API error" in response.json()["detail"]


def test_search_not_configured(test_client):
    """GET /api/umls/search returns 503 when UMLS not configured."""
    with patch(
        "api_service.umls_search.get_umls_client",
        side_effect=ValueError("UMLS API key is required"),
    ):
        response = test_client.get("/api/umls/search", params={"q": "test"})

    assert response.status_code == 503
    assert "not configured" in response.json()["detail"]


def test_search_max_results_limit(test_client, mock_umls_client):
    """GET /api/umls/search respects max_results parameter."""
    mock_umls_client.search_snomed.return_value = [
        SnomedCandidate(
            cui=f"C{i:07d}",
            code=f"{i}",
            display=f"Concept {i}",
            ontology="SNOMEDCT_US",
            confidence=0.9,
        )
        for i in range(3)
    ]

    with patch(
        "api_service.umls_search.get_umls_client",
        return_value=mock_umls_client,
    ):
        response = test_client.get(
            "/api/umls/search",
            params={"q": "test", "max_results": 3},
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3

    # Verify client was called with correct limit
    mock_umls_client.search_snomed.assert_called_once_with("test", limit=3)


def test_search_max_results_clamped(test_client, mock_umls_client):
    """GET /api/umls/search validates max_results range (1-20)."""
    mock_umls_client.search_snomed.return_value = []

    with patch(
        "api_service.umls_search.get_umls_client",
        return_value=mock_umls_client,
    ):
        # Test upper bound validation (FastAPI rejects > 20)
        response = test_client.get(
            "/api/umls/search",
            params={"q": "test", "max_results": 100},
        )
        assert response.status_code == 422  # Validation error

        # Test lower bound validation (FastAPI rejects < 1)
        response = test_client.get(
            "/api/umls/search",
            params={"q": "test", "max_results": 0},
        )
        assert response.status_code == 422  # Validation error

        # Test valid range works
        response = test_client.get(
            "/api/umls/search",
            params={"q": "test", "max_results": 10},
        )
        assert response.status_code == 200
        mock_umls_client.search_snomed.assert_called_with("test", limit=10)
