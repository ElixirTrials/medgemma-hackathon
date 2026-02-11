"""Parse node: post-process extracted criteria with assertion refinement.

This node refines the raw criteria from the extract node:
1. Assertion refinement: detect negation/conditionality markers
2. Confidence calibration: adjust scores for unusual patterns
3. Deduplication: remove near-duplicate criteria

This node does NOT call any LLM -- it is pure Python post-processing.
"""

from __future__ import annotations

import logging
from typing import Any

from agent_a_service.state import ExtractionState

logger = logging.getLogger(__name__)

# Negation markers that indicate ABSENT assertion status
_NEGATION_MARKERS = (
    "no history of",
    "without",
    "absence of",
    "not have",
    "free of",
    "no evidence of",
    "no prior",
    "must not",
    "has not",
    "never had",
)

# Conditionality markers that indicate CONDITIONAL assertion status
_CONDITIONALITY_MARKERS = (
    "if ",
    "in case of",
    "when applicable",
    "for patients who",
    "provided that",
    "unless",
)


def _normalize_text(text: str) -> str:
    """Normalize criterion text for comparison."""
    return text.lower().strip()


def _refine_assertion(criterion: dict[str, Any]) -> dict[str, Any]:
    """Refine assertion status based on negation and conditionality markers.

    If the criterion text contains negation markers and assertion_status
    is PRESENT, override to ABSENT. Similarly for conditionality markers
    and CONDITIONAL.

    Args:
        criterion: Raw criterion dict with text and assertion_status.

    Returns:
        Updated criterion dict with refined assertion_status.
    """
    text_lower = criterion.get("text", "").lower()
    status = criterion.get("assertion_status", "PRESENT")

    # Only refine if status is PRESENT (avoid overriding correct LLM output)
    if status == "PRESENT":
        # Check for negation markers
        for marker in _NEGATION_MARKERS:
            if marker in text_lower:
                criterion["assertion_status"] = "ABSENT"
                logger.debug(
                    "Refined assertion to ABSENT (negation marker '%s'): %s",
                    marker,
                    criterion.get("text", "")[:80],
                )
                break

        # Check for conditionality markers (only if not already changed)
        if criterion.get("assertion_status") == "PRESENT":
            for marker in _CONDITIONALITY_MARKERS:
                if marker in text_lower:
                    criterion["assertion_status"] = "CONDITIONAL"
                    logger.debug(
                        "Refined assertion to CONDITIONAL (marker '%s'): %s",
                        marker,
                        criterion.get("text", "")[:80],
                    )
                    break

    return criterion


def _calibrate_confidence(criterion: dict[str, Any]) -> dict[str, Any]:
    """Calibrate confidence score based on unusual patterns.

    Lowers confidence for:
    - Inclusion criteria with ABSENT status (unusual, may be misclassified)
    - Very short text (<10 chars, likely incomplete extraction)

    Args:
        criterion: Criterion dict with confidence, criteria_type, etc.

    Returns:
        Updated criterion dict with calibrated confidence.
    """
    confidence = criterion.get("confidence", 1.0)

    # Unusual: inclusion + ABSENT (may be misclassified)
    if (
        criterion.get("criteria_type") == "inclusion"
        and criterion.get("assertion_status") == "ABSENT"
    ):
        confidence -= 0.1

    # Very short text is suspicious
    text = criterion.get("text", "")
    if len(text) < 10:
        confidence -= 0.2

    # Clamp to [0.0, 1.0]
    criterion["confidence"] = max(0.0, min(1.0, confidence))
    return criterion


def _deduplicate(criteria: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove near-duplicate criteria, keeping higher confidence entries.

    Uses simple normalized text comparison. If two criteria have identical
    normalized text, the one with higher confidence is kept.

    Args:
        criteria: List of criterion dicts.

    Returns:
        Deduplicated list of criterion dicts.
    """
    seen: dict[str, dict[str, Any]] = {}

    for criterion in criteria:
        normalized = _normalize_text(criterion.get("text", ""))
        if not normalized:
            continue

        if normalized in seen:
            # Keep the one with higher confidence
            existing_confidence = seen[normalized].get("confidence", 0.0)
            new_confidence = criterion.get("confidence", 0.0)
            if new_confidence > existing_confidence:
                seen[normalized] = criterion
        else:
            seen[normalized] = criterion

    return list(seen.values())


async def parse_node(state: ExtractionState) -> dict[str, Any]:
    """Post-process extracted criteria with assertion refinement.

    Applies:
    1. Assertion refinement (negation/conditionality marker detection)
    2. Confidence calibration (unusual pattern adjustments)
    3. Deduplication (remove near-duplicate criteria)

    Args:
        state: Current extraction state with raw_criteria from extract node.

    Returns:
        Dict with refined raw_criteria list.
    """
    if state.get("error"):
        return {}

    raw_criteria = state.get("raw_criteria", [])
    logger.info(
        "Parsing %d raw criteria for protocol %s",
        len(raw_criteria),
        state.get("protocol_id", "unknown"),
    )

    # Step 1: Assertion refinement
    refined = [_refine_assertion(dict(c)) for c in raw_criteria]

    # Step 2: Confidence calibration
    refined = [_calibrate_confidence(c) for c in refined]

    # Step 3: Deduplication
    refined = _deduplicate(refined)

    logger.info(
        "Parse complete: %d -> %d criteria (after dedup) for protocol %s",
        len(raw_criteria),
        len(refined),
        state.get("protocol_id", "unknown"),
    )

    return {"raw_criteria": refined}
