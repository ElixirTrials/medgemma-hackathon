"""MedGemma agentic grounding node.

Implements a programmatic agentic loop where MedGemma extracts medical
entities from criteria text and iteratively refines UMLS grounding via
MCP concept_search. This replaces the previous 3-node pipeline
(extract_entities -> ground_to_umls -> map_to_snomed).

Architecture:
- MedGemma doesn't support native tool calling (Model Garden endpoint)
- Code orchestrates the loop: MedGemma JSON -> code calls UMLS MCP -> fed back
- Max 3 iterations per criterion batch
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from inference.config import AgentConfig
from inference.model_garden import ModelGardenChatModel, create_model_loader
from langchain_core.messages import HumanMessage, SystemMessage
from shared.resilience import umls_breaker, vertex_ai_breaker
from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

from grounding_service.schemas.agentic_actions import (
    AgenticAction,
    ExtractedEntityAction,
    GroundingSelection,
)
from grounding_service.state import GroundingState

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
MAX_ITERATIONS = 3

# Cache the model loader across invocations
_model_loader = None


def _get_medgemma_model() -> ModelGardenChatModel:
    """Get or create the MedGemma model instance."""
    global _model_loader  # noqa: PLW0603
    if _model_loader is None:
        _model_loader = create_model_loader(AgentConfig.from_env())
    return _model_loader()


def _render_template(template_name: str, **kwargs: Any) -> str:
    """Render a Jinja2 template from the prompts directory."""
    from jinja2 import Environment, FileSystemLoader

    env = Environment(loader=FileSystemLoader(str(PROMPTS_DIR)))
    template = env.get_template(template_name)
    return template.render(**kwargs)


def _parse_json_response(text: str) -> dict[str, Any]:
    """Parse JSON from MedGemma response, handling markdown fences."""
    text = text.strip()
    # Strip markdown code fences if present
    if text.startswith("```"):
        # Remove opening fence (```json or ```)
        first_newline = text.find("\n")
        if first_newline >= 0:
            text = text[first_newline + 1 :]
        # Remove closing fence
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3].rstrip()
    return json.loads(text)


def _load_criteria_texts(criteria_ids: list[str]) -> list[dict[str, Any]]:
    """Load criteria records from the database.

    Args:
        criteria_ids: List of Criteria record IDs to load.

    Returns:
        List of criteria dicts with id, text, criteria_type, category.
    """
    from api_service.storage import engine
    from shared.models import Criteria
    from sqlmodel import Session

    criteria_texts: list[dict[str, Any]] = []
    with Session(engine) as session:
        for cid in criteria_ids:
            criterion = session.get(Criteria, cid)
            if criterion:
                criteria_texts.append(
                    {
                        "id": criterion.id,
                        "text": criterion.text,
                        "criteria_type": criterion.criteria_type,
                        "category": criterion.category,
                    }
                )
    return criteria_texts


def _parse_content_blocks(blocks: list[Any]) -> list[dict[str, Any]]:
    """Extract JSON from MCP content blocks (concept_search returns a list).

    langchain-mcp-adapters 0.2.x returns content as a list of
    ``{"type": "text", "text": "<json>"}`` blocks.
    """
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            text_val = block.get("text", "")
            if isinstance(text_val, str):
                parsed = json.loads(text_val)
                if isinstance(parsed, list):
                    return parsed
                return [parsed]
    return []


def _parse_json_as_list(raw: str) -> list[dict[str, Any]]:
    """Parse a JSON string and ensure the result is a list."""
    parsed = json.loads(raw)
    if isinstance(parsed, list):
        return parsed
    return [parsed]


def _normalize_tool_message_content(
    content: Any,
) -> list[dict[str, Any]]:
    """Normalize ToolMessage .content to a list of candidate dicts."""
    if isinstance(content, str):
        return _parse_json_as_list(content)
    if isinstance(content, list):
        return _parse_content_blocks(content)
    if isinstance(content, dict):
        return [content]
    return []


def _normalize_search_results(raw_result: object) -> list[dict[str, Any]]:
    """Normalize MCP concept_search result to a list of candidate dicts.

    concept_search returns a LIST of candidates (unlike concept_linking
    which returns a single dict). Each candidate has:
    snomed_code, display, cui, ontology, confidence
    """
    if isinstance(raw_result, list):
        if raw_result and isinstance(raw_result[0], dict):
            if raw_result[0].get("type") == "text":
                return _parse_content_blocks(raw_result)
            return raw_result
        return []

    if isinstance(raw_result, str):
        return _parse_json_as_list(raw_result)

    if isinstance(raw_result, dict):
        return [raw_result]

    # ToolMessage wrapper
    if hasattr(raw_result, "content"):
        return _normalize_tool_message_content(raw_result.content)

    logger.warning(
        "Unexpected concept_search result type: %s",
        type(raw_result).__name__,
    )
    return []


@umls_breaker
@retry(
    retry=retry_if_exception_type((RuntimeError, ConnectionError, OSError)),
    stop=stop_after_attempt(3),
    wait=wait_random_exponential(multiplier=1, min=4, max=10),
    before_sleep=before_sleep_log(logger, logging.WARNING),
    reraise=True,
)
async def _search_umls_for_entities(
    entities: list[ExtractedEntityAction],
) -> list[dict[str, Any]]:
    """Search UMLS for each entity via MCP concept_search.

    Returns list of dicts with entity info + candidates list.
    """
    from langchain_mcp_adapters.client import MultiServerMCPClient
    from langchain_mcp_adapters.sessions import StdioConnection

    mcp_config: dict[str, StdioConnection] = {
        "umls": StdioConnection(
            command="uv",
            args=["run", "python", "-m", "umls_mcp_server.server"],
            transport="stdio",
        )
    }

    search_results: list[dict[str, Any]] = []

    mcp_client = MultiServerMCPClient(mcp_config)  # type: ignore[arg-type]
    tools = await mcp_client.get_tools()
    concept_search_tool = None
    for tool in tools:
        if tool.name == "concept_search":
            concept_search_tool = tool
            break

    if concept_search_tool is None:
        raise RuntimeError("concept_search tool not found on MCP server")

    for entity in entities:
        try:
            raw_result = await concept_search_tool.ainvoke(
                {"term": entity.search_term, "max_results": 5}
            )
            candidates = _normalize_search_results(raw_result)
            search_results.append(
                {
                    "entity_text": entity.text,
                    "entity_type": entity.entity_type,
                    "search_term": entity.search_term,
                    "candidates": candidates,
                }
            )
        except Exception as e:
            logger.warning("UMLS search failed for '%s': %s", entity.search_term, e)
            search_results.append(
                {
                    "entity_text": entity.text,
                    "entity_type": entity.entity_type,
                    "search_term": entity.search_term,
                    "candidates": [],
                }
            )

    return search_results


def _build_grounded_entities(
    extracted: list[ExtractedEntityAction],
    selections: list[GroundingSelection],
) -> list[dict[str, Any]]:
    """Build grounded entity dicts from MedGemma selections.

    Maps extracted entities to their selections by entity_text. Each entity
    carries its own criterion_id from the extract phase.
    """
    # Map selections by entity_text for lookup
    selection_map = {s.entity_text: s for s in selections}

    grounded: list[dict[str, Any]] = []
    for entity in extracted:
        selection = selection_map.get(entity.text)
        if selection:
            # Detect "NOT_MEDICAL_ENTITY" flag from MedGemma reasoning
            if selection.reasoning.startswith("NOT_MEDICAL_ENTITY:"):
                method = "not_medical_entity"
            else:
                method = "agentic_medgemma"
            grounded.append(
                {
                    "criteria_id": entity.criterion_id,
                    "text": selection.entity_text,
                    "entity_type": selection.entity_type,
                    "span_start": entity.span_start,
                    "span_end": entity.span_end,
                    "context_window": entity.context_window,
                    "umls_cui": selection.selected_cui,
                    "preferred_term": selection.preferred_term,
                    "snomed_code": selection.snomed_code,
                    "grounding_confidence": selection.confidence,
                    "grounding_method": method,
                }
            )
        else:
            grounded.append(
                {
                    "criteria_id": entity.criterion_id,
                    "text": entity.text,
                    "entity_type": entity.entity_type,
                    "span_start": entity.span_start,
                    "span_end": entity.span_end,
                    "context_window": entity.context_window,
                    "umls_cui": None,
                    "preferred_term": None,
                    "snomed_code": None,
                    "grounding_confidence": 0.0,
                    "grounding_method": "expert_review",
                }
            )

    return grounded


@vertex_ai_breaker
async def _invoke_medgemma(model: Any, system_prompt: str, user_prompt: str) -> str:
    """Invoke MedGemma and return raw text response."""
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]
    result = await model.ainvoke(messages)
    return result.content


def _fallback_entities_for_criteria(
    criteria_texts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build expert_review fallback entities when extraction fails."""
    fallback: list[dict[str, Any]] = []
    for ct in criteria_texts:
        fallback.append(
            {
                "criteria_id": ct["id"],
                "text": ct["text"],
                "entity_type": "Condition",
                "span_start": 0,
                "span_end": len(ct["text"]),
                "context_window": ct["text"][:40],
                "umls_cui": None,
                "preferred_term": None,
                "snomed_code": None,
                "grounding_confidence": 0.0,
                "grounding_method": "expert_review",
            }
        )
    return fallback


def _fallback_from_entities(
    entities: list[ExtractedEntityAction],
) -> list[dict[str, Any]]:
    """Build expert_review fallback from extracted entities."""
    return [
        {
            "criteria_id": e.criterion_id,
            "text": e.text,
            "entity_type": e.entity_type,
            "span_start": e.span_start,
            "span_end": e.span_end,
            "context_window": e.context_window,
            "umls_cui": None,
            "preferred_term": None,
            "snomed_code": None,
            "grounding_confidence": 0.0,
            "grounding_method": "expert_review",
        }
        for e in entities
    ]


async def _run_evaluate_loop(
    model: Any,
    system_prompt: str,
    entities: list[ExtractedEntityAction],
    iteration_history: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Run the UMLS search + MedGemma evaluate loop.

    Returns grounded entities list (empty if loop exhausts iterations).
    """
    current_entities = entities

    for iteration in range(MAX_ITERATIONS):
        search_results = await _search_umls_for_entities(current_entities)

        evaluate_prompt = _render_template(
            "agentic_evaluate.jinja2",
            search_results=search_results,
            iteration=iteration,
            max_iterations=MAX_ITERATIONS,
        )

        raw_response = await _invoke_medgemma(model, system_prompt, evaluate_prompt)

        try:
            parsed = _parse_json_response(raw_response)
            action = AgenticAction.model_validate(parsed)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning(
                "Failed to parse evaluate response (iter %d): %s",
                iteration,
                e,
            )
            iteration_history.append({"iteration": iteration + 1, "error": str(e)})
            break

        iteration_history.append(
            {
                "iteration": iteration + 1,
                "action_type": action.action_type,
                "selection_count": len(action.selections),
                "entity_count": len(action.entities),
            }
        )

        if action.action_type == "evaluate":
            return _build_grounded_entities(current_entities, action.selections)

        if action.action_type == "refine" and iteration < MAX_ITERATIONS - 1:
            current_entities = action.entities
            continue

        break

    return []


async def medgemma_ground_node(
    state: GroundingState,
) -> dict[str, Any]:
    """Agentic grounding node using MedGemma + UMLS MCP concept_search.

    Implements a programmatic agentic loop:
    1. MedGemma extracts entities and suggests UMLS search terms
    2. Code calls UMLS MCP concept_search for each entity
    3. MedGemma evaluates results and selects best matches
    4. If unsatisfied, MedGemma refines search terms (max 3 iterations)

    Args:
        state: Current grounding state with criteria_ids.

    Returns:
        Dict with criteria_texts and grounded_entities.
    """
    if state.get("error"):
        return {}

    try:
        criteria_texts = _load_criteria_texts(state["criteria_ids"])

        if not criteria_texts:
            logger.warning("No criteria found for batch %s", state.get("batch_id"))
            return {"criteria_texts": [], "grounded_entities": []}

        model = _get_medgemma_model()
        system_prompt = _render_template("agentic_system.jinja2")
        iteration_history: list[dict[str, Any]] = []

        # Step 1: Extract entities
        extract_prompt = _render_template(
            "agentic_extract.jinja2", criteria=criteria_texts
        )
        raw_response = await _invoke_medgemma(model, system_prompt, extract_prompt)

        try:
            parsed = _parse_json_response(raw_response)
            action = AgenticAction.model_validate(parsed)
        except (json.JSONDecodeError, Exception) as e:
            logger.warning("Failed to parse MedGemma extract response: %s", e)
            return {
                "criteria_texts": criteria_texts,
                "grounded_entities": _fallback_entities_for_criteria(criteria_texts),
                "iteration_history": [{"iteration": 0, "error": str(e)}],
            }

        iteration_history.append(
            {
                "iteration": 0,
                "action_type": action.action_type,
                "entity_count": len(action.entities),
            }
        )

        # Step 2-3: UMLS search + evaluate loop
        all_grounded = await _run_evaluate_loop(
            model, system_prompt, action.entities, iteration_history
        )

        # Fallback if loop completed without evaluate
        if not all_grounded:
            all_grounded = _fallback_from_entities(action.entities)

        logger.info(
            "Agentic grounding produced %d entities for batch %s (%d iterations)",
            len(all_grounded),
            state.get("batch_id"),
            len(iteration_history),
        )

        return {
            "criteria_texts": criteria_texts,
            "grounded_entities": all_grounded,
            "iteration_history": iteration_history,
        }

    except Exception as e:
        logger.exception(
            "Agentic grounding failed for batch %s: %s",
            state.get("batch_id", "unknown"),
            e,
        )
        return {"error": f"Agentic grounding failed: {e}"}
