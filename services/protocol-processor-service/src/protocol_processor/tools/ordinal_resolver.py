"""Ordinal scale resolution tool using Gemini structured output.

Identifies unrecognized clinical ordinal scoring systems (Child-Pugh, GCS,
APACHE II, MELD, mRS, SOFA, etc.) and proposes YAML config entries for
human review.

Follows the detect_logic_structure() pattern from structure_builder.py:
- Guard on GOOGLE_API_KEY
- Late import of ChatGoogleGenerativeAI
- with_structured_output() for typed LLM response
- Return None on any failure (graceful degradation)
"""

from __future__ import annotations

import logging
from typing import Any

from protocol_processor.prompts import render_template
from protocol_processor.schemas.ordinal import (
    OrdinalResolutionResponse,
    OrdinalScaleProposal,
)
from protocol_processor.tools.gemini_utils import (
    create_structured_llm,
    parse_structured_output,
)

logger = logging.getLogger(__name__)


async def resolve_ordinal_candidates(
    candidates: list[dict[str, Any]],
) -> OrdinalResolutionResponse | None:
    """Send candidate entities to Gemini for ordinal scale identification.

    Args:
        candidates: List of dicts with keys 'entity_text', 'value_numeric',
            'relation_operator' from AtomicCriterion records.

    Returns:
        OrdinalResolutionResponse with proposals, or None on failure/skip.
    """
    if not candidates:
        return None

    structured_llm = create_structured_llm(OrdinalResolutionResponse)
    if structured_llm is None:
        return None

    try:
        # Build indexed entity list for the prompt
        entity_lines = []
        for i, c in enumerate(candidates):
            entity = c.get("entity_text", "?")
            value = c.get("value_numeric", "?")
            relation = c.get("relation_operator", "?")
            entity_lines.append(
                f'  [{i}] entity="{entity}" relation="{relation}" value={value}'
            )
        entities_text = "\n".join(entity_lines)

        prompt = render_template(
            "ordinal_resolution.jinja2", entities_text=entities_text
        )

        from protocol_processor.tracing import llm_span

        with llm_span("gemini_ordinal_resolution") as llm:
            llm.set_request(prompt)
            result = await structured_llm.ainvoke(prompt)
            llm.set_response(str(result))

        response = parse_structured_output(result, OrdinalResolutionResponse)

        # Filter to confirmed ordinals with sufficient confidence
        confirmed: list[OrdinalScaleProposal] = [
            p for p in response.proposals if p.is_ordinal_scale and p.confidence >= 0.7
        ]

        return OrdinalResolutionResponse(proposals=confirmed)

    except Exception as e:
        logger.warning(
            "Ordinal resolution failed: %s",
            e,
            exc_info=True,
        )
        return None
