"""Integration tests for the grounding pipeline with real UMLS API.

These tests require UMLS_API_KEY to be set (either in env or .env file).
They verify end-to-end grounding: MCP tool invocation, result parsing,
CUI resolution, and SNOMED lookup.

Skipped automatically if UMLS_API_KEY is not available.
"""

import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import json

import pytest
from dotenv import load_dotenv

# Load .env so UMLS_API_KEY is available even when not exported
load_dotenv()

_UMLS_API_KEY = os.getenv("UMLS_API_KEY")
_skip_no_api_key = pytest.mark.skipif(
    not _UMLS_API_KEY,
    reason="UMLS_API_KEY not set",
)


def _parse_content_blocks(blocks: list) -> dict:
    """Extract JSON dict from a list of MCP content blocks."""
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            text_val = block.get("text", "")
            if isinstance(text_val, str):
                return json.loads(text_val)
    return {}


def _normalize_tool_result(raw_result: object) -> dict:
    """Normalize MCP tool result (mirrors ground_to_umls._normalize_tool_result)."""
    if isinstance(raw_result, dict):
        return raw_result
    if isinstance(raw_result, str):
        return json.loads(raw_result)
    # langchain-mcp-adapters 0.2.x returns list of content blocks
    if isinstance(raw_result, list):
        return _parse_content_blocks(raw_result)
    if hasattr(raw_result, "content"):
        content = raw_result.content
        if isinstance(content, str):
            return json.loads(content)
        if isinstance(content, dict):
            return content
        if isinstance(content, list):
            return _parse_content_blocks(content)
    return {}


@_skip_no_api_key
@pytest.mark.asyncio
async def test_mcp_concept_linking_returns_cui() -> None:
    """Verify concept_linking resolves acetaminophen to a UMLS CUI."""
    from langchain_mcp_adapters.client import MultiServerMCPClient
    from langchain_mcp_adapters.sessions import StdioConnection

    mcp_config = {
        "umls": StdioConnection(
            command="uv",
            args=["run", "python", "-m", "umls_mcp_server.server"],
            transport="stdio",
        )
    }

    mcp_client = MultiServerMCPClient(mcp_config)  # type: ignore[arg-type]
    tools = await mcp_client.get_tools()
    concept_linking_tool = next((t for t in tools if t.name == "concept_linking"), None)
    assert concept_linking_tool is not None, "concept_linking tool not found"

    raw_result = await concept_linking_tool.ainvoke(
        {"term": "acetaminophen", "context": ""}
    )
    parsed = _normalize_tool_result(raw_result)

    assert parsed.get("cui") is not None, f"Expected CUI, got: {parsed}"
    assert parsed.get("method") != "expert_review", f"Expected grounded, got: {parsed}"
    assert (parsed.get("confidence") or 0) > 0.5, f"Low confidence: {parsed}"


@_skip_no_api_key
@pytest.mark.asyncio
async def test_mcp_concept_linking_multiple_terms() -> None:
    """Verify multiple known medical terms resolve to CUIs."""
    from langchain_mcp_adapters.client import MultiServerMCPClient
    from langchain_mcp_adapters.sessions import StdioConnection

    mcp_config = {
        "umls": StdioConnection(
            command="uv",
            args=["run", "python", "-m", "umls_mcp_server.server"],
            transport="stdio",
        )
    }

    mcp_client = MultiServerMCPClient(mcp_config)  # type: ignore[arg-type]
    tools = await mcp_client.get_tools()
    concept_linking_tool = next((t for t in tools if t.name == "concept_linking"), None)
    assert concept_linking_tool is not None

    terms = ["osteoarthritis", "Heparin", "diabetes mellitus", "hypertension"]
    successes = 0

    for term in terms:
        raw_result = await concept_linking_tool.ainvoke({"term": term, "context": ""})
        parsed = _normalize_tool_result(raw_result)
        if parsed.get("cui") is not None:
            successes += 1

    assert successes >= 3, (
        f"Expected at least 3/4 terms to ground, got {successes}/{len(terms)}"
    )


@_skip_no_api_key
@pytest.mark.asyncio
async def test_ground_via_mcp_function() -> None:
    """Verify _ground_via_mcp returns grounded entities with CUI."""
    from grounding_service.nodes.ground_to_umls import _ground_via_mcp

    entities = [
        {
            "text": "acetaminophen",
            "entity_type": "Medication",
            "context_window": "",
            "criteria_id": "test",
            "span_start": 0,
            "span_end": 13,
        }
    ]

    result = await _ground_via_mcp(entities)

    assert len(result) == 1
    grounded = result[0]
    assert grounded["umls_cui"] is not None, f"Expected CUI, got: {grounded}"
    assert grounded["grounding_method"] != "expert_review", (
        f"Expected grounded, got: {grounded}"
    )


@_skip_no_api_key
@pytest.mark.asyncio
async def test_snomed_lookup_for_known_cui() -> None:
    """Verify SNOMED lookup succeeds for a known CUI (acetaminophen)."""
    from langchain_mcp_adapters.client import MultiServerMCPClient
    from langchain_mcp_adapters.sessions import StdioConnection

    from grounding_service.umls_client import get_snomed_code_for_cui

    mcp_config = {
        "umls": StdioConnection(
            command="uv",
            args=["run", "python", "-m", "umls_mcp_server.server"],
            transport="stdio",
        )
    }

    mcp_client = MultiServerMCPClient(mcp_config)  # type: ignore[arg-type]
    tools = await mcp_client.get_tools()
    concept_linking_tool = next((t for t in tools if t.name == "concept_linking"), None)
    assert concept_linking_tool is not None

    raw_result = await concept_linking_tool.ainvoke(
        {"term": "acetaminophen", "context": ""}
    )
    parsed = _normalize_tool_result(raw_result)
    cui = parsed.get("cui")
    assert cui is not None, "Need a valid CUI to test SNOMED lookup"

    # Now test SNOMED lookup
    snomed_code = await get_snomed_code_for_cui(cui)
    assert snomed_code is not None, f"Expected SNOMED code for CUI {cui}, got None"
