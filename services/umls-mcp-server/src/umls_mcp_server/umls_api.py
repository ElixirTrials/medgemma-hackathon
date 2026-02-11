"""UMLS REST API client for the UMLS MCP server."""

import logging
import os

import httpx

logger = logging.getLogger(__name__)

UMLS_BASE_URL = "https://uts-ws.nlm.nih.gov/rest"


class UMLSClient:
    """Async client for the UMLS REST API.

    Uses the official UMLS Terminology Services REST API at
    https://uts-ws.nlm.nih.gov/rest for concept search, lookup,
    and SNOMED-CT crosswalk.
    """

    def __init__(self, api_key: str) -> None:
        """Initialize with a UMLS API key.

        Args:
            api_key: UMLS Terminology Services API key.
        """
        self.api_key = api_key

    async def search(
        self,
        term: str,
        sabs: str = "SNOMEDCT_US",
        search_type: str = "exact",
        max_results: int = 5,
    ) -> list[dict]:
        """Search UMLS concepts by term.

        Args:
            term: Medical term to search for.
            sabs: Source vocabulary to filter (default: SNOMEDCT_US).
            search_type: Search type - "exact" or "words".
            max_results: Maximum number of results to return.

        Returns:
            List of matching concepts with cui, name, and source.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{UMLS_BASE_URL}/search/current",
                params={
                    "string": term,
                    "apiKey": self.api_key,
                    "sabs": sabs,
                    "searchType": search_type,
                    "returnIdType": "concept",
                    "pageSize": max_results,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("result", {}).get("results", [])
            return [
                {
                    "cui": r["ui"],
                    "name": r["name"],
                    "source": r.get("rootSource", ""),
                }
                for r in results
                if r.get("ui") != "NONE"
            ]

    async def get_concept(self, cui: str) -> dict | None:
        """Validate that a CUI exists in UMLS and return its details.

        Args:
            cui: UMLS Concept Unique Identifier (e.g., "C0011849").

        Returns:
            Concept dict with cui and name, or None if not found.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{UMLS_BASE_URL}/content/current/CUI/{cui}",
                params={"apiKey": self.api_key},
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            result = data.get("result", {})
            return {
                "cui": result.get("ui", cui),
                "name": result.get("name", ""),
            }

    async def get_snomed_code(self, cui: str) -> str | None:
        """Get the SNOMED-CT code for a given CUI.

        Args:
            cui: UMLS CUI to look up.

        Returns:
            SNOMED-CT code string, or None if no mapping found.
        """
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{UMLS_BASE_URL}/search/current",
                params={
                    "string": cui,
                    "apiKey": self.api_key,
                    "sabs": "SNOMEDCT_US",
                    "returnIdType": "code",
                    "pageSize": 1,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            results = data.get("result", {}).get("results", [])
            if results and results[0].get("ui") != "NONE":
                return str(results[0]["ui"])
            return None


def get_umls_client() -> UMLSClient:
    """Factory function to get the UMLS client.

    Requires UMLS_API_KEY environment variable to be set.
    Raises ValueError if the key is missing.

    Returns:
        UMLSClient instance.
    """
    api_key = os.getenv("UMLS_API_KEY", "")
    if not api_key:
        raise ValueError(
            "UMLS_API_KEY environment variable is required but not set. "
            "Get a key at https://uts.nlm.nih.gov/uts/signup-login"
        )
    return UMLSClient(api_key=api_key)
