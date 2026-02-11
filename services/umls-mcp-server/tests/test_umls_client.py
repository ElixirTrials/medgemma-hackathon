"""Unit tests for UMLS client: search, caching, errors, retry, exception hierarchy."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from umls_mcp_server.umls_api import (
    SnomedCandidate,
    UmlsApiAuthenticationError,
    UmlsApiClientError,
    UmlsApiError,
    UmlsApiRateLimitError,
    UmlsApiServerError,
    UmlsClient,
    _ServerError,
    get_umls_client,
)


def _make_response(
    status_code: int, json_data: dict | None = None, text: str = ""
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.is_success = 200 <= status_code < 300
    resp.text = text or str(json_data)
    resp.json.return_value = json_data or {}
    return resp


def _search_success_json() -> dict:
    return {
        "result": {
            "results": [
                {
                    "ui": "C0011849",
                    "name": "Diabetes mellitus",
                    "rootSource": "SNOMEDCT_US",
                },
                {"ui": "C0011847", "name": "Diabetes", "rootSource": "SNOMEDCT_US"},
            ]
        }
    }


def _atoms_success_json(code: str = "73211009") -> dict:
    return {"result": {"results": [{"code": code, "sourceUi": code}]}}


class TestUmlsClientSearch:
    """Tests for search_snomed."""

    def test_search_snomed_returns_candidates(
        self, tmp_path: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("UMLS_CACHE_DIR", str(tmp_path))
        mock_get = MagicMock(return_value=_make_response(200, _search_success_json()))
        with patch("umls_mcp_server.umls_api.httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__ = lambda self: self
            mock_client_cls.return_value.__exit__ = lambda *a: None
            mock_client_cls.return_value.get = mock_get
            with UmlsClient(api_key="test-key") as client:
                candidates = client.search_snomed("diabetes", limit=5)
        assert len(candidates) == 2
        assert candidates[0].cui == "C0011849"
        assert candidates[0].display == "Diabetes mellitus"
        assert candidates[0].ontology == "SNOMEDCT_US"
        assert candidates[0].confidence == 0.9

    def test_search_snomed_maps_fields_correctly(
        self, tmp_path: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("UMLS_CACHE_DIR", str(tmp_path))
        mock_get = MagicMock(return_value=_make_response(200, _search_success_json()))
        with patch("umls_mcp_server.umls_api.httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__ = lambda self: self
            mock_client_cls.return_value.__exit__ = lambda *a: None
            mock_client_cls.return_value.get = mock_get
            with patch.object(
                UmlsClient, "_get_snomed_code_for_cui", return_value="73211009"
            ):
                with UmlsClient(api_key="test-key") as client:
                    candidates = client.search_snomed("diabetes", limit=2)
        assert candidates[0].code == "73211009"
        assert candidates[0].cui == "C0011849"
        assert candidates[0].display == "Diabetes mellitus"

    def test_search_snomed_caches_results(
        self, tmp_path: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("UMLS_CACHE_DIR", str(tmp_path))
        mock_get = MagicMock(return_value=_make_response(200, _search_success_json()))
        with patch("umls_mcp_server.umls_api.httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__ = lambda self: self
            mock_client_cls.return_value.__exit__ = lambda *a: None
            mock_client_cls.return_value.get = mock_get
            with patch.object(
                UmlsClient, "_get_snomed_code_for_cui", return_value="73211009"
            ):
                with UmlsClient(api_key="test-key") as client:
                    client.search_snomed("diabetes", limit=5)
                    client.search_snomed("diabetes", limit=5)
        assert mock_get.call_count == 1

    def test_search_snomed_empty_query_raises(
        self, tmp_path: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("UMLS_CACHE_DIR", str(tmp_path))
        with patch("umls_mcp_server.umls_api.httpx.Client"):
            with UmlsClient(api_key="test-key") as client:
                with pytest.raises(ValueError, match="query is required"):
                    client.search_snomed("")
                with pytest.raises(ValueError, match="query is required"):
                    client.search_snomed("   ")

    def test_search_snomed_respects_limit(
        self, tmp_path: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("UMLS_CACHE_DIR", str(tmp_path))
        mock_get = MagicMock(return_value=_make_response(200, _search_success_json()))
        with patch("umls_mcp_server.umls_api.httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__ = lambda self: self
            mock_client_cls.return_value.__exit__ = lambda *a: None
            mock_client_cls.return_value.get = mock_get
            with patch.object(
                UmlsClient, "_get_snomed_code_for_cui", return_value="73211009"
            ):
                with UmlsClient(api_key="test-key") as client:
                    candidates = client.search_snomed("diabetes", limit=1)
        assert len(candidates) == 1

    def test_search_snomed_no_results(
        self, tmp_path: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("UMLS_CACHE_DIR", str(tmp_path))
        mock_get = MagicMock(
            return_value=_make_response(200, {"result": {"results": []}})
        )
        with patch("umls_mcp_server.umls_api.httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__ = lambda self: self
            mock_client_cls.return_value.__exit__ = lambda *a: None
            mock_client_cls.return_value.get = mock_get
            with UmlsClient(api_key="test-key") as client:
                candidates = client.search_snomed("xyznonexistent", limit=5)
        assert candidates == []


class TestUmlsClientConfig:
    """Tests for client configuration."""

    def test_default_base_url(self) -> None:
        with patch("umls_mcp_server.umls_api.httpx.Client"):
            client = UmlsClient(api_key="k")
            assert "uts-ws" in client.base_url
            client.close()

    def test_custom_base_url(self) -> None:
        with patch("umls_mcp_server.umls_api.httpx.Client"):
            client = UmlsClient(api_key="k", base_url="https://custom.example/rest")
            assert client.base_url == "https://custom.example/rest"
            client.close()

    def test_missing_api_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("UMLS_API_KEY", raising=False)
        with pytest.raises(ValueError, match="UMLS API key is required"):
            UmlsClient()

    def test_custom_timeout(self) -> None:
        with patch("umls_mcp_server.umls_api.httpx.Client") as m:
            UmlsClient(api_key="k", timeout=30.0)
            m.assert_called_once()
            call_kw = m.call_args[1]
            assert call_kw["timeout"] == 30.0

    def test_cache_ttl_default(self) -> None:
        assert UmlsClient._parse_cache_ttl(None) == 7 * 24 * 60 * 60

    def test_cache_ttl_from_env(self) -> None:
        assert UmlsClient._parse_cache_ttl("3600") == 3600
        assert UmlsClient._parse_cache_ttl("0") == 7 * 24 * 60 * 60
        assert UmlsClient._parse_cache_ttl("invalid") == 7 * 24 * 60 * 60


class TestUmlsClientExceptionHierarchy:
    """Tests for HTTP error mapping and exception hierarchy."""

    def test_authentication_error_401(
        self, tmp_path: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("UMLS_CACHE_DIR", str(tmp_path))
        mock_get = MagicMock(return_value=_make_response(401, None, "Unauthorized"))
        with patch("umls_mcp_server.umls_api.httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__ = lambda self: self
            mock_client_cls.return_value.__exit__ = lambda *a: None
            mock_client_cls.return_value.get = mock_get
            with UmlsClient(api_key="test-key") as client:
                with pytest.raises(UmlsApiAuthenticationError) as exc_info:
                    client.search_snomed("diabetes")
        assert exc_info.value.status_code == 401

    def test_authentication_error_403(
        self, tmp_path: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("UMLS_CACHE_DIR", str(tmp_path))
        mock_get = MagicMock(return_value=_make_response(403, None, "Forbidden"))
        with patch("umls_mcp_server.umls_api.httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__ = lambda self: self
            mock_client_cls.return_value.__exit__ = lambda *a: None
            mock_client_cls.return_value.get = mock_get
            with UmlsClient(api_key="test-key") as client:
                with pytest.raises(UmlsApiAuthenticationError) as exc_info:
                    client.search_snomed("diabetes")
        assert exc_info.value.status_code == 403

    def test_rate_limit_error_429(
        self, tmp_path: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("UMLS_CACHE_DIR", str(tmp_path))
        mock_get = MagicMock(
            return_value=_make_response(429, None, "Too Many Requests")
        )
        with patch("umls_mcp_server.umls_api.httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__ = lambda self: self
            mock_client_cls.return_value.__exit__ = lambda *a: None
            mock_client_cls.return_value.get = mock_get
            with UmlsClient(api_key="test-key") as client:
                with pytest.raises(UmlsApiRateLimitError) as exc_info:
                    client.search_snomed("diabetes")
        assert exc_info.value.status_code == 429

    def test_server_error_500(
        self, tmp_path: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("UMLS_CACHE_DIR", str(tmp_path))
        mock_get = MagicMock(
            return_value=_make_response(500, None, "Internal Server Error")
        )
        with patch("umls_mcp_server.umls_api.httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__ = lambda self: self
            mock_client_cls.return_value.__exit__ = lambda *a: None
            mock_client_cls.return_value.get = mock_get
            with UmlsClient(api_key="test-key") as client:
                with pytest.raises((_ServerError, UmlsApiServerError)):
                    client.search_snomed("diabetes")

    def test_client_error_400(
        self, tmp_path: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("UMLS_CACHE_DIR", str(tmp_path))
        mock_get = MagicMock(return_value=_make_response(400, None, "Bad Request"))
        with patch("umls_mcp_server.umls_api.httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__ = lambda self: self
            mock_client_cls.return_value.__exit__ = lambda *a: None
            mock_client_cls.return_value.get = mock_get
            with UmlsClient(api_key="test-key") as client:
                with pytest.raises(UmlsApiClientError) as exc_info:
                    client.search_snomed("diabetes")
        assert exc_info.value.status_code == 400

    def test_exception_hierarchy_inheritance(self) -> None:
        assert issubclass(UmlsApiAuthenticationError, UmlsApiClientError)
        assert issubclass(UmlsApiClientError, UmlsApiError)
        assert issubclass(UmlsApiRateLimitError, UmlsApiClientError)


class TestUmlsClientRetry:
    """Tests for tenacity retry behavior."""

    def test_retry_on_server_error_then_success(
        self,
        tmp_path: str,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("UMLS_CACHE_DIR", str(tmp_path))
        success_resp = _make_response(200, _search_success_json())
        error_resp = _make_response(500, None, "Error")
        mock_get = MagicMock(side_effect=[error_resp, success_resp])
        with patch("umls_mcp_server.umls_api.httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__ = lambda self: self
            mock_client_cls.return_value.__exit__ = lambda *a: None
            mock_client_cls.return_value.get = mock_get
            with patch.object(
                UmlsClient, "_get_snomed_code_for_cui", return_value="73211009"
            ):
                with UmlsClient(api_key="test-key") as client:
                    candidates = client.search_snomed("diabetes", limit=5)
        assert len(candidates) == 2
        assert mock_get.call_count == 2

    def test_no_retry_on_auth_error(
        self, tmp_path: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("UMLS_CACHE_DIR", str(tmp_path))
        mock_get = MagicMock(return_value=_make_response(401, None, "Unauthorized"))
        with patch("umls_mcp_server.umls_api.httpx.Client") as mock_client_cls:
            mock_client_cls.return_value.__enter__ = lambda self: self
            mock_client_cls.return_value.__exit__ = lambda *a: None
            mock_client_cls.return_value.get = mock_get
            with UmlsClient(api_key="test-key") as client:
                with pytest.raises(UmlsApiAuthenticationError):
                    client.search_snomed("diabetes")
        assert mock_get.call_count == 1


class TestUmlsClientContextManager:
    """Tests for context manager and factory."""

    def test_context_manager_closes_resources(self) -> None:
        with patch("umls_mcp_server.umls_api.httpx.Client") as m:
            inst = m.return_value
            with UmlsClient(api_key="k") as _client:
                pass
            inst.close.assert_called_once()

    def test_get_umls_client_factory(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("UMLS_API_KEY", "test-key")
        with patch("umls_mcp_server.umls_api.httpx.Client"):
            client = get_umls_client()
            assert isinstance(client, UmlsClient)
            client.close()


class TestSnomedCandidate:
    """Tests for SnomedCandidate dataclass."""

    def test_snomed_candidate_fields(self) -> None:
        c = SnomedCandidate(
            cui="C0011849",
            code="73211009",
            display="Diabetes mellitus",
            ontology="SNOMEDCT_US",
            confidence=0.9,
        )
        assert c.cui == "C0011849"
        assert c.code == "73211009"
        assert c.display == "Diabetes mellitus"
        assert c.ontology == "SNOMEDCT_US"
        assert c.confidence == 0.9
