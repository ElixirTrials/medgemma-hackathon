"""FastMCP server exposing UMLS concept search, linking, and semantic type tools."""

from fastmcp import FastMCP

from umls_mcp_server.umls_api import get_umls_client

mcp = FastMCP("UMLS Grounding Server")


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
    client = get_umls_client()
    return await client.search(
        term, sabs=sabs, search_type="exact", max_results=max_results
    )


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
    client = get_umls_client()

    # Tier 1: Exact match
    exact_results = await client.search(
        term, sabs=sabs, search_type="exact", max_results=1
    )
    if exact_results:
        return {**exact_results[0], "confidence": 0.95, "method": "exact_match"}

    # Tier 2: Semantic similarity (words search)
    word_results = await client.search(
        term, sabs=sabs, search_type="words", max_results=5
    )
    if word_results:
        return {
            **word_results[0],
            "confidence": 0.75,
            "method": "semantic_similarity",
        }

    # Tier 3: No match -- flag for expert review
    return {
        "cui": None,
        "name": None,
        "source": None,
        "confidence": 0.0,
        "method": "expert_review",
        "nearest_term": term,
    }


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
