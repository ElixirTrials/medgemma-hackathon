"""Async UMLS REST API validation client.

Provides functions to validate CUI codes and retrieve SNOMED-CT
codes from the UMLS REST API. Used by the validate_confidence
graph node to verify grounding results before database storage.

When UMLS_API_KEY is not set, operates in mock mode: validate_cui
returns True and get_snomed_code_for_cui returns a placeholder code.
This enables development and testing without UMLS credentials.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

UMLS_API_KEY = os.getenv("UMLS_API_KEY", "")
UMLS_BASE_URL = "https://uts-ws.nlm.nih.gov/rest"

_mock_warning_logged = False


def _log_mock_warning() -> None:
    """Log a warning on first mock mode call."""
    global _mock_warning_logged  # noqa: PLW0603
    if not _mock_warning_logged:
        logger.warning(
            "UMLS_API_KEY not set -- running in mock mode. "
            "CUI validation and SNOMED lookups will return mock values."
        )
        _mock_warning_logged = True


async def validate_cui(cui: str) -> bool:
    """Validate that a CUI exists in UMLS.

    Calls GET /content/current/CUI/{cui} to verify the CUI is
    a real UMLS concept. In mock mode (no API key), always returns
    True to allow development without credentials.

    Args:
        cui: UMLS Concept Unique Identifier (e.g., 'C0011849').

    Returns:
        True if the CUI exists (or in mock mode), False otherwise.
    """
    if not cui:
        return False

    if not UMLS_API_KEY:
        _log_mock_warning()
        return True

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{UMLS_BASE_URL}/content/current/CUI/{cui}",
                params={"apiKey": UMLS_API_KEY},
            )
            return resp.status_code == 200
    except Exception:
        logger.warning("UMLS CUI validation failed for %s", cui)
        return False


async def get_snomed_code_for_cui(cui: str) -> str | None:
    """Get SNOMED-CT code for a given CUI.

    Searches UMLS with the CUI filtered to SNOMEDCT_US source
    and returnIdType=code. In mock mode (no API key), returns
    a placeholder SNOMED code ("73211009" -- diabetes mellitus).

    Args:
        cui: UMLS CUI to look up.

    Returns:
        SNOMED-CT code string, or None if not found.
    """
    if not cui:
        return None

    if not UMLS_API_KEY:
        _log_mock_warning()
        return "73211009"

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{UMLS_BASE_URL}/search/current",
                params={
                    "string": cui,
                    "apiKey": UMLS_API_KEY,
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
    except Exception:
        logger.warning("SNOMED lookup failed for CUI %s", cui)
        return None
