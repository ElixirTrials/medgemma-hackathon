"""FastAPI router for entity approval workflow.

Provides endpoints for:
- GET /entities/criteria/{criteria_id}: List entities for a criterion
- GET /entities/batch/{batch_id}: List entities for all criteria in a batch
- POST /entities/{entity_id}/action: Submit approve/reject/modify action
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from shared.models import AuditLog, Criteria, Entity, Review
from sqlmodel import Session, select

from api_service.dependencies import get_current_user, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/entities", tags=["entities"])


# --- Request/Response models ---


class EntityResponse(BaseModel):
    """Response model for a single entity."""

    id: str
    criteria_id: str
    entity_type: str
    text: str
    span_start: int | None
    span_end: int | None
    umls_cui: str | None
    snomed_code: str | None
    preferred_term: str | None
    grounding_confidence: float | None
    grounding_method: str | None
    review_status: str | None
    context_window: Dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


class EntityActionRequest(BaseModel):
    """Request body for entity approval action."""

    action: Literal["approve", "reject", "modify"]
    reviewer_id: str
    modified_umls_cui: str | None = None
    modified_snomed_code: str | None = None
    modified_preferred_term: str | None = None
    comment: str | None = None


# --- Endpoints ---


@router.get("/criteria/{criteria_id}", response_model=list[EntityResponse])
def list_entities_for_criteria(
    criteria_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> list[EntityResponse]:
    """List all entities for a criterion, sorted by span_start (reading order).

    Returns entities in the order they appear in the criterion text.
    """
    # Verify criterion exists
    criterion = db.get(Criteria, criteria_id)
    if not criterion:
        raise HTTPException(
            status_code=404,
            detail=f"Criterion {criteria_id} not found",
        )

    stmt = (
        select(Entity)
        .where(Entity.criteria_id == criteria_id)
        .order_by(Entity.span_start.asc())  # type: ignore[attr-defined]
    )
    entities = db.exec(stmt).all()

    return [_entity_to_response(e) for e in entities]


@router.get("/batch/{batch_id}", response_model=list[EntityResponse])
def list_entities_for_batch(
    batch_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> list[EntityResponse]:
    """List all entities for all criteria in a batch.

    Joins Entity to Criteria via criteria_id, filters by batch_id.
    Returns entities sorted by criteria_id then span_start.
    """
    # Build query joining Entity and Criteria
    stmt = (
        select(Entity)
        .join(Criteria, Entity.criteria_id == Criteria.id)
        .where(Criteria.batch_id == batch_id)
        .order_by(
            Entity.criteria_id.asc(),  # type: ignore[attr-defined]
            Entity.span_start.asc(),  # type: ignore[attr-defined]
        )
    )
    entities = db.exec(stmt).all()

    return [_entity_to_response(e) for e in entities]


@router.post("/{entity_id}/action", response_model=EntityResponse)
def submit_entity_action(
    entity_id: str,
    body: EntityActionRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> EntityResponse:
    """Submit an approve/reject/modify action for an entity.

    Updates Entity.review_status and creates Review + AuditLog records.
    """
    entity = db.get(Entity, entity_id)
    if not entity:
        raise HTTPException(
            status_code=404,
            detail=f"Entity {entity_id} not found",
        )

    # Apply action and capture before/after values
    before_value, after_value = _apply_entity_action(entity, body)
    db.add(entity)

    # Create Review record
    review = Review(
        reviewer_id=body.reviewer_id,
        target_type="entity",
        target_id=entity_id,
        action=body.action,
        before_value=before_value,
        after_value=after_value,
        comment=body.comment,
    )
    db.add(review)

    # Create AuditLog record
    audit_log = AuditLog(
        event_type="review_action",
        actor_id=body.reviewer_id,
        target_type="entity",
        target_id=entity_id,
        details={
            "action": body.action,
            "before_value": before_value,
            "after_value": after_value,
        },
    )
    db.add(audit_log)

    db.commit()
    db.refresh(entity)

    return _entity_to_response(entity)


# --- Helpers ---


def _entity_to_response(entity: Entity) -> EntityResponse:
    """Convert an Entity model to EntityResponse."""
    return EntityResponse(
        id=entity.id,
        criteria_id=entity.criteria_id,
        entity_type=entity.entity_type,
        text=entity.text,
        span_start=entity.span_start,
        span_end=entity.span_end,
        umls_cui=entity.umls_cui,
        snomed_code=entity.snomed_code,
        preferred_term=entity.preferred_term,
        grounding_confidence=entity.grounding_confidence,
        grounding_method=entity.grounding_method,
        review_status=entity.review_status,
        context_window=entity.context_window,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


def _apply_entity_action(
    entity: Entity,
    body: EntityActionRequest,
) -> tuple[Dict[str, Any], Dict[str, Any] | None]:
    """Apply a review action to an entity and return before/after values.

    Returns:
        Tuple of (before_value, after_value). after_value is None unless
        action is "modify".
    """
    before_value: Dict[str, Any] = {
        "umls_cui": entity.umls_cui,
        "snomed_code": entity.snomed_code,
        "preferred_term": entity.preferred_term,
    }
    after_value: Dict[str, Any] | None = None

    if body.action == "approve":
        entity.review_status = "approved"
    elif body.action == "reject":
        entity.review_status = "rejected"
    elif body.action == "modify":
        entity.review_status = "modified"
        if body.modified_umls_cui is not None:
            entity.umls_cui = body.modified_umls_cui
        if body.modified_snomed_code is not None:
            entity.snomed_code = body.modified_snomed_code
        if body.modified_preferred_term is not None:
            entity.preferred_term = body.modified_preferred_term
        after_value = {
            "umls_cui": entity.umls_cui,
            "snomed_code": entity.snomed_code,
            "preferred_term": entity.preferred_term,
        }

    return before_value, after_value
