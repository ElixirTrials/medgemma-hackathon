"""UMLS SNOMED client with disk cache, retry, and exception hierarchy.

Provides a production-quality sync HTTP client for the UMLS REST API
with disk-based caching (diskcache), retry with exponential backoff
(tenacity), and a structured exception hierarchy.

Environment variables:
- UMLS_API_KEY: API key for UMLS (required).
- UMLS_BASE_URL: Base URL override (optional; defaults to
  https://uts-ws.nlm.nih.gov/rest).
- UMLS_TIMEOUT_SECONDS: HTTP timeout in seconds (optional; default 10).
- UMLS_CACHE_TTL_SECONDS: TTL in seconds for cache entries (optional;
  defaults to 7 days; must be >0).
- UMLS_CACHE_DIR: Directory for disk cache (optional; defaults to
  platformdirs user_cache_dir).
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import diskcache  # type: ignore[import-untyped]
import httpx
from platformdirs import user_cache_dir
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

UMLS_DEFAULT_URL = "https://uts-ws.nlm.nih.gov/rest"

# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class UmlsApiError(Exception):
    """Base exception for all UMLS API errors."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        response_body: str | None = None,
    ) -> None:
        """Initialize UMLS API error.

        Args:
            message: Error message.
            status_code: HTTP status code if applicable.
            response_body: Response body if applicable.
        """
        self.message = message
        self.status_code = status_code
        self.response_body = response_body
        super().__init__(self.message)


class UmlsApiClientError(UmlsApiError):
    """4xx errors: client configuration or request issues."""


class UmlsApiServerError(UmlsApiError):
    """5xx errors: server-side issues."""


class UmlsApiTimeoutError(UmlsApiError):
    """Request timeout errors."""


class UmlsApiAuthenticationError(UmlsApiClientError):
    """401/403: authentication or authorization failures."""


class UmlsApiRateLimitError(UmlsApiClientError):
    """429: rate limit exceeded."""


class _ServerError(Exception):
    """Internal: raised on 5xx to trigger tenacity retry."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"Server error {status_code}: {body[:100]}")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SnomedCandidate:
    """SNOMED candidate returned from UMLS search.

    Attributes:
        cui: UMLS Concept Unique Identifier.
        code: SNOMED concept code.
        display: Human-readable concept name.
        ontology: Ontology label (e.g., SNOMEDCT_US).
        confidence: Confidence or relevance score.
    """

    cui: str
    code: str
    display: str
    ontology: str
    confidence: float


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


class UmlsClient:
    """Sync HTTP client for UMLS REST API with disk cache and retry.

    Uses httpx.Client (sync) for HTTP transport, diskcache.Cache for
    disk-based caching, and tenacity for retry with exponential backoff
    on transient errors (5xx, 429, network errors).

    Args:
        base_url: Base URL for the UMLS REST API.
        api_key: UMLS API key (required).
        timeout: HTTP timeout in seconds.
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float | None = None,
    ) -> None:
        """Initialize the UMLS client configuration."""
        self.base_url: str = base_url or os.getenv("UMLS_BASE_URL") or UMLS_DEFAULT_URL
        self.api_key = api_key or os.getenv("UMLS_API_KEY")
        env_timeout = os.getenv("UMLS_TIMEOUT_SECONDS")
        self.timeout = (
            float(env_timeout)
            if env_timeout
            else (timeout if timeout is not None else 10.0)
        )
        if not self.api_key:
            raise ValueError(
                "UMLS API key is required. Set UMLS_API_KEY environment variable."
            )
        self._http = httpx.Client(timeout=self.timeout)
        cache_dir = os.getenv("UMLS_CACHE_DIR")
        default_cache = Path(user_cache_dir("umls-mcp-server")) / "umls"
        cache_path = Path(cache_dir) if cache_dir else default_cache
        cache_path.mkdir(parents=True, exist_ok=True)
        self._cache_dir = str(cache_path)
        self._cache_ttl = self._parse_cache_ttl(os.getenv("UMLS_CACHE_TTL_SECONDS"))
        self._cache = diskcache.Cache(self._cache_dir)

    # -- Context manager --------------------------------------------------

    def __enter__(self) -> "UmlsClient":
        """Enter context manager scope."""
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        """Exit context manager scope and close resources."""
        self.close()

    # -- Public API --------------------------------------------------------

    def search_snomed(self, query: str, limit: int = 5) -> list[SnomedCandidate]:
        """Search SNOMED concepts via UMLS.

        Args:
            query: Free-text clinical concept to search.
            limit: Maximum number of candidates to return.

        Returns:
            A list of candidate SNOMED concepts.

        Raises:
            ValueError: If the query is empty.
            UmlsApiAuthenticationError: If authentication fails (401/403).
            UmlsApiRateLimitError: If rate limit is exceeded (429).
            UmlsApiServerError: If server error persists after retries.
        """
        if not query.strip():
            raise ValueError("query is required")

        cache_key = f"snomed:{query.lower()}:{limit}"
        cached = cast(list[SnomedCandidate] | None, self._cache.get(cache_key))
        if cached:
            return cached

        candidates = self._fetch_from_api(query, limit)
        if self._cache_ttl:
            self._cache.set(cache_key, candidates, expire=self._cache_ttl)
        return candidates

    def get_concept(self, cui: str) -> dict[str, object] | None:
        """Get concept details for a CUI from UMLS.

        Args:
            cui: UMLS Concept Unique Identifier.

        Returns:
            Dictionary with concept data, or None if not found.
        """
        if not cui.strip():
            return None

        cache_key = f"concept:{cui}"
        cached = cast(dict[str, object] | None, self._cache.get(cache_key))
        if cached:
            return cached

        url = f"{self.base_url.rstrip('/')}/content/current/CUI/{cui}"
        params: dict[str, str | int] = {"apiKey": self.api_key or ""}

        data = self._request_with_retry(url, params)
        if self._cache_ttl:
            self._cache.set(cache_key, data, expire=self._cache_ttl)
        return data

    def get_snomed_code(self, cui: str) -> str | None:
        """Get SNOMED-CT code for a given CUI.

        Fetches the SNOMED code via /CUI/{cui}/atoms endpoint filtered
        to SNOMEDCT_US source.

        Args:
            cui: UMLS CUI to look up.

        Returns:
            SNOMED-CT code string, or None if not found.
        """
        if not cui.strip():
            return None

        cache_key = f"snomed_code:{cui}"
        cached = cast(str | None, self._cache.get(cache_key))
        if cached:
            return cached

        url = f"{self.base_url.rstrip('/')}/content/current/CUI/{cui}/atoms"
        params: dict[str, str | int] = {
            "sabs": "SNOMEDCT_US",
            "pageSize": 1,
            "apiKey": self.api_key or "",
        }
        data = self._request_with_retry(url, params)
        snomed_code = self._extract_snomed_code_from_atoms(data)
        if snomed_code and self._cache_ttl:
            self._cache.set(cache_key, snomed_code, expire=self._cache_ttl)
        return snomed_code or None

    def close(self) -> None:
        """Close the HTTP client and release resources."""
        self._http.close()
        try:
            self._cache.close()
        except (OSError, AttributeError):
            pass

    # -- Internal ----------------------------------------------------------

    def _fetch_from_api(self, query: str, limit: int) -> list[SnomedCandidate]:
        """Execute HTTP request to UMLS search API with retry."""
        url = f"{self.base_url.rstrip('/')}/search/current"
        is_code_query = bool(re.fullmatch(r"\d+", query.strip()))
        params: dict[str, str | int] = {
            "string": query,
            "sabs": "SNOMEDCT_US",
            "searchType": "exact" if is_code_query else "words",
            "inputType": "sourceUi" if is_code_query else "atom",
            "pageSize": limit,
            "apiKey": self.api_key or "",
        }

        data = self._request_with_retry(url, params)
        fallback = query if is_code_query else ""
        return self._parse_response(data, limit, fallback_code=fallback)

    @retry(
        retry=retry_if_exception_type(
            (httpx.RequestError, _ServerError, UmlsApiRateLimitError)
        ),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
        reraise=True,
    )
    def _request_with_retry(
        self, url: str, params: dict[str, str | int]
    ) -> dict[str, object]:
        """Make HTTP request with tenacity retry on transient errors."""
        response = self._http.get(url, params=params)
        if response.status_code >= 500:
            raise _ServerError(response.status_code, response.text)
        if response.status_code == 429:
            raise UmlsApiRateLimitError(
                message=f"Rate limit exceeded: {response.text[:200]}",
                status_code=429,
                response_body=response.text[:500],
            )
        if not response.is_success:
            raise self._map_http_error(response)
        return response.json()  # type: ignore[no-any-return]

    def _map_http_error(self, response: httpx.Response) -> UmlsApiError:
        """Map HTTP response to appropriate UMLS API exception."""
        status = response.status_code
        body = response.text[:500]

        if status in (401, 403):
            return UmlsApiAuthenticationError(
                message=f"Authentication failed: {body}",
                status_code=status,
                response_body=body,
            )
        if status == 429:
            return UmlsApiRateLimitError(
                message=f"Rate limit exceeded: {body}",
                status_code=status,
                response_body=body,
            )
        if 400 <= status < 500:
            return UmlsApiClientError(
                message=f"Client error {status}: {body}",
                status_code=status,
                response_body=body,
            )
        if status >= 500:
            return UmlsApiServerError(
                message=f"Server error {status}: {body}",
                status_code=status,
                response_body=body,
            )
        return UmlsApiError(
            message=f"Unexpected status {status}: {body}",
            status_code=status,
            response_body=body,
        )

    def _parse_response(
        self,
        data: dict[str, object],
        limit: int,
        fallback_code: str = "",
    ) -> list[SnomedCandidate]:
        """Parse UMLS API response into SnomedCandidate list."""
        result = data.get("result", {})
        if not isinstance(result, dict):
            return []
        results = result.get("results", [])
        if not isinstance(results, Sequence):
            return []

        candidates: list[SnomedCandidate] = []
        for item in results[:limit]:
            if not isinstance(item, dict):
                continue
            ui = item.get("ui")
            name = item.get("name")
            root = item.get("rootSource")
            cui = str(ui) if isinstance(ui, str) else ""
            snomed_code = fallback_code
            if cui and not snomed_code:
                snomed_code = self._get_snomed_code_for_cui(cui)
            candidates.append(
                SnomedCandidate(
                    cui=cui,
                    code=snomed_code,
                    display=str(name) if isinstance(name, str) else "",
                    ontology=str(root) if isinstance(root, str) else "SNOMEDCT_US",
                    confidence=0.9,
                )
            )
        return candidates

    def _get_snomed_code_for_cui(self, cui: str) -> str:
        """Fetch SNOMED code for a CUI via atoms endpoint (internal)."""
        cache_key = f"snomed_code:{cui}"
        cached = cast(str | None, self._cache.get(cache_key))
        if cached:
            return cached

        url = f"{self.base_url.rstrip('/')}/content/current/CUI/{cui}/atoms"
        params: dict[str, str | int] = {
            "sabs": "SNOMEDCT_US",
            "pageSize": 1,
            "apiKey": self.api_key or "",
        }
        try:
            data = self._request_with_retry(url, params)
            snomed_code = self._extract_snomed_code_from_atoms(data)
            if self._cache_ttl:
                self._cache.set(cache_key, snomed_code, expire=self._cache_ttl)
            return snomed_code
        except (UmlsApiError, _ServerError, httpx.RequestError) as exc:
            logger.warning("UMLS API error for CUI atoms %s: %s", cui, exc)
            return ""

    @staticmethod
    def _extract_code_from_value(value: str) -> str:
        """Extract a numeric SNOMED code from a value that may be a URL.

        The UMLS atoms API returns code/sourceConcept as full URLs like
        ``https://uts-ws.nlm.nih.gov/rest/content/2025AB/source/SNOMEDCT_US/387517004``.
        This extracts the trailing numeric code segment.

        Args:
            value: Raw value from UMLS API (may be a URL or plain code).

        Returns:
            Extracted numeric code, or the original value if no URL pattern.
        """
        if "/" in value:
            # Extract last path segment (e.g., 387517004 from URL)
            last_segment = value.rstrip("/").rsplit("/", 1)[-1]
            if last_segment and last_segment != "NONE":
                return last_segment
        return value

    @staticmethod
    def _extract_snomed_code_from_atoms(data: dict[str, object]) -> str:
        """Extract SNOMED code from atoms API response.

        The atoms endpoint returns either:
        - ``{"result": [...]}`` (list of atoms directly)
        - ``{"result": {"results": [...]}}`` (nested dict with results)
        """
        result = data.get("result", {})

        # Handle direct list of atoms (most common for /CUI/{cui}/atoms)
        atoms: Sequence[object] = []
        if isinstance(result, list):
            atoms = result
        elif isinstance(result, dict):
            inner = result.get("results", [])
            if isinstance(inner, Sequence):
                atoms = inner

        if not atoms:
            return ""

        first = atoms[0]
        if not isinstance(first, dict):
            return ""

        for key in ("code", "sourceConcept", "sourceConceptId", "sourceUi"):
            value = first.get(key)
            if isinstance(value, str) and value and value != "NONE":
                extracted = UmlsClient._extract_code_from_value(value)
                if extracted and extracted != "NONE":
                    return extracted
        return ""

    @staticmethod
    def _parse_cache_ttl(value: str | None) -> int:
        """Parse cache TTL from string value.

        Args:
            value: TTL string in seconds, or None for default.

        Returns:
            TTL in seconds (default 7 days).
        """
        if not value:
            return 7 * 24 * 60 * 60
        try:
            ttl = int(value)
        except ValueError:
            return 7 * 24 * 60 * 60
        return ttl if ttl > 0 else 7 * 24 * 60 * 60


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_umls_client() -> UmlsClient:
    """Create a UmlsClient using environment configuration.

    Raises ValueError if UMLS_API_KEY is not set.

    Returns:
        Configured UmlsClient instance.
    """
    return UmlsClient()
