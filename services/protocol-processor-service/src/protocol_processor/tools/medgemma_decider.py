"""MedGemma decision tool for best-match selection from TerminologyRouter candidates.

Per user decision: "MedGemma acts as decision-maker, minimum token usage."
MedGemma evaluates candidates returned by TerminologyRouter and selects the best
match for each entity. Uses the two-model architecture: MedGemma for medical
reasoning, Gemini for structured output parsing.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from protocol_processor.tools.terminology_router import TerminologyRouter

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from protocol_processor.prompts import render_template
from protocol_processor.schemas.grounding import (
    EntityGroundingResult,
    GroundingCandidate,
)
from protocol_processor.tools.gemini_utils import (
    create_structured_llm,
    parse_structured_output,
)

logger = logging.getLogger(__name__)

_model_loader = None


class AgenticReasoningResult(BaseModel):
    """MedGemma's 3-question reasoning output for failed grounding retry.

    Used by agentic_reasoning_loop to determine whether to skip an entity,
    apply derived entity mapping, or rephrase the query for a better search.

    Attributes:
        should_skip: True if entity is not a valid medical criterion.
        is_derived: True if entity maps to a more standard medical concept.
        derived_term: Standard concept term if is_derived is True.
        rephrased_query: Rephrased medical terminology query if applicable.
        gemini_suggestion: Optional additional reformulation from Gemini.
        reasoning: Brief explanation of the reasoning decisions.
    """

    should_skip: bool = Field(
        default=False,
        description=(
            "True if entity is not a valid medical criterion "
            "(e.g., consent, participation, willingness)"
        ),
    )
    is_derived: bool = Field(
        default=False,
        description="True if entity maps to a more standard medical concept",
    )
    derived_term: str | None = Field(
        default=None,
        description=(
            "Standard concept term if is_derived is True "
            "(e.g., 'age' for 'age >= 18 years')"
        ),
    )
    rephrased_query: str | None = Field(
        default=None,
        description=(
            "Rephrased medical terminology query for better search "
            "(e.g., 'hypertension' for 'high blood pressure')"
        ),
    )
    gemini_suggestion: str | None = Field(
        default=None,
        description=("Optional reformulation suggestion from Gemini structuring step"),
    )
    reasoning: str = Field(
        default="",
        description="Brief explanation of the three-question reasoning",
    )


class GroundingDecision(BaseModel):
    """MedGemma's decision for the best terminology match."""

    selected_code: str | None = Field(
        default=None,
        description=(
            "Selected terminology code (CUI for UMLS, SNOMED code, etc)."
            " Null if no good match."
        ),
    )
    selected_system: str | None = Field(
        default=None,
        description=(
            "The API/system that produced the selected code (e.g. 'umls', 'snomed')."
        ),
    )
    preferred_term: str | None = Field(
        default=None,
        description="Canonical preferred term for the selected code.",
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Confidence score 0.0-1.0."
            " 0.9-1.0=exact, 0.7-0.8=synonym, 0.5-0.6=partial, 0.0=no match."
        ),
    )
    reasoning: str = Field(
        default="",
        description="Brief explanation for selection.",
    )


def _get_medgemma_model() -> Any:
    """Get or create MedGemma model instance."""
    global _model_loader  # noqa: PLW0603
    if _model_loader is None:
        from inference.config import AgentConfig
        from inference.model_garden import create_model_loader

        _model_loader = create_model_loader(AgentConfig.from_env())
    return _model_loader()


async def _structure_decision_with_gemini(raw_text: str) -> GroundingDecision:
    """Structure raw MedGemma output using Gemini with_structured_output.

    Args:
        raw_text: Raw MedGemma output (free-form medical reasoning).

    Returns:
        GroundingDecision with selected code and confidence.
    """
    structured_llm = create_structured_llm(GroundingDecision)
    if structured_llm is None:
        raise ValueError(
            "No LLM backend available (GOOGLE_API_KEY or OLLAMA_BASE_URL required)"
        )

    from protocol_processor.tracing import llm_span

    prompt = render_template("structure_decision.jinja2", raw_text=raw_text)

    gemini_model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
    with llm_span("gemini_structure_decision", gemini_model_name) as llm:
        llm.set_request(prompt)
        result = await structured_llm.ainvoke(prompt)
        llm.set_response(str(result))

    return parse_structured_output(result, GroundingDecision)


async def medgemma_decide(
    entity: dict[str, Any],
    candidates: list[GroundingCandidate],
    criterion_context: str,
) -> EntityGroundingResult:
    """Use MedGemma to select the best terminology match for an entity.

    MedGemma evaluates the candidates returned by TerminologyRouter and
    selects the most appropriate code for the entity. Returns a result with
    confidence=0.0 and no code if no candidates are available or none are
    appropriate.

    Args:
        entity: Entity dict with keys: text, entity_type, criterion_id.
        candidates: List of GroundingCandidate objects from TerminologyRouter.
        criterion_context: The full criterion text for context.

    Returns:
        EntityGroundingResult with the selected code, confidence, and reasoning.
    """
    entity_text = entity.get("text", "")
    entity_type = entity.get("entity_type", "")
    criterion_id = entity.get("criterion_id", "")

    # If no candidates, return result with confidence=0.0
    if not candidates:
        logger.info(
            "No candidates for entity '%s' (type=%s, criterion=%s)"
            " — returning empty grounding",
            entity_text[:50],
            entity_type,
            criterion_id[:12],
        )
        return EntityGroundingResult(
            entity_text=entity_text,
            entity_type=entity_type,
            selected_code=None,
            selected_system=None,
            preferred_term=None,
            confidence=0.0,
            candidates=[],
            reasoning="No terminology candidates available from any API",
        )

    try:
        model = _get_medgemma_model()

        system_prompt = render_template("grounding_system.jinja2")
        evaluate_prompt = render_template(
            "grounding_evaluate.jinja2",
            entity_text=entity_text,
            entity_type=entity_type,
            criterion_context=criterion_context,
            candidates=candidates,
        )

        from protocol_processor.tracing import llm_span

        model_name = getattr(model, "model_name", "") or getattr(model, "model", "")
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=evaluate_prompt),
        ]

        with llm_span("medgemma_evaluate", str(model_name)) as llm:
            llm.set_request(f"[system] {system_prompt}\n\n[user] {evaluate_prompt}")
            raw_response = await model.ainvoke(messages)
            raw_text = raw_response.content
            usage: dict[str, int] = {}
            um = getattr(raw_response, "usage_metadata", None)
            if isinstance(um, dict):
                if um.get("input_tokens"):
                    usage["input_tokens"] = um["input_tokens"]
                if um.get("output_tokens"):
                    usage["output_tokens"] = um["output_tokens"]
                if um.get("total_tokens"):
                    usage["total_tokens"] = um["total_tokens"]
            llm.set_response(str(raw_text), usage or None)

        logger.debug(
            "MedGemma evaluate response for '%s' (first 200 chars): %s",
            entity_text[:30],
            raw_text[:200],
        )

        decision = await _structure_decision_with_gemini(raw_text)

        logger.info(
            "Grounding decision for '%s': code=%s, system=%s, conf=%.2f",
            entity_text[:50],
            decision.selected_code,
            decision.selected_system,
            decision.confidence,
        )

        return EntityGroundingResult(
            entity_text=entity_text,
            entity_type=entity_type,
            selected_code=decision.selected_code,
            selected_system=decision.selected_system,
            preferred_term=decision.preferred_term,
            confidence=decision.confidence,
            candidates=candidates,
            reasoning=decision.reasoning,
        )

    except Exception as e:
        logger.error(
            "MedGemma decision failed for entity '%s': %s",
            entity_text[:50],
            e,
            exc_info=True,
        )
        return EntityGroundingResult(
            entity_text=entity_text,
            entity_type=entity_type,
            selected_code=None,
            selected_system=None,
            preferred_term=None,
            confidence=0.0,
            candidates=candidates,
            reasoning=f"MedGemma decision failed: {e}",
        )


async def _structure_reasoning_with_gemini(raw_text: str) -> AgenticReasoningResult:
    """Structure raw MedGemma reasoning output using Gemini with_structured_output.

    Gemini also acts as a collaborating agent here — it can add its own
    reformulation suggestions via the gemini_suggestion field when structuring
    the output.

    Args:
        raw_text: Raw MedGemma reasoning output (free-form text).

    Returns:
        AgenticReasoningResult with structured 3-question answers.
    """
    structured_llm = create_structured_llm(AgenticReasoningResult)
    if structured_llm is None:
        raise ValueError(
            "No LLM backend available (GOOGLE_API_KEY or OLLAMA_BASE_URL required)"
        )

    from protocol_processor.tracing import llm_span

    prompt = render_template("structure_reasoning.jinja2", raw_text=raw_text)

    gemini_model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")
    with llm_span("gemini_structure_reasoning", gemini_model_name) as llm:
        llm.set_request(prompt)
        result = await structured_llm.ainvoke(prompt)
        llm.set_response(str(result))

    return parse_structured_output(result, AgenticReasoningResult)


async def agentic_reasoning_loop(
    entity: dict[str, Any],
    criterion_context: str,
    router: "TerminologyRouter",
    attempt: int = 1,
) -> AgenticReasoningResult:
    """Ask MedGemma 3 reasoning questions to determine retry strategy.

    Called by ground_node when an entity fails initial grounding (zero
    candidates or confidence < 0.5). Asks MedGemma in a single prompt:
    - Q1: Is this a valid medical criterion (or should it be skipped)?
    - Q2: Is this a derived entity that maps to a standard concept?
    - Q3: Can this entity be rephrased for better terminology search?

    Uses the two-model architecture: MedGemma for medical reasoning, Gemini
    for structured output parsing (and optional reformulation suggestion).

    Args:
        entity: Entity dict with keys: text, entity_type, criterion_id.
        criterion_context: The full criterion text for context.
        router: TerminologyRouter instance (for get_apis_for_entity context).
        attempt: Current attempt number (1-3) for prompt context.

    Returns:
        AgenticReasoningResult with should_skip, is_derived, derived_term,
        rephrased_query, gemini_suggestion, and reasoning fields.
        On error, returns default result (no skip, no rephrase) to allow
        the retry loop to continue with the original query.
    """
    entity_text = entity.get("text", "")
    entity_type = entity.get("entity_type", "")
    previous_query = entity.get("_previous_query", entity_text)

    logger.info(
        "Agentic reasoning (attempt %d) for entity '%s' (type=%s)",
        attempt,
        entity_text[:50],
        entity_type,
    )

    try:
        model = _get_medgemma_model()

        system_prompt = render_template("grounding_system.jinja2")
        reasoning_prompt = render_template(
            "grounding_reasoning.jinja2",
            entity_text=entity_text,
            entity_type=entity_type,
            criterion_context=criterion_context,
            previous_query=previous_query,
            attempt=attempt,
        )

        from protocol_processor.tracing import llm_span

        model_name = getattr(model, "model_name", "") or getattr(model, "model", "")
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=reasoning_prompt),
        ]

        with llm_span("medgemma_reasoning", str(model_name)) as llm:
            llm.set_request(f"[system] {system_prompt}\n\n[user] {reasoning_prompt}")
            raw_response = await model.ainvoke(messages)
            raw_text = raw_response.content
            usage_r: dict[str, int] = {}
            um_r = getattr(raw_response, "usage_metadata", None)
            if isinstance(um_r, dict):
                if um_r.get("input_tokens"):
                    usage_r["input_tokens"] = um_r["input_tokens"]
                if um_r.get("output_tokens"):
                    usage_r["output_tokens"] = um_r["output_tokens"]
                if um_r.get("total_tokens"):
                    usage_r["total_tokens"] = um_r["total_tokens"]
            llm.set_response(str(raw_text), usage_r or None)

        logger.debug(
            "MedGemma reasoning response for '%s' (first 300 chars): %s",
            entity_text[:30],
            raw_text[:300],
        )

        result = await _structure_reasoning_with_gemini(raw_text)

        logger.info(
            "Agentic reasoning result for '%s': skip=%s, derived=%s, "
            "derived_term=%s, rephrased=%s",
            entity_text[:50],
            result.should_skip,
            result.is_derived,
            result.derived_term,
            result.rephrased_query,
        )

        return result

    except Exception as e:
        logger.error(
            "Agentic reasoning loop failed for entity '%s': %s",
            entity_text[:50],
            e,
            exc_info=True,
        )
        # Return default result (no skip, no rephrase) — retry with original query
        return AgenticReasoningResult(
            should_skip=False,
            is_derived=False,
            derived_term=None,
            rephrased_query=None,
            reasoning=f"Reasoning loop failed: {e}",
        )
