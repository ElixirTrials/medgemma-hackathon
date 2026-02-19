"""FastAPI router for per-criterion AI re-run endpoint.

Provides a proposal-only endpoint for re-extracting a single criterion
using reviewer feedback as a correction prompt. NEVER writes to the database.
The reviewer must call POST /reviews/criteria/{id}/action with action=modify
to commit any changes.

Endpoints:
- POST /reviews/criteria/{criterion_id}/rerun: AI re-extraction with feedback
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from shared.models import Criteria
from sqlmodel import Session

from api_service.dependencies import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reviews", tags=["reviews"])

_AI_PARSE_ERROR = (
    "AI could not produce a valid structured result. Try rephrasing your feedback."
)


# --- Request/Response models ---


class SingleCriterionResult(BaseModel):
    """Structured output schema for a single re-extracted criterion.

    Mirrors one ExtractedCriterion from the extraction schema.
    Used as the response_schema for Gemini structured output.
    """

    criteria_type: Literal["inclusion", "exclusion"]
    category: str | None = None
    text: str
    temporal_constraint: Dict[str, Any] | None = None
    conditions: list[str] = []
    numeric_thresholds: list[Dict[str, Any]] = []
    assertion_status: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class CriterionRerunRequest(BaseModel):
    """Request body for the criterion re-run endpoint."""

    reviewer_feedback: str


class CriterionRerunResponse(BaseModel):
    """Response containing original and revised structured criterion fields."""

    original_criterion: Dict[str, Any]
    revised_criterion: Dict[str, Any]


# --- Endpoint ---


@router.post(
    "/criteria/{criterion_id}/rerun",
    response_model=CriterionRerunResponse,
)
async def rerun_criterion(
    criterion_id: str,
    body: CriterionRerunRequest,
    db: Session = Depends(get_db),
) -> CriterionRerunResponse:
    """Re-extract a single criterion using reviewer feedback as guidance.

    Sends the original criterion and reviewer feedback to Gemini and returns
    a structured revised extraction. This endpoint NEVER writes to the database.
    It returns a proposal only. The reviewer must call
    POST /reviews/criteria/{id}/action with action=modify to commit changes.

    Returns 404 if criterion not found.
    Returns 422 if Gemini cannot produce a valid structured result.
    """
    criterion = db.get(Criteria, criterion_id)
    if not criterion:
        raise HTTPException(
            status_code=404,
            detail=f"Criterion {criterion_id} not found",
        )

    # Capture original fields for response
    original_criterion = {
        "criteria_type": criterion.criteria_type,
        "category": criterion.category,
        "text": criterion.text,
        "temporal_constraint": criterion.temporal_constraint,
        "conditions": criterion.conditions,
        "numeric_thresholds": criterion.numeric_thresholds,
        "assertion_status": criterion.assertion_status,
        "confidence": criterion.confidence,
    }

    # Build prompt following research Pattern 3
    current_extraction = {
        "criteria_type": criterion.criteria_type,
        "category": criterion.category,
        "temporal_constraint": criterion.temporal_constraint,
        "conditions": criterion.conditions,
        "numeric_thresholds": criterion.numeric_thresholds,
    }

    prompt = f"""You are correcting a structured clinical trial criterion extraction.

Original criterion text: {criterion.text}
Current extraction: {json.dumps(current_extraction, indent=2)}

Reviewer feedback: {body.reviewer_feedback}

Re-extract this single criterion following the reviewer's correction guidance.
Return ONLY valid JSON with these fields:
- criteria_type: "inclusion" or "exclusion"
- category: string or null
- text: string (the criterion text)
- temporal_constraint: object or null (e.g. reference_point, offset)
- conditions: array of strings
- numeric_thresholds: array of objects (with fields like value, unit, comparator)
- assertion_status: string or null
- confidence: number between 0 and 1"""

    # Configure Gemini client (lazy import to avoid requiring package at test time)
    try:
        from google import genai  # noqa: PLC0415
        from google.genai import types  # noqa: PLC0415
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail="google-genai package not installed",
        ) from exc

    api_key = os.getenv("GOOGLE_API_KEY")
    model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.5-flash")

    client = genai.Client(api_key=api_key)

    try:
        response = await client.aio.models.generate_content(
            model=model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
            ),
        )
    except Exception as e:
        logger.error(
            "Gemini API error during criterion rerun for %s: %s",
            criterion_id,
            e,
        )
        raise HTTPException(status_code=422, detail=_AI_PARSE_ERROR) from e

    # Parse response — try .parsed first, fallback to model_validate_json
    revised: SingleCriterionResult | None = None
    try:
        if hasattr(response, "parsed") and response.parsed is not None:
            revised = response.parsed  # type: ignore[assignment]
        else:
            revised = SingleCriterionResult.model_validate_json(response.text)  # type: ignore[arg-type]
    except Exception as e:
        logger.warning(
            "Failed to parse Gemini response for criterion %s: %s",
            criterion_id,
            e,
        )
        raise HTTPException(status_code=422, detail=_AI_PARSE_ERROR) from e

    if revised is None:
        raise HTTPException(status_code=422, detail=_AI_PARSE_ERROR)

    return CriterionRerunResponse(
        original_criterion=original_criterion,
        revised_criterion=revised.model_dump(),
    )
