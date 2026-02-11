"""FastAPI router for criteria review workflow.

Provides endpoints for:
- GET /reviews/batches: Paginated batch list with protocol info and progress
- GET /reviews/batches/{batch_id}/criteria: All criteria for a batch
- POST /reviews/criteria/{criteria_id}/action: Submit approve/reject/modify action
- GET /reviews/protocols/{protocol_id}/pdf-url: Signed download URL for protocol PDF
- GET /reviews/audit-log: Paginated audit log with optional filters
"""

from __future__ import annotations

import logging
from datetime import datetime
from math import ceil
from typing import Any, Dict, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from shared.models import AuditLog, Criteria, CriteriaBatch, Protocol, Review
from sqlmodel import Session, col, func, select

from api_service.dependencies import get_db
from api_service.gcs import generate_download_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reviews", tags=["reviews"])


# --- Request/Response models ---


class BatchResponse(BaseModel):
    """Response model for a single criteria batch."""

    id: str
    protocol_id: str
    protocol_title: str
    status: str
    extraction_model: str | None
    criteria_count: int
    reviewed_count: int
    created_at: datetime
    updated_at: datetime


class BatchListResponse(BaseModel):
    """Paginated list of criteria batches."""

    items: list[BatchResponse]
    total: int
    page: int
    page_size: int
    pages: int


class CriterionResponse(BaseModel):
    """Response model for a single criterion."""

    id: str
    batch_id: str
    criteria_type: str
    category: str | None
    text: str
    temporal_constraint: Dict[str, Any] | None
    conditions: Dict[str, Any] | None
    numeric_thresholds: Dict[str, Any] | None
    assertion_status: str | None
    confidence: float
    source_section: str | None
    review_status: str | None
    created_at: datetime
    updated_at: datetime


class ReviewActionRequest(BaseModel):
    """Request body for submitting a review action."""

    action: Literal["approve", "reject", "modify"]
    reviewer_id: str
    modified_text: str | None = None
    modified_type: str | None = None
    modified_category: str | None = None
    comment: str | None = None


class PdfUrlResponse(BaseModel):
    """Response with signed PDF download URL."""

    url: str
    expires_in_minutes: int


class AuditLogResponse(BaseModel):
    """Response model for a single audit log entry."""

    id: str
    event_type: str
    actor_id: str | None
    target_type: str | None
    target_id: str | None
    details: Dict[str, Any]
    created_at: datetime


class AuditLogListResponse(BaseModel):
    """Paginated list of audit log entries."""

    items: list[AuditLogResponse]
    total: int
    page: int
    page_size: int
    pages: int


# --- Endpoints ---


@router.get("/batches", response_model=BatchListResponse)
def list_batches(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> BatchListResponse:
    """List criteria batches with pagination, protocol info, and review progress.

    Returns batches ordered by creation date (newest first) with:
    - Protocol title from joined Protocol table
    - Count of linked criteria per batch
    - Count of reviewed criteria (review_status IS NOT NULL) for progress
    """
    # Build count query
    count_stmt = select(func.count()).select_from(CriteriaBatch)
    if status:
        count_stmt = count_stmt.where(CriteriaBatch.status == status)
    total = db.exec(count_stmt).one()

    # Build data query
    data_stmt = select(CriteriaBatch)
    if status:
        data_stmt = data_stmt.where(CriteriaBatch.status == status)
    data_stmt = (
        data_stmt.offset((page - 1) * page_size)
        .limit(page_size)
        .order_by(col(CriteriaBatch.created_at).desc())
    )

    batches = db.exec(data_stmt).all()
    pages = ceil(total / page_size) if total > 0 else 1

    items: list[BatchResponse] = []
    for batch in batches:
        # Get protocol title
        protocol = db.get(Protocol, batch.protocol_id)
        protocol_title = protocol.title if protocol else "Unknown"

        # Count total criteria in batch
        criteria_count_stmt = (
            select(func.count())
            .select_from(Criteria)
            .where(Criteria.batch_id == batch.id)
        )
        criteria_count = db.exec(criteria_count_stmt).one()

        # Count reviewed criteria (review_status IS NOT NULL)
        reviewed_count_stmt = (
            select(func.count())
            .select_from(Criteria)
            .where(
                Criteria.batch_id == batch.id,
                col(Criteria.review_status).isnot(None),
            )
        )
        reviewed_count = db.exec(reviewed_count_stmt).one()

        items.append(
            BatchResponse(
                id=batch.id,
                protocol_id=batch.protocol_id,
                protocol_title=protocol_title,
                status=batch.status,
                extraction_model=batch.extraction_model,
                criteria_count=criteria_count,
                reviewed_count=reviewed_count,
                created_at=batch.created_at,
                updated_at=batch.updated_at,
            )
        )

    return BatchListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get(
    "/batches/{batch_id}/criteria",
    response_model=list[CriterionResponse],
)
def list_batch_criteria(
    batch_id: str,
    sort_by: str = Query(default="confidence"),
    sort_order: str = Query(default="asc"),
    db: Session = Depends(get_db),
) -> list[CriterionResponse]:
    """List all criteria for a batch, sorted by confidence (low first by default).

    Low-confidence criteria appear first so reviewers focus on items
    that most need human judgment (REQ-04.3).
    """
    # Verify batch exists
    batch = db.get(CriteriaBatch, batch_id)
    if not batch:
        raise HTTPException(
            status_code=404,
            detail=f"Batch {batch_id} not found",
        )

    stmt = select(Criteria).where(Criteria.batch_id == batch_id)

    # Apply sorting
    sort_column = getattr(Criteria, sort_by, Criteria.confidence)
    if sort_order == "desc":
        stmt = stmt.order_by(col(sort_column).desc())
    else:
        stmt = stmt.order_by(col(sort_column).asc())

    criteria = db.exec(stmt).all()

    return [_criterion_to_response(c) for c in criteria]


@router.post(
    "/criteria/{criteria_id}/action",
    response_model=CriterionResponse,
)
def submit_review_action(
    criteria_id: str,
    body: ReviewActionRequest,
    db: Session = Depends(get_db),
) -> CriterionResponse:
    """Submit an approve/reject/modify action for a criterion.

    Creates Review and AuditLog records atomically. Updates the parent
    batch status based on review progress:
    - pending_review -> in_progress (first review submitted)
    - in_progress -> approved (all criteria reviewed, none rejected)
    - in_progress -> rejected (all criteria reviewed, any rejected)
    """
    criterion = db.get(Criteria, criteria_id)
    if not criterion:
        raise HTTPException(
            status_code=404,
            detail=f"Criterion {criteria_id} not found",
        )

    # Apply action and capture before/after values
    before_value, after_value = _apply_review_action(criterion, body)
    db.add(criterion)

    # Create Review record
    review = Review(
        reviewer_id=body.reviewer_id,
        target_type="criteria",
        target_id=criteria_id,
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
        target_type="criteria",
        target_id=criteria_id,
        details={
            "action": body.action,
            "before_value": before_value,
            "after_value": after_value,
        },
    )
    db.add(audit_log)

    # Update batch status based on review progress
    _update_batch_status(db, criterion.batch_id)

    db.commit()
    db.refresh(criterion)

    return _criterion_to_response(criterion)


@router.get(
    "/protocols/{protocol_id}/pdf-url",
    response_model=PdfUrlResponse,
)
def get_pdf_url(
    protocol_id: str,
    db: Session = Depends(get_db),
) -> PdfUrlResponse:
    """Get a signed download URL for a protocol PDF.

    Returns a pre-signed GCS URL valid for 60 minutes.
    """
    protocol = db.get(Protocol, protocol_id)
    if not protocol:
        raise HTTPException(
            status_code=404,
            detail=f"Protocol {protocol_id} not found",
        )

    url = generate_download_url(protocol.file_uri)
    return PdfUrlResponse(url=url, expires_in_minutes=60)


@router.get("/audit-log", response_model=AuditLogListResponse)
def list_audit_log(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    target_type: str | None = Query(default=None),
    target_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> AuditLogListResponse:
    """List audit log entries with pagination and optional filters.

    Supports filtering by target_type and target_id for scoped views.
    """
    # Build count query
    count_stmt = select(func.count()).select_from(AuditLog)
    if target_type:
        count_stmt = count_stmt.where(AuditLog.target_type == target_type)
    if target_id:
        count_stmt = count_stmt.where(AuditLog.target_id == target_id)
    total = db.exec(count_stmt).one()

    # Build data query
    data_stmt = select(AuditLog)
    if target_type:
        data_stmt = data_stmt.where(AuditLog.target_type == target_type)
    if target_id:
        data_stmt = data_stmt.where(AuditLog.target_id == target_id)
    data_stmt = (
        data_stmt.offset((page - 1) * page_size)
        .limit(page_size)
        .order_by(col(AuditLog.created_at).desc())
    )

    entries = db.exec(data_stmt).all()
    pages = ceil(total / page_size) if total > 0 else 1

    return AuditLogListResponse(
        items=[
            AuditLogResponse(
                id=entry.id,
                event_type=entry.event_type,
                actor_id=entry.actor_id,
                target_type=entry.target_type,
                target_id=entry.target_id,
                details=entry.details,
                created_at=entry.created_at,
            )
            for entry in entries
        ],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


# --- Helpers ---


def _apply_review_action(
    criterion: Criteria,
    body: ReviewActionRequest,
) -> tuple[Dict[str, Any], Dict[str, Any] | None]:
    """Apply a review action to a criterion and return before/after values.

    Returns:
        Tuple of (before_value, after_value). after_value is None unless
        action is "modify".
    """
    before_value: Dict[str, Any] = {
        "text": criterion.text,
        "criteria_type": criterion.criteria_type,
        "category": criterion.category,
    }
    after_value: Dict[str, Any] | None = None

    if body.action == "approve":
        criterion.review_status = "approved"
    elif body.action == "reject":
        criterion.review_status = "rejected"
    elif body.action == "modify":
        criterion.review_status = "modified"
        if body.modified_text is not None:
            criterion.text = body.modified_text
        if body.modified_type is not None:
            criterion.criteria_type = body.modified_type
        if body.modified_category is not None:
            criterion.category = body.modified_category
        after_value = {
            "text": criterion.text,
            "criteria_type": criterion.criteria_type,
            "category": criterion.category,
        }

    return before_value, after_value


def _update_batch_status(db: Session, batch_id: str) -> None:
    """Update a batch's status based on its criteria review progress.

    Transitions: pending_review -> in_progress -> approved/rejected
    """
    batch = db.get(CriteriaBatch, batch_id)
    if not batch:
        return

    total_count = db.exec(
        select(func.count()).select_from(Criteria).where(Criteria.batch_id == batch.id)
    ).one()

    reviewed_count = db.exec(
        select(func.count())
        .select_from(Criteria)
        .where(
            Criteria.batch_id == batch.id,
            col(Criteria.review_status).isnot(None),
        )
    ).one()

    if batch.status == "pending_review" and reviewed_count >= 1:
        batch.status = "in_progress"

    if reviewed_count == total_count and total_count > 0:
        rejected_count = db.exec(
            select(func.count())
            .select_from(Criteria)
            .where(
                Criteria.batch_id == batch.id,
                Criteria.review_status == "rejected",
            )
        ).one()
        batch.status = "rejected" if rejected_count > 0 else "approved"

    db.add(batch)


def _criterion_to_response(criterion: Criteria) -> CriterionResponse:
    """Convert a Criteria model to CriterionResponse."""
    return CriterionResponse(
        id=criterion.id,
        batch_id=criterion.batch_id,
        criteria_type=criterion.criteria_type,
        category=criterion.category,
        text=criterion.text,
        temporal_constraint=criterion.temporal_constraint,
        conditions=criterion.conditions,
        numeric_thresholds=criterion.numeric_thresholds,
        assertion_status=criterion.assertion_status,
        confidence=criterion.confidence,
        source_section=criterion.source_section,
        review_status=criterion.review_status,
        created_at=criterion.created_at,
        updated_at=criterion.updated_at,
    )
