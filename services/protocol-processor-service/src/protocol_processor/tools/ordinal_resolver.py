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

        prompt = (
            "You are a clinical terminology expert specializing in medical scoring "
            "systems and ordinal scales.\n\n"
            "For each entity below, determine if it is a clinical ordinal scoring "
            "system (e.g. ECOG, Karnofsky, NYHA, Child-Pugh, GCS, APACHE II, MELD, "
            "mRS, SOFA, etc.).\n\n"
            "An ordinal scoring system has these characteristics:\n"
            "- Uses discrete numeric grades/scores (not continuous measurements)\n"
            "- Each grade has a specific clinical meaning\n"
            "- The unit is conceptually {score}, not a physical unit\n"
            "- Common in clinical trials for performance status, organ function, "
            "disease severity\n\n"
            "NOT ordinal scales:\n"
            "- Lab values with physical units (mg/dL, g/L, IU/mL)\n"
            "- Continuous measurements (weight, height, BMI)\n"
            "- Binary yes/no conditions (HIV status, pregnancy)\n"
            "- Age, duration, or time-based criteria\n\n"
            f"Entities to evaluate:\n{entities_text}\n\n"
            "For each entity that IS an ordinal scale, propose:\n"
            "- scale_name: snake_case identifier for YAML config\n"
            "- entity_aliases: alternative names clinicians might use\n"
            "- loinc_code: LOINC code if known\n"
            "- values: list of grades with descriptions\n"
        )

        result = await structured_llm.ainvoke(prompt)
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
