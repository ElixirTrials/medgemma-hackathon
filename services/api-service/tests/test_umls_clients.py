"""Unit tests for UMLS REST API clients with mocked httpx.

Tests both the umls_mcp_server.umls_api.UmlsClient class and
the grounding_service.umls_client validation functions.
"""

from unittest.mock import MagicMock, patch

import pytest
from umls_mcp_server.umls_api import (
    UmlsApiClientError,
    UmlsClient,
    get_umls_client,
)

# ---------------------------------------------------------------------------
# UmlsClient (umls_mcp_server) tests — sync client with search_snomed
# ---------------------------------------------------------------------------


class TestUmlsClientSearch:
    """Tests for UmlsClient.search_snomed()."""

    def test_search_returns_matching_concepts(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("UMLS_CACHE_DIR", str(tmp_path))
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.text = ""
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
        mock_get = MagicMock(return_value=mock_response)
        with patch("umls_mcp_server.umls_api.httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__ = lambda self: self
            mock_client_cls.return_value.__exit__ = lambda *a: None
            mock_client_cls.return_value.get = mock_get
            with patch.object(
                UmlsClient, "_get_snomed_code_for_cui", return_value="73211009"
            ):
                with UmlsClient(api_key="test-key") as client:
                    results = client.search_snomed("diabetes")
        assert len(results) == 1
        assert results[0].cui == "C0011849"
        assert results[0].display == "Diabetes Mellitus"
        assert results[0].ontology == "SNOMEDCT_US"

    def test_search_filters_out_none_results(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("UMLS_CACHE_DIR", str(tmp_path))
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.text = ""
        mock_response.json.return_value = {
            "result": {
                "results": [
                    {"ui": "NONE", "name": "NO RESULTS", "rootSource": ""},
                    {
                        "ui": "C0011849",
                        "name": "Diabetes Mellitus",
                        "rootSource": "SNOMEDCT_US",
                    },
                ]
            }
        }
        mock_get = MagicMock(return_value=mock_response)
        with patch("umls_mcp_server.umls_api.httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__ = lambda self: self
            mock_client_cls.return_value.__exit__ = lambda *a: None
            mock_client_cls.return_value.get = mock_get
            with patch.object(
                UmlsClient, "_get_snomed_code_for_cui", return_value="73211009"
            ):
                with UmlsClient(api_key="test-key") as client:
                    results = client.search_snomed("diabetes")
        assert len(results) == 2
        assert results[1].cui == "C0011849"

    def test_search_passes_correct_params(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("UMLS_CACHE_DIR", str(tmp_path))
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.text = ""
        mock_response.json.return_value = {"result": {"results": []}}
        mock_get = MagicMock(return_value=mock_response)
        with patch("umls_mcp_server.umls_api.httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__ = lambda self: self
            mock_client_cls.return_value.__exit__ = lambda *a: None
            mock_client_cls.return_value.get = mock_get
            with UmlsClient(api_key="test-key") as client:
                client.search_snomed("test", limit=5)
        call_args = mock_get.call_args
        assert call_args is not None
        params = call_args.kwargs.get("params", call_args[1] if call_args[1] else {})
        assert params.get("string") == "test"
        assert params.get("apiKey") == "test-key"
        assert params.get("sabs") == "SNOMEDCT_US"
        assert params.get("pageSize") == 5


class TestUmlsClientGetConcept:
    """Tests for UmlsClient.get_concept()."""

    def test_returns_concept_when_found(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("UMLS_CACHE_DIR", str(tmp_path))
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.text = ""
        mock_response.json.return_value = {
            "result": {"ui": "C0011849", "name": "Diabetes Mellitus"}
        }
        mock_get = MagicMock(return_value=mock_response)
        with patch("umls_mcp_server.umls_api.httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__ = lambda self: self
            mock_client_cls.return_value.__exit__ = lambda *a: None
            mock_client_cls.return_value.get = mock_get
            with UmlsClient(api_key="test-key") as client:
                result = client.get_concept("C0011849")
        assert result is not None
        assert result.get("result", {}).get("ui") == "C0011849"

    def test_raises_on_404(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("UMLS_CACHE_DIR", str(tmp_path))
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.is_success = False
        mock_response.text = "Not Found"
        mock_get = MagicMock(return_value=mock_response)
        with patch("umls_mcp_server.umls_api.httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__ = lambda self: self
            mock_client_cls.return_value.__exit__ = lambda *a: None
            mock_client_cls.return_value.get = mock_get
            with UmlsClient(api_key="test-key") as client:
                with pytest.raises(UmlsApiClientError):
                    client.get_concept("INVALID")


class TestUmlsClientGetSnomedCode:
    """Tests for UmlsClient.get_snomed_code()."""

    def test_returns_snomed_code(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("UMLS_CACHE_DIR", str(tmp_path))
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.text = ""
        mock_response.json.return_value = {
            "result": {"results": [{"code": "73211009", "sourceUi": "73211009"}]}
        }
        mock_get = MagicMock(return_value=mock_response)
        with patch("umls_mcp_server.umls_api.httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__ = lambda self: self
            mock_client_cls.return_value.__exit__ = lambda *a: None
            mock_client_cls.return_value.get = mock_get
            with UmlsClient(api_key="test-key") as client:
                code = client.get_snomed_code("C0011849")
        assert code == "73211009"

    def test_returns_none_when_no_mapping(self, tmp_path, monkeypatch) -> None:
        monkeypatch.setenv("UMLS_CACHE_DIR", str(tmp_path))
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.text = ""
        mock_response.json.return_value = {"result": {"results": []}}
        mock_get = MagicMock(return_value=mock_response)
        with patch("umls_mcp_server.umls_api.httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__ = lambda self: self
            mock_client_cls.return_value.__exit__ = lambda *a: None
            mock_client_cls.return_value.get = mock_get
            with UmlsClient(api_key="test-key") as client:
                code = client.get_snomed_code("C9999999")
        assert code is None


class TestGetUmlsClient:
    """Tests for get_umls_client() factory."""

    def test_raises_when_api_key_not_set(self, monkeypatch) -> None:
        monkeypatch.delenv("UMLS_API_KEY", raising=False)
        with pytest.raises(ValueError, match="UMLS_API_KEY"):
            get_umls_client()

    def test_returns_client_when_api_key_set(self, monkeypatch) -> None:
        monkeypatch.setenv("UMLS_API_KEY", "test-key-123")
        with patch("umls_mcp_server.umls_api.httpx.Client"):
            client = get_umls_client()
            assert isinstance(client, UmlsClient)
            assert client.api_key == "test-key-123"
            client.close()


# ---------------------------------------------------------------------------
# Agent-B UMLS validation client tests
# ---------------------------------------------------------------------------


class TestAgentBValidateCui:
    """Tests for grounding_service.umls_client.validate_cui()."""

    @pytest.mark.asyncio
    async def test_returns_true_when_cui_exists(self, monkeypatch) -> None:
        monkeypatch.setenv("UMLS_API_KEY", "test-key")
        from grounding_service.umls_client import validate_cui

        mock_client = MagicMock()
        mock_client.get_concept.return_value = {"result": {"ui": "C0011849"}}
        cm = MagicMock()
        cm.__enter__.return_value = mock_client
        cm.__exit__.return_value = False
        with patch(
            "grounding_service.umls_client.get_umls_client",
            return_value=cm,
        ):
            result = await validate_cui("C0011849")
        assert result is True

    @pytest.mark.asyncio
    async def test_returns_false_when_cui_not_found(self, monkeypatch) -> None:
        monkeypatch.setenv("UMLS_API_KEY", "test-key")
        from grounding_service.umls_client import validate_cui

        mock_client = MagicMock()
        mock_client.get_concept.return_value = None
        cm = MagicMock()
        cm.__enter__.return_value = mock_client
        cm.__exit__.return_value = False
        with patch(
            "grounding_service.umls_client.get_umls_client",
            return_value=cm,
        ):
            result = await validate_cui("INVALID")
        assert result is False

    @pytest.mark.asyncio
    async def test_empty_cui_returns_false_without_api_call(self, monkeypatch) -> None:
        monkeypatch.setenv("UMLS_API_KEY", "test-key")
        from grounding_service.umls_client import validate_cui

        result = await validate_cui("")
        assert result is False

    @pytest.mark.asyncio
    async def test_raises_when_api_key_not_set(self, monkeypatch) -> None:
        monkeypatch.delenv("UMLS_API_KEY", raising=False)
        from grounding_service.umls_client import validate_cui

        with pytest.raises(ValueError, match="UMLS_API_KEY"):
            await validate_cui("C0011849")


class TestAgentBGetSnomedCodeForCui:
    """Tests for grounding_service.umls_client.get_snomed_code_for_cui()."""

    @pytest.mark.asyncio
    async def test_returns_snomed_code(self, monkeypatch) -> None:
        monkeypatch.setenv("UMLS_API_KEY", "test-key")
        from grounding_service.umls_client import get_snomed_code_for_cui

        mock_client = MagicMock()
        mock_client.get_snomed_code.return_value = "73211009"
        cm = MagicMock()
        cm.__enter__.return_value = mock_client
        cm.__exit__.return_value = False
        with patch(
            "grounding_service.umls_client.get_umls_client",
            return_value=cm,
        ):
            code = await get_snomed_code_for_cui("C0011849")
        assert code == "73211009"

    @pytest.mark.asyncio
    async def test_empty_cui_returns_none(self, monkeypatch) -> None:
        monkeypatch.setenv("UMLS_API_KEY", "test-key")
        from grounding_service.umls_client import get_snomed_code_for_cui

        result = await get_snomed_code_for_cui("")
        assert result is None

    @pytest.mark.asyncio
    async def test_raises_when_api_key_not_set(self, monkeypatch) -> None:
        monkeypatch.delenv("UMLS_API_KEY", raising=False)
        from grounding_service.umls_client import get_snomed_code_for_cui

        with pytest.raises(ValueError, match="UMLS_API_KEY"):
            await get_snomed_code_for_cui("C0011849")
