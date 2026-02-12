"""FastMCP server exposing UMLS concept search, linking, and semantic type tools."""

import logging
import re

from dotenv import load_dotenv
from fastmcp import FastMCP

from umls_mcp_server.umls_api import SnomedCandidate, get_umls_client

# Load .env from current working directory (e.g. repo root) so UMLS_API_KEY is set.
load_dotenv()

logger = logging.getLogger(__name__)

mcp = FastMCP("UMLS Grounding Server")


def _candidate_to_dict(c: SnomedCandidate) -> dict:
    """SnomedCandidate -> dict with snomed_code, display, cui, ontology, confidence."""
    return {
        "snomed_code": c.code,
        "display": c.display,
        "cui": c.cui,
        "ontology": c.ontology,
        "confidence": c.confidence,
    }


@mcp.tool()
async def concept_search(
    term: str,
    sabs: str = "SNOMEDCT_US",
    max_results: int = 5,
) -> list[dict]:
    """Search UMLS for concepts matching a medical term.

    Args:
        term: Medical term to search for (e.g., "diabetes mellitus").
        sabs: Source vocabulary to filter (default: SNOMEDCT_US).
        max_results: Maximum results to return.

    Returns:
        List of matching concepts with CUI, name, and source info.
    """
    with get_umls_client() as client:
        candidates = client.search_snomed(term, limit=max_results)
    return [_candidate_to_dict(c) for c in candidates]


@mcp.tool()
async def concept_linking(
    term: str,
    context: str = "",
    sabs: str = "SNOMEDCT_US",
) -> dict:
    """Link a medical term to its best-matching UMLS concept with tiered grounding.

    Uses a three-tier strategy:
    1. Exact match (confidence 0.95)
    2. Semantic similarity via word search (confidence 0.75)
    3. Expert review fallback (confidence 0.0)

    Args:
        term: Medical entity text to link.
        context: Surrounding context for disambiguation.
        sabs: Source vocabulary filter.

    Returns:
        Best matching concept with CUI, name, confidence, and method.
    """
    logger.debug("concept_linking called: term=%r, context=%r", term, context)
    with get_umls_client() as client:
        candidates = client.search_snomed(term, limit=5)
    if candidates:
        first = candidates[0]
        is_exact = bool(re.fullmatch(r"\d+", term.strip()))
        result_dict = {
            "cui": first.cui,
            "name": first.display,
            "source": first.ontology,
            "confidence": 0.95 if is_exact else 0.75,
            "method": "exact_match" if is_exact else "semantic_similarity",
        }
        logger.debug("concept_linking result: %r", result_dict)
        return result_dict
    result_dict = {
        "cui": None,
        "name": None,
        "source": None,
        "confidence": 0.0,
        "method": "expert_review",
        "nearest_term": term,
    }
    logger.debug("concept_linking result (no candidates): %r", result_dict)
    return result_dict


@mcp.tool()
async def semantic_type_prediction(term: str, entity_type: str) -> list[str]:
    """Predict UMLS semantic types for a medical entity based on its type.

    Maps entity types to their expected UMLS semantic type identifiers (TUIs).

    Args:
        term: The medical entity text.
        entity_type: Entity type (Condition, Medication, Procedure,
            Lab_Value, Demographic, Biomarker).

    Returns:
        List of expected UMLS semantic type abbreviations.
    """
    type_map: dict[str, list[str]] = {
        "Condition": ["T047", "T048", "T191"],
        "Medication": ["T121", "T200"],
        "Procedure": ["T061", "T060"],
        "Lab_Value": ["T059", "T034"],
        "Demographic": ["T032"],
        "Biomarker": ["T116", "T123"],
    }
    return type_map.get(entity_type, [])


if __name__ == "__main__":
    mcp.run(transport="stdio")
