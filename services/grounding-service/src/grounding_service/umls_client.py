"""Async UMLS REST API validation client.

Uses the shared UmlsClient from umls-mcp-server for UMLS API access.
Provides async wrappers for use in grounding-service graph nodes.
"""

from umls_mcp_server.umls_api import get_umls_client


async def validate_cui(cui: str) -> bool:
    """Validate that a CUI exists in UMLS.

    Args:
        cui: UMLS Concept Unique Identifier (e.g., 'C0011849').

    Returns:
        True if the CUI exists, False otherwise.
    """
    if not cui:
        return False
    client = get_umls_client()
    try:
        result = client.get_concept(cui)
        return result is not None
    finally:
        client.close()


async def get_snomed_code_for_cui(cui: str) -> str | None:
    """Get SNOMED-CT code for a given CUI.

    Args:
        cui: UMLS CUI to look up.

    Returns:
        SNOMED-CT code string, or None if not found.
    """
    if not cui:
        return None
    client = get_umls_client()
    try:
        return client.get_snomed_code(cui)
    finally:
        client.close()
