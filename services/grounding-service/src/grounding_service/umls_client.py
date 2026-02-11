"""Async UMLS REST API validation client.

Provides functions to validate CUI codes and retrieve SNOMED-CT
codes from the UMLS REST API. Used by the validate_confidence
graph node to verify grounding results before database storage.

Requires UMLS_API_KEY environment variable to be set.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

UMLS_BASE_URL = "https://uts-ws.nlm.nih.gov/rest"


def _get_api_key() -> str:
    """Get the UMLS API key from environment, raising if not set."""
    api_key = os.getenv("UMLS_API_KEY", "")
    if not api_key:
        raise ValueError(
            "UMLS_API_KEY environment variable is required but not set. "
            "Get a key at https://uts.nlm.nih.gov/uts/signup-login"
        )
    return api_key


async def validate_cui(cui: str) -> bool:
    """Validate that a CUI exists in UMLS.

    Calls GET /content/current/CUI/{cui} to verify the CUI is
    a real UMLS concept.

    Args:
        cui: UMLS Concept Unique Identifier (e.g., 'C0011849').

    Returns:
        True if the CUI exists, False otherwise.

    Raises:
        ValueError: If UMLS_API_KEY is not set.
    """
    if not cui:
        return False

    api_key = _get_api_key()

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{UMLS_BASE_URL}/content/current/CUI/{cui}",
            params={"apiKey": api_key},
        )
        return resp.status_code == 200


async def get_snomed_code_for_cui(cui: str) -> str | None:
    """Get SNOMED-CT code for a given CUI.

    Searches UMLS with the CUI filtered to SNOMEDCT_US source
    and returnIdType=code.

    Args:
        cui: UMLS CUI to look up.

    Returns:
        SNOMED-CT code string, or None if not found.

    Raises:
        ValueError: If UMLS_API_KEY is not set.
    """
    if not cui:
        return None

    api_key = _get_api_key()

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{UMLS_BASE_URL}/search/current",
            params={
                "string": cui,
                "apiKey": api_key,
                "sabs": "SNOMEDCT_US",
                "returnIdType": "code",
                "pageSize": 1,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        results = data.get("result", {}).get("results", [])
        if results and results[0].get("ui") != "NONE":
            return results[0]["ui"]
        return None
