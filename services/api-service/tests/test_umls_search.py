"""Tests for UMLS search proxy endpoint backed by ToolUniverse.

All ToolUniverse calls are mocked via patch on
api_service.umls_search.search_terminology. No real network calls are made.
"""

from unittest.mock import patch

from protocol_processor.schemas.grounding import GroundingCandidate


def _make_umls_candidate(
    code: str = "C0011849",
    preferred_term: str = "Diabetes mellitus",
    semantic_type: str | None = "Disease or Syndrome",
    score: float = 0.95,
) -> GroundingCandidate:
    return GroundingCandidate(
        source_api="umls",
        code=code,
        preferred_term=preferred_term,
        semantic_type=semantic_type,
        score=score,
    )


def test_search_too_short(test_client):
    """GET /api/umls/search?q=ab returns 422 (query too short)."""
    response = test_client.get("/api/umls/search", params={"q": "ab"})
    assert response.status_code == 422


def test_search_success(test_client):
    """GET /api/umls/search?q=diabetes returns 200 with ToolUniverse-backed results."""
    mock_candidates = [
        _make_umls_candidate(code="C0011849", preferred_term="Diabetes mellitus"),
        _make_umls_candidate(
            code="C0011860",
            preferred_term="Diabetes mellitus type 2",
            score=0.90,
        ),
    ]

    with patch(
        "api_service.umls_search.search_terminology",
        return_value=mock_candidates,
    ):
        response = test_client.get("/api/umls/search", params={"q": "diabetes"})

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2

    # Verify first result structure matches UmlsConceptResponse
    assert data[0]["cui"] == "C0011849"
    assert data[0]["preferred_term"] == "Diabetes mellitus"
    assert data[0]["confidence"] == 0.95
    assert "semantic_type" in data[0]
    assert "snomed_code" in data[0]

    # Verify second result
    assert data[1]["cui"] == "C0011860"
    assert data[1]["preferred_term"] == "Diabetes mellitus type 2"


def test_search_empty_results(test_client):
    """GET /api/umls/search with no results returns 200 with empty list."""
    with patch(
        "api_service.umls_search.search_terminology",
        return_value=[],
    ):
        response = test_client.get("/api/umls/search", params={"q": "xyz"})

    assert response.status_code == 200
    assert response.json() == []


def test_search_error_returns_502(test_client):
    """GET /api/umls/search returns 502 when ToolUniverse fails."""
    with patch(
        "api_service.umls_search.search_terminology",
        side_effect=RuntimeError("ToolUniverse connection refused"),
    ):
        response = test_client.get("/api/umls/search", params={"q": "test"})

    assert response.status_code == 502
    assert "Terminology lookup failed" in response.json()["detail"]


def test_search_max_results_limit(test_client):
    """GET /api/umls/search respects max_results parameter."""
    mock_candidates = [
        _make_umls_candidate(code=f"C{i:07d}", preferred_term=f"Concept {i}")
        for i in range(3)
    ]

    with patch(
        "api_service.umls_search.search_terminology",
        return_value=mock_candidates,
    ) as mock_search:
        response = test_client.get(
            "/api/umls/search",
            params={"q": "test", "max_results": 3},
        )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3

    # Verify client was called with correct limit
    mock_search.assert_called_once_with("umls", "test", max_results=3)


def test_search_max_results_clamped(test_client):
    """GET /api/umls/search validates max_results range (1-20)."""
    with patch(
        "api_service.umls_search.search_terminology",
        return_value=[],
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
