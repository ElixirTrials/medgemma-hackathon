"""MedGemma decision tool for best-match selection from TerminologyRouter candidates.

Per user decision: "MedGemma acts as decision-maker, minimum token usage."
MedGemma evaluates candidates returned by TerminologyRouter and selects the best
match for each entity. Uses the two-model architecture: MedGemma for medical
reasoning, Gemini for structured output parsing.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from protocol_processor.schemas.grounding import (
    EntityGroundingResult,
    GroundingCandidate,
)

logger = logging.getLogger(__name__)

_model_loader = None
_PROMPTS_DIR = None


def _get_prompts_dir():
    from pathlib import Path
    return Path(__file__).parent.parent / "prompts"


def _render_template(template_name: str, **kwargs: Any) -> str:
    """Render a Jinja2 template from the prompts directory."""
    from jinja2 import Environment, FileSystemLoader

    prompts_dir = _get_prompts_dir()
    env = Environment(loader=FileSystemLoader(str(prompts_dir)), autoescape=False)
    template = env.get_template(template_name)
    return template.render(**kwargs)


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
            "The API/system that produced the selected code"
            " (e.g. 'umls', 'snomed')."
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


def _structure_decision_with_gemini(raw_text: str) -> GroundingDecision:
    """Structure raw MedGemma output using Gemini with_structured_output.

    Args:
        raw_text: Raw MedGemma output (free-form medical reasoning).

    Returns:
        GroundingDecision with selected code and confidence.
    """
    gemini_model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.0-flash")
    google_api_key = os.getenv("GOOGLE_API_KEY")

    if not google_api_key:
        raise ValueError("GOOGLE_API_KEY environment variable is required")

    gemini = ChatGoogleGenerativeAI(
        model=gemini_model_name,
        google_api_key=google_api_key,
    )
    structured_llm = gemini.with_structured_output(GroundingDecision)

    prompt = (
        "Extract the grounding decision from this medical terminology analysis."
        " Return the selected code, system, preferred term, confidence,"
        f" and reasoning.\n\n{raw_text}"
    )

    result = structured_llm.invoke(prompt)
    if isinstance(result, dict):
        return GroundingDecision.model_validate(result)
    return result  # type: ignore[return-value]


async def medgemma_decide(
    entity: dict,
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

        system_prompt = _render_template("grounding_system.jinja2")
        evaluate_prompt = _render_template(
            "grounding_evaluate.jinja2",
            entity_text=entity_text,
            entity_type=entity_type,
            criterion_context=criterion_context,
            candidates=candidates,
        )

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=evaluate_prompt),
        ]
        raw_response = await model.ainvoke(messages)
        raw_text = raw_response.content

        logger.debug(
            "MedGemma evaluate response for '%s' (first 200 chars): %s",
            entity_text[:30],
            raw_text[:200],
        )

        decision = _structure_decision_with_gemini(raw_text)

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
        # Return zero-confidence result on error so error accumulation continues
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
