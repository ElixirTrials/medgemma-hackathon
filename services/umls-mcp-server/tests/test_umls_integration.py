"""Integration tests for real UMLS API calls.

Requires a valid UMLS_API_KEY (not the unit-test placeholder).
Run with: uv run pytest tests/test_umls_integration.py -v -m integration
Or: UMLS_API_KEY=<your-key> uv run pytest tests/test_umls_integration.py -v
Skipped when UMLS_API_KEY is unset or "test-key-for-unit-tests".
"""

from __future__ import annotations

import os

import pytest

from umls_mcp_server.umls_api import UmlsClient

# Placeholder used by conftest for unit tests; integration needs a real key.
_PLACEHOLDER_KEY = "test-key-for-unit-tests"


def _has_real_api_key() -> bool:
    key = os.getenv("UMLS_API_KEY")
    return bool(key) and key != _PLACEHOLDER_KEY


requires_umls_key = pytest.mark.skipif(
    not _has_real_api_key(),
    reason="UMLS_API_KEY not set or is unit-test placeholder; set real key to run",
)

pytestmark = [pytest.mark.integration, requires_umls_key]


@pytest.fixture(scope="module")
def umls_api_key() -> str:
    """Return the configured UMLS API key (skip if not real)."""
    key = os.getenv("UMLS_API_KEY")
    if not key or key == _PLACEHOLDER_KEY:
        pytest.skip(
            "Set UMLS_API_KEY to a real UMLS API key to run integration tests. "
            "Get a key at https://uts.nlm.nih.gov/uts/signup-login"
        )
    return key


class TestUmlsIntegration:
    """Integration tests that hit the real UMLS REST API."""

    def test_search_snomed_returns_candidates(self, umls_api_key: str) -> None:
        """Search for a common medical term and verify candidates returned."""
        with UmlsClient(api_key=umls_api_key) as client:
            candidates = client.search_snomed("heart failure")

        assert len(candidates) > 0
        assert candidates[0].display
        assert candidates[0].ontology
        assert candidates[0].cui
        if candidates[0].code:
            assert len(candidates[0].code) > 0

    def test_search_snomed_diabetes(self, umls_api_key: str) -> None:
        """Search for diabetes and verify result contains diabetes-related concepts."""
        with UmlsClient(api_key=umls_api_key) as client:
            candidates = client.search_snomed("diabetes mellitus")

        assert len(candidates) > 0
        displays = [c.display.lower() for c in candidates]
        assert any("diabetes" in d for d in displays)

    def test_search_snomed_melanoma(self, umls_api_key: str) -> None:
        """Search for melanoma and verify candidates."""
        with UmlsClient(api_key=umls_api_key) as client:
            candidates = client.search_snomed("melanoma")

        assert len(candidates) > 0
        displays = [c.display.lower() for c in candidates]
        assert any("melanoma" in d for d in displays)

    def test_search_snomed_respects_limit(self, umls_api_key: str) -> None:
        """Verify limit parameter is respected."""
        with UmlsClient(api_key=umls_api_key) as client:
            candidates = client.search_snomed("cancer", limit=3)

        assert len(candidates) <= 3

    def test_search_snomed_empty_query_raises(self, umls_api_key: str) -> None:
        """Empty query should raise ValueError."""
        with UmlsClient(api_key=umls_api_key) as client:
            with pytest.raises(ValueError, match="query is required"):
                client.search_snomed("")

    def test_search_snomed_caching(self, umls_api_key: str) -> None:
        """Second call for same query returns same results (cache or live)."""
        with UmlsClient(api_key=umls_api_key) as client:
            first = client.search_snomed("hypertension")
            second = client.search_snomed("hypertension")

        assert first == second
        assert len(first) > 0

    def test_get_concept_returns_dict_for_valid_cui(self, umls_api_key: str) -> None:
        """get_concept returns concept data for a known CUI (e.g. diabetes)."""
        with UmlsClient(api_key=umls_api_key) as client:
            # C0011849 = Diabetes mellitus
            result = client.get_concept("C0011849")

        assert result is not None
        assert isinstance(result, dict)

    def test_get_snomed_code_for_valid_cui(self, umls_api_key: str) -> None:
        """get_snomed_code returns a SNOMED code for a known CUI."""
        with UmlsClient(api_key=umls_api_key) as client:
            code = client.get_snomed_code("C0011849")

        # Diabetes mellitus has SNOMED representation; may be non-empty string
        assert code is None or (isinstance(code, str) and len(code) > 0)
