"""Base class and shared data types for terminology HTTP clients.

All terminology clients (RxNorm, ICD-10, LOINC, HPO) extend this ABC.
Built-in disk caching (diskcache) and retry (tenacity) are wired in here
so individual clients only need to implement _fetch.
"""

from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

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

_DEFAULT_TTL = 7 * 24 * 60 * 60  # 7 days in seconds


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class TerminologyResult:
    """A single terminology match result.

    Attributes:
        code: The terminology-specific code (e.g., "1049502" for RxNorm).
        display: Human-readable concept name.
        system: Terminology system name (e.g., "RxNorm", "ICD-10-CM").
        confidence: Relevance/confidence score in range [0.0, 1.0].
        method: How the result was found (e.g., "exact", "approximate").
    """

    code: str
    display: str
    system: str
    confidence: float
    method: str


# ---------------------------------------------------------------------------
# Internal sentinel for server errors (triggers tenacity retry)
# ---------------------------------------------------------------------------


class _TransientError(Exception):
    """Raised internally to trigger tenacity retry on 5xx / 429 errors."""

    def __init__(self, status_code: int, body: str) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"Transient error {status_code}: {body[:100]}")


# ---------------------------------------------------------------------------
# Abstract base client
# ---------------------------------------------------------------------------


class BaseTerminologyClient(ABC):
    """Abstract base class for async terminology API clients.

    Provides:
    - ``httpx.AsyncClient`` with configurable timeout (default 10s).
    - Disk-based response caching via ``diskcache.Cache`` (default TTL 7 days).
    - Retry with exponential backoff via ``tenacity`` (3 attempts, 0.5-2s).

    Subclasses must implement ``_fetch`` which performs the actual HTTP
    request and returns a list of ``TerminologyResult`` objects.
    The ``search`` method handles caching and retry automatically.
    """

    #: Subclasses override to provide a unique cache namespace.
    _cache_namespace: str = "base"

    def __init__(
        self,
        timeout: float = 10.0,
        cache_ttl: int = _DEFAULT_TTL,
        cache_dir: str | None = None,
    ) -> None:
        """Initialise shared HTTP client, cache, and retry configuration.

        Args:
            timeout: HTTP request timeout in seconds.
            cache_ttl: Cache TTL in seconds (default 7 days).
            cache_dir: Override directory for disk cache. Defaults to
                ``platformdirs.user_cache_dir("terminology-clients")``.
        """
        self._http = httpx.AsyncClient(timeout=timeout)
        self._cache_ttl = cache_ttl

        resolved_dir = cache_dir or os.getenv("TERMINOLOGY_CACHE_DIR")
        default_path = (
            Path(user_cache_dir("terminology-clients")) / self._cache_namespace
        )
        cache_path = (
            Path(resolved_dir) / self._cache_namespace
            if resolved_dir
            else default_path
        )
        cache_path.mkdir(parents=True, exist_ok=True)
        self._cache: diskcache.Cache = diskcache.Cache(str(cache_path))

    # -- Public API ----------------------------------------------------------

    async def search(self, term: str, limit: int = 5) -> list[TerminologyResult]:
        """Search for terminology matches for the given clinical term.

        Checks the disk cache first. On cache miss, calls ``_fetch`` with
        retry on transient errors.

        Args:
            term: Clinical term to search (e.g., "aspirin").
            limit: Maximum number of results to return (default 5).

        Returns:
            List of TerminologyResult objects (may be empty on no match).
        """
        if not term.strip():
            return []

        cache_key = f"{self._cache_namespace}:{term.lower().strip()}:{limit}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached  # type: ignore[return-value]

        results = await self._fetch_with_retry(term.strip(), limit)
        if results:
            self._cache.set(cache_key, results, expire=self._cache_ttl)
        return results

    async def aclose(self) -> None:
        """Close the underlying HTTP client and cache."""
        await self._http.aclose()
        try:
            self._cache.close()
        except (OSError, AttributeError):
            pass

    # -- Abstract interface --------------------------------------------------

    @abstractmethod
    async def _fetch(self, term: str, limit: int) -> list[TerminologyResult]:
        """Perform the actual HTTP request(s) and return results.

        Implementations should raise ``_TransientError`` for 5xx/429 responses
        so that the retry decorator in ``_fetch_with_retry`` can retry them.

        Args:
            term: Pre-stripped search term.
            limit: Maximum results to return.

        Returns:
            List of TerminologyResult objects.
        """
        ...

    # -- Internal retry wrapper ---------------------------------------------

    @retry(
        retry=retry_if_exception_type((httpx.RequestError, _TransientError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
        reraise=True,
    )
    async def _fetch_with_retry(self, term: str, limit: int) -> list[TerminologyResult]:
        """Invoke ``_fetch`` with tenacity retry on transient errors."""
        return await self._fetch(term, limit)
