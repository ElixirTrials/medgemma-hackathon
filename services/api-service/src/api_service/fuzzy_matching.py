"""Fuzzy matching utilities for review inheritance on re-extraction.

When a protocol is re-extracted, new criteria are compared against reviewed
criteria from archived batches. If a new criterion text matches an old
reviewed criterion at >90% token_set_ratio AND has the same criteria_type
(inclusion/exclusion), the review decision is automatically inherited.

Key design decisions:
- Uses rapidfuzz.fuzz.token_set_ratio (NOT fuzz.ratio) to handle word order
  variations and subset matching in AI-generated text.
- MUST check criteria_type before comparing text to prevent false positives
  (e.g., "Age >= 18 years" inclusion vs "Age < 18 years" exclusion score 91.7%).
- Default threshold is 90.0 — configurable in code, not user-facing.
"""

from __future__ import annotations

import logging
from typing import Any

from rapidfuzz import fuzz

logger = logging.getLogger(__name__)


def find_matching_reviewed_criterion(
    new_text: str,
    new_criteria_type: str,
    old_criteria: list[dict[str, Any]],
    threshold: float = 90.0,
) -> dict[str, Any] | None:
    """Find the best matching reviewed criterion from archived batches.

    Uses token_set_ratio which handles:
    - Word order differences (e.g., "Age >= 18 years" vs "18 years or older")
    - Extra words (e.g., "Patient must be" prefix variations)
    - Minor wording changes from AI extraction variations between runs

    CRITICAL: criteria_type is checked before text comparison to prevent
    false positives between semantically opposite criteria (Pitfall 2 in
    RESEARCH.md: inclusion "Age >= 18" vs exclusion "Age < 18" scores 91.7%).

    Args:
        new_text: Criterion text from the new extraction run.
        new_criteria_type: Type of new criterion ("inclusion" or "exclusion").
        old_criteria: List of criterion dicts from archived batches.
            Each dict must have: id, text, criteria_type, review_status,
            reviewed_by (optional).
        threshold: Minimum similarity score (0-100). Default 90.0.

    Returns:
        Dict with criterion_id, review_status, reviewed_by, match_score
        if a match is found at or above threshold, else None.
    """
    best_match: dict[str, Any] | None = None
    best_score = 0.0

    for old_criterion in old_criteria:
        # CRITICAL: Skip if criteria_type differs — prevents false positives
        # between semantically opposite inclusion/exclusion criteria.
        if old_criterion.get("criteria_type") != new_criteria_type:
            logger.debug(
                "Skipping type mismatch: new=%s old=%s text=%.50s",
                new_criteria_type,
                old_criterion.get("criteria_type"),
                old_criterion.get("text", ""),
            )
            continue

        # Skip unreviewed criteria — only inherit reviewed decisions
        if not old_criterion.get("review_status"):
            continue

        old_text = old_criterion.get("text", "")
        score = fuzz.token_set_ratio(new_text, old_text)

        if score >= threshold and score > best_score:
            best_score = score
            best_match = old_criterion
            logger.info(
                "Fuzzy match found: score=%.1f new=%.50s old=%.50s",
                score,
                new_text,
                old_text,
            )
        else:
            logger.debug(
                "No match: score=%.1f (threshold=%.1f) new=%.50s old=%.50s",
                score,
                threshold,
                new_text,
                old_text,
            )

    if best_match is None:
        return None

    return {
        "criterion_id": best_match["id"],
        "review_status": best_match["review_status"],
        "reviewed_by": best_match.get("reviewed_by"),
        "match_score": best_score,
    }


def inherit_reviews_for_batch(
    new_criteria: list[dict[str, Any]],
    archived_criteria: list[dict[str, Any]],
    threshold: float = 90.0,
) -> list[dict[str, Any]]:
    """Apply fuzzy matching across all new criteria against archived reviewed criteria.

    Processes each new criterion independently, finding the best match from
    the archived criteria pool. Returns a list of inheritance results for
    criteria where a match was found.

    Args:
        new_criteria: List of new criterion dicts (must have id, text, criteria_type).
        archived_criteria: List of criterion dicts from archived batches.
            Only reviewed criteria (review_status not None) are eligible for matching.
        threshold: Minimum similarity score (0-100). Default 90.0.

    Returns:
        List of dicts with: new_criterion_id, old_criterion_id, review_status,
        reviewed_by, match_score. Only criteria with a match are included.
    """
    results: list[dict[str, Any]] = []
    matched = 0

    for new_criterion in new_criteria:
        new_text = new_criterion.get("text", "")
        new_type = new_criterion.get("criteria_type", "")

        match = find_matching_reviewed_criterion(
            new_text=new_text,
            new_criteria_type=new_type,
            old_criteria=archived_criteria,
            threshold=threshold,
        )

        if match is not None:
            matched += 1
            results.append(
                {
                    "new_criterion_id": new_criterion["id"],
                    "old_criterion_id": match["criterion_id"],
                    "review_status": match["review_status"],
                    "reviewed_by": match["reviewed_by"],
                    "match_score": match["match_score"],
                }
            )

    total = len(new_criteria)
    logger.info(
        "Review inheritance: matched %d/%d criteria (threshold=%.1f)",
        matched,
        total,
        threshold,
    )

    return results
