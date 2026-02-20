"""FastAPI router for batch comparison endpoint.

Compares criteria between two extraction batches using fuzzy matching to
classify each criterion as added, removed, changed, or unchanged.

Key thresholds (distinct from the 90% inheritance threshold in fuzzy_matching.py):
- >= 90.0: unchanged (text is essentially identical)
- >= 70.0 and < 90.0: changed (same criterion, wording differs)
- < 70.0: removed from batch A / added in batch B

Endpoints:
- GET /reviews/batch-compare: Fuzzy-matched criterion diff between two batches
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from rapidfuzz import fuzz
from shared.models import Criteria, CriteriaBatch
from sqlmodel import Session, select

from api_service.dependencies import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reviews", tags=["reviews"])

# Comparison thresholds — DISTINCT from the 90% inheritance threshold.
# These thresholds are used only for batch-to-batch diff display.
UNCHANGED_THRESHOLD = 90.0
CHANGED_THRESHOLD = 70.0

# Type alias for compare row status values
CompareStatus = Literal["added", "removed", "changed", "unchanged"]


# --- Request/Response models ---


class CriterionCompareRow(BaseModel):
    """A single criterion alignment row in the batch comparison result."""

    status: CompareStatus
    batch_a_criterion: Dict[str, Any] | None
    batch_b_criterion: Dict[str, Any] | None
    match_score: float | None


class BatchCompareResponse(BaseModel):
    """Response for the batch comparison endpoint."""

    batch_a_id: str
    batch_b_id: str
    added: int
    removed: int
    changed: int
    unchanged: int
    rows: list[CriterionCompareRow]


# --- Helpers ---


def _criterion_dict(c: Criteria) -> Dict[str, Any]:
    """Convert a Criteria row to a compact comparison dict."""
    return {
        "id": c.id,
        "text": c.text,
        "criteria_type": c.criteria_type,
        "review_status": c.review_status,
        "category": c.category,
    }


def _find_best_match(
    crit_a: Criteria,
    b_items: list[Dict[str, Any]],
) -> tuple[int | None, float]:
    """Find the best unmatched criterion in batch B for a given batch A criterion.

    Checks criteria_type match first to prevent false positives between
    semantically opposite inclusion/exclusion criteria.

    Returns:
        Tuple of (best_b_idx, best_score). best_b_idx is None if no same-type
        criterion exists in batch B.
    """
    best_score = 0.0
    best_b_idx: int | None = None

    for idx, b_item in enumerate(b_items):
        if b_item["matched"]:
            continue

        crit_b: Criteria = b_item["criterion"]

        # CRITICAL: criteria_type must match before text comparison.
        # Prevents false positives between semantically opposite criteria
        # (e.g., "Age >= 18 inclusion" vs "Age < 18 exclusion" scores ~92%).
        if crit_b.criteria_type != crit_a.criteria_type:
            continue

        score = float(fuzz.token_set_ratio(crit_a.text, crit_b.text))

        if score > best_score:
            best_score = score
            best_b_idx = idx

    return best_b_idx, best_score


# --- Endpoint ---


@router.get("/batch-compare", response_model=BatchCompareResponse)
def compare_batches(
    batch_a: str = Query(..., description="ID of the reference batch (older)"),
    batch_b: str = Query(..., description="ID of the comparison batch (newer)"),
    db: Session = Depends(get_db),
) -> BatchCompareResponse:
    """Compare criteria between two extraction batches.

    Uses fuzzy matching (token_set_ratio) to align criteria between the two
    batches. Criteria type is checked before text comparison to prevent false
    positives between semantically opposite inclusion/exclusion criteria.

    Thresholds:
    - match_score >= 90.0 -> unchanged
    - 70.0 <= match_score < 90.0 -> changed
    - match_score < 70.0 -> removed (from batch A) or added (from batch B)

    Returns 404 if either batch doesn't exist.
    """
    # Verify both batches exist
    if not db.get(CriteriaBatch, batch_a):
        raise HTTPException(status_code=404, detail=f"Batch {batch_a} not found")
    if not db.get(CriteriaBatch, batch_b):
        raise HTTPException(status_code=404, detail=f"Batch {batch_b} not found")

    # Load all criteria for both batches
    criteria_a = db.exec(select(Criteria).where(Criteria.batch_id == batch_a)).all()
    criteria_b = db.exec(select(Criteria).where(Criteria.batch_id == batch_b)).all()

    # Build mutable tracking list for batch B
    b_items = [{"criterion": c, "matched": False} for c in criteria_b]

    rows: list[CriterionCompareRow] = []
    added_count = 0
    removed_count = 0
    changed_count = 0
    unchanged_count = 0

    # For each criterion in batch A, find the best match in batch B
    for crit_a in criteria_a:
        best_b_idx, best_score = _find_best_match(crit_a, b_items)

        if best_b_idx is not None and best_score >= CHANGED_THRESHOLD:
            b_items[best_b_idx]["matched"] = True
            matched_b = cast(Criteria, b_items[best_b_idx]["criterion"])

            if best_score >= UNCHANGED_THRESHOLD:
                status: CompareStatus = "unchanged"
                unchanged_count += 1
            else:
                status = "changed"
                changed_count += 1

            rows.append(
                CriterionCompareRow(
                    status=status,
                    batch_a_criterion=_criterion_dict(crit_a),
                    batch_b_criterion=_criterion_dict(matched_b),
                    match_score=best_score,
                )
            )
        else:
            # No match found in batch B — criterion was removed
            removed_count += 1
            rows.append(
                CriterionCompareRow(
                    status="removed",
                    batch_a_criterion=_criterion_dict(crit_a),
                    batch_b_criterion=None,
                    match_score=best_score if best_b_idx is not None else None,
                )
            )

    # Unmatched batch B criteria are new additions
    for b_item in b_items:
        if not b_item["matched"]:
            added_count += 1
            rows.append(
                CriterionCompareRow(
                    status="added",
                    batch_a_criterion=None,
                    batch_b_criterion=_criterion_dict(
                        cast(Criteria, b_item["criterion"])
                    ),
                    match_score=None,
                )
            )

    logger.info(
        "Batch comparison %s vs %s: added=%d removed=%d changed=%d unchanged=%d",
        batch_a,
        batch_b,
        added_count,
        removed_count,
        changed_count,
        unchanged_count,
    )

    return BatchCompareResponse(
        batch_a_id=batch_a,
        batch_b_id=batch_b,
        added=added_count,
        removed=removed_count,
        changed=changed_count,
        unchanged=unchanged_count,
        rows=rows,
    )
