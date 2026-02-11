"""Unit tests for UMLS REST API clients with mocked httpx.

Tests both the umls_mcp_server.umls_api.UMLSClient class and
the agent_b_service.umls_client validation functions.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from umls_mcp_server.umls_api import UMLSClient, get_umls_client

# ---------------------------------------------------------------------------
# UMLSClient (umls_mcp_server) tests
# ---------------------------------------------------------------------------


class TestUMLSClientSearch:
    """Tests for UMLSClient.search()."""

    async def test_search_returns_matching_concepts(self) -> None:
        client = UMLSClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {
                "results": [
                    {
                        "ui": "C0011849",
                        "name": "Diabetes Mellitus",
                        "rootSource": "SNOMEDCT_US",
                    },
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        with patch.object(
            httpx, "AsyncClient", return_value=mock_http
        ):
            results = await client.search("diabetes")

        assert len(results) == 1
        assert results[0]["cui"] == "C0011849"
        assert results[0]["name"] == "Diabetes Mellitus"
        assert results[0]["source"] == "SNOMEDCT_US"

    async def test_search_filters_out_none_results(self) -> None:
        client = UMLSClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {
                "results": [
                    {"ui": "NONE", "name": "NO RESULTS"},
                    {
                        "ui": "C0011849",
                        "name": "Diabetes Mellitus",
                        "rootSource": "SNOMEDCT_US",
                    },
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        with patch.object(
            httpx, "AsyncClient", return_value=mock_http
        ):
            results = await client.search("diabetes")

        assert len(results) == 1
        assert results[0]["cui"] == "C0011849"

    async def test_search_passes_correct_params(self) -> None:
        client = UMLSClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.json.return_value = {"result": {"results": []}}
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        with patch.object(
            httpx, "AsyncClient", return_value=mock_http
        ):
            await client.search(
                "test",
                sabs="SNOMEDCT_US",
                search_type="exact",
                max_results=5,
            )

        call_kwargs = mock_http.get.call_args
        assert "params" in call_kwargs.kwargs
        params = call_kwargs.kwargs["params"]
        assert params["string"] == "test"
        assert params["apiKey"] == "test-key"
        assert params["sabs"] == "SNOMEDCT_US"
        assert params["searchType"] == "exact"
        assert params["returnIdType"] == "concept"
        assert params["pageSize"] == 5


class TestUMLSClientGetConcept:
    """Tests for UMLSClient.get_concept()."""

    async def test_returns_concept_when_found(self) -> None:
        client = UMLSClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "result": {
                "ui": "C0011849",
                "name": "Diabetes Mellitus",
            }
        }

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        with patch.object(
            httpx, "AsyncClient", return_value=mock_http
        ):
            result = await client.get_concept("C0011849")

        assert result is not None
        assert result["cui"] == "C0011849"
        assert result["name"] == "Diabetes Mellitus"

    async def test_returns_none_when_not_found(self) -> None:
        client = UMLSClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        with patch.object(
            httpx, "AsyncClient", return_value=mock_http
        ):
            result = await client.get_concept("INVALID")

        assert result is None


class TestUMLSClientGetSnomedCode:
    """Tests for UMLSClient.get_snomed_code()."""

    async def test_returns_snomed_code(self) -> None:
        client = UMLSClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {
                "results": [
                    {"ui": "73211009", "name": "Diabetes mellitus"},
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        with patch.object(
            httpx, "AsyncClient", return_value=mock_http
        ):
            code = await client.get_snomed_code("C0011849")

        assert code == "73211009"

    async def test_returns_none_when_no_mapping(self) -> None:
        client = UMLSClient(api_key="test-key")
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {
                "results": [{"ui": "NONE", "name": "NO RESULTS"}]
            }
        }
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        with patch.object(
            httpx, "AsyncClient", return_value=mock_http
        ):
            code = await client.get_snomed_code("C9999999")

        assert code is None


class TestGetUmlsClient:
    """Tests for get_umls_client() factory."""

    def test_raises_when_api_key_not_set(self, monkeypatch) -> None:
        monkeypatch.delenv("UMLS_API_KEY", raising=False)
        with pytest.raises(ValueError, match="UMLS_API_KEY"):
            get_umls_client()

    def test_returns_client_when_api_key_set(
        self, monkeypatch
    ) -> None:
        monkeypatch.setenv("UMLS_API_KEY", "test-key-123")
        client = get_umls_client()
        assert isinstance(client, UMLSClient)
        assert client.api_key == "test-key-123"


# ---------------------------------------------------------------------------
# Agent-B UMLS validation client tests
# ---------------------------------------------------------------------------


class TestAgentBValidateCui:
    """Tests for agent_b_service.umls_client.validate_cui()."""

    async def test_returns_true_when_cui_exists(
        self, monkeypatch
    ) -> None:
        monkeypatch.setenv("UMLS_API_KEY", "test-key")

        from agent_b_service.umls_client import validate_cui

        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        with patch.object(
            httpx, "AsyncClient", return_value=mock_http
        ):
            result = await validate_cui("C0011849")

        assert result is True

    async def test_returns_false_when_cui_not_found(
        self, monkeypatch
    ) -> None:
        monkeypatch.setenv("UMLS_API_KEY", "test-key")

        from agent_b_service.umls_client import validate_cui

        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        with patch.object(
            httpx, "AsyncClient", return_value=mock_http
        ):
            result = await validate_cui("INVALID")

        assert result is False

    async def test_empty_cui_returns_false_without_api_call(
        self, monkeypatch
    ) -> None:
        monkeypatch.setenv("UMLS_API_KEY", "test-key")

        from agent_b_service.umls_client import validate_cui

        result = await validate_cui("")
        assert result is False

    async def test_raises_when_api_key_not_set(
        self, monkeypatch
    ) -> None:
        monkeypatch.delenv("UMLS_API_KEY", raising=False)

        from agent_b_service.umls_client import validate_cui

        with pytest.raises(ValueError, match="UMLS_API_KEY"):
            await validate_cui("C0011849")


class TestAgentBGetSnomedCodeForCui:
    """Tests for agent_b_service.umls_client.get_snomed_code_for_cui()."""

    async def test_returns_snomed_code(self, monkeypatch) -> None:
        monkeypatch.setenv("UMLS_API_KEY", "test-key")

        from agent_b_service.umls_client import get_snomed_code_for_cui

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "result": {
                "results": [
                    {"ui": "73211009", "name": "Diabetes mellitus"},
                ]
            }
        }
        mock_response.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_response)
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=None)

        with patch.object(
            httpx, "AsyncClient", return_value=mock_http
        ):
            code = await get_snomed_code_for_cui("C0011849")

        assert code == "73211009"

    async def test_empty_cui_returns_none(
        self, monkeypatch
    ) -> None:
        monkeypatch.setenv("UMLS_API_KEY", "test-key")

        from agent_b_service.umls_client import get_snomed_code_for_cui

        result = await get_snomed_code_for_cui("")
        assert result is None

    async def test_raises_when_api_key_not_set(
        self, monkeypatch
    ) -> None:
        monkeypatch.delenv("UMLS_API_KEY", raising=False)

        from agent_b_service.umls_client import get_snomed_code_for_cui

        with pytest.raises(ValueError, match="UMLS_API_KEY"):
            await get_snomed_code_for_cui("C0011849")
