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
import os
from datetime import datetime
from math import ceil
from typing import Any, Dict, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from shared.models import AuditLog, Criteria, CriteriaBatch, Entity, Protocol, Review
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


class CriterionEntityResponse(BaseModel):
    """Embedded entity summary within a criterion response."""

    id: str
    entity_type: str
    text: str
    umls_cui: str | None
    snomed_code: str | None
    preferred_term: str | None
    grounding_confidence: float | None
    grounding_method: str | None
    rxnorm_code: str | None
    icd10_code: str | None
    loinc_code: str | None
    hpo_code: str | None


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
    page_number: int | None = None
    review_status: str | None
    entities: list[CriterionEntityResponse] = []
    created_at: datetime
    updated_at: datetime


class ReviewActionRequest(BaseModel):
    """Request body for submitting a review action."""

    action: Literal["approve", "reject", "modify"]
    reviewer_id: str
    modified_text: str | None = None
    modified_type: str | None = None
    modified_category: str | None = None
    modified_structured_fields: Dict[str, Any] | None = None
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


class PendingSummaryResponse(BaseModel):
    """Summary of pending review work."""

    pending_batches: int
    pending_criteria: int
    message: str


class BatchMetricsResponse(BaseModel):
    """Per-batch review agreement metrics response."""

    batch_id: str
    total_criteria: int
    approved: int
    rejected: int
    modified: int
    pending: int
    approved_pct: float
    rejected_pct: float
    modified_pct: float
    modification_breakdown: Dict[str, int]
    per_criterion_details: list[Dict[str, Any]]


# --- Endpoints ---


@router.get("/batches", response_model=BatchListResponse)
def list_batches(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    protocol_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> BatchListResponse:
    """List criteria batches with pagination, protocol info, and review progress.

    Returns batches ordered by creation date (newest first) with:
    - Protocol title from joined Protocol table
    - Count of linked criteria per batch
    - Count of reviewed criteria (review_status IS NOT NULL) for progress
    """
    # Build count query — exclude archived batches (hidden from dashboard)
    count_stmt = select(func.count()).select_from(CriteriaBatch).where(
        CriteriaBatch.is_archived == False  # noqa: E712
    )
    if status:
        count_stmt = count_stmt.where(CriteriaBatch.status == status)
    if protocol_id:
        count_stmt = count_stmt.where(CriteriaBatch.protocol_id == protocol_id)
    total = db.exec(count_stmt).one()

    # Build data query — exclude archived batches (Pitfall 1 from RESEARCH.md)
    data_stmt = select(CriteriaBatch).where(
        CriteriaBatch.is_archived == False  # noqa: E712
    )
    if status:
        data_stmt = data_stmt.where(CriteriaBatch.status == status)
    if protocol_id:
        data_stmt = data_stmt.where(CriteriaBatch.protocol_id == protocol_id)
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
    "/batches/{batch_id}/metrics",
    response_model=BatchMetricsResponse,
)
def get_batch_metrics(
    batch_id: str,
    db: Session = Depends(get_db),
) -> BatchMetricsResponse:
    """Return agreement metrics for a criteria batch.

    Counts criteria by review_status and computes percentages.
    Breaks down modify actions by schema_version from AuditLog details.
    Includes per_criterion_details for reviewed criteria (drill-down layer 2).

    Uses exactly 2 SQL queries (criteria + audit logs) — no N+1.
    """
    # Verify batch exists
    batch = db.get(CriteriaBatch, batch_id)
    if not batch:
        raise HTTPException(
            status_code=404,
            detail=f"Batch {batch_id} not found",
        )

    # Query 1: All criteria for this batch
    criteria_list = db.exec(
        select(Criteria).where(Criteria.batch_id == batch_id)
    ).all()

    total = len(criteria_list)
    approved = sum(1 for c in criteria_list if c.review_status == "approved")
    rejected = sum(1 for c in criteria_list if c.review_status == "rejected")
    modified = sum(1 for c in criteria_list if c.review_status == "modified")
    pending = sum(1 for c in criteria_list if c.review_status is None)

    def _pct(count: int) -> float:
        return round(count / total * 100, 1) if total > 0 else 0.0

    # Query 2: All audit logs for this batch's criteria (join Criteria → AuditLog)
    criteria_ids = [c.id for c in criteria_list]
    modification_breakdown: Dict[str, int] = {}
    if criteria_ids:
        audit_logs = db.exec(
            select(AuditLog)
            .join(Criteria, col(AuditLog.target_id) == col(Criteria.id))
            .where(
                col(AuditLog.target_type) == "criteria",
                col(Criteria.batch_id) == batch_id,
                col(AuditLog.event_type) == "review_action",
            )
        ).all()

        schema_version_map = {
            "text_v1": "text_edits",
            "structured_v1": "structured_edits",
            "v1.5-multi": "field_mapping_changes",
        }
        for log in audit_logs:
            details = log.details or {}
            if details.get("action") == "modify":
                schema_version = details.get("schema_version", "")
                breakdown_key = schema_version_map.get(schema_version)
                if breakdown_key:
                    modification_breakdown[breakdown_key] = (
                        modification_breakdown.get(breakdown_key, 0) + 1
                    )

    # Build per_criterion_details for reviewed criteria
    per_criterion_details: list[Dict[str, Any]] = [
        {
            "criterion_id": c.id,
            "criterion_text": c.text[:100],
            "review_status": c.review_status,
            "criteria_type": c.criteria_type,
        }
        for c in criteria_list
        if c.review_status is not None
    ]

    return BatchMetricsResponse(
        batch_id=batch_id,
        total_criteria=total,
        approved=approved,
        rejected=rejected,
        modified=modified,
        pending=pending,
        approved_pct=_pct(approved),
        rejected_pct=_pct(rejected),
        modified_pct=_pct(modified),
        modification_breakdown=modification_breakdown,
        per_criterion_details=per_criterion_details,
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

    # Batch-load entities for all criteria in one query
    criteria_ids = [c.id for c in criteria]
    entities_by_criteria: dict[str, list[Entity]] = {cid: [] for cid in criteria_ids}
    if criteria_ids:
        entity_stmt = (
            select(Entity)
            .where(col(Entity.criteria_id).in_(criteria_ids))
            .order_by(col(Entity.span_start).asc())
        )
        for entity in db.exec(entity_stmt).all():
            entities_by_criteria[entity.criteria_id].append(entity)

    return [
        _criterion_to_response(c, entities_by_criteria.get(c.id, [])) for c in criteria
    ]


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
    # Determine schema version based on what fields are modified
    has_field_mappings = (
        body.modified_structured_fields
        and "field_mappings" in body.modified_structured_fields
    )
    if has_field_mappings:
        schema_version = "v1.5-multi"
    elif body.modified_structured_fields:
        schema_version = "structured_v1"
    else:
        schema_version = "text_v1"

    audit_details: Dict[str, Any] = {
        "action": body.action,
        "before_value": before_value,
        "after_value": after_value,
        "schema_version": schema_version,
    }
    if body.comment:
        audit_details["rationale"] = body.comment

    audit_log = AuditLog(
        event_type="review_action",
        actor_id=body.reviewer_id,
        target_type="criteria",
        target_id=criteria_id,
        details=audit_details,
    )
    db.add(audit_log)

    # Trace HITL action in MLflow
    try:
        import mlflow

        if os.getenv("MLFLOW_TRACKING_URI"):
            with mlflow.start_span(
                name=f"hitl_review_{body.action}",
                span_type="TOOL",
            ) as span:
                span.set_inputs(
                    {
                        "action": body.action,
                        "reviewer_id": body.reviewer_id,
                        "criteria_id": criteria_id,
                        "batch_id": criterion.batch_id,
                    }
                )
    except Exception:
        logger.debug("MLflow HITL tracing failed", exc_info=True)

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


@router.get("/pending-summary", response_model=PendingSummaryResponse)
def get_pending_summary(db: Session = Depends(get_db)) -> PendingSummaryResponse:
    """Get summary of pending review work.

    Returns counts of batches and criteria needing review.
    Pending = batches with at least one unreviewed criterion.
    """
    # Count criteria where review_status IS NULL in active batches
    pending_criteria_stmt = (
        select(func.count())
        .select_from(Criteria)
        .join(CriteriaBatch, col(Criteria.batch_id) == col(CriteriaBatch.id))
        .where(
            col(Criteria.review_status).is_(None),
            col(CriteriaBatch.status).in_(
                ["pending_review", "in_progress", "entities_grounded"]
            ),
        )
    )
    pending_criteria = db.exec(pending_criteria_stmt).one()

    # Count distinct batches that have at least one unreviewed criterion
    pending_batches_stmt = (
        select(func.count(func.distinct(col(CriteriaBatch.id))))
        .select_from(Criteria)
        .join(CriteriaBatch, col(Criteria.batch_id) == col(CriteriaBatch.id))
        .where(
            col(Criteria.review_status).is_(None),
            col(CriteriaBatch.status).in_(
                ["pending_review", "in_progress", "entities_grounded"]
            ),
        )
    )
    pending_batches = db.exec(pending_batches_stmt).one()

    message = (
        f"{pending_batches} batch{'es' if pending_batches != 1 else ''} "
        f"({pending_criteria} criteria) pending review"
    )

    return PendingSummaryResponse(
        pending_batches=pending_batches,
        pending_criteria=pending_criteria,
        message=message,
    )


@router.get("/audit-log", response_model=AuditLogListResponse)
def list_audit_log(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    target_type: str | None = Query(default=None),
    target_id: str | None = Query(default=None),
    batch_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> AuditLogListResponse:
    """List audit log entries with pagination and optional filters.

    Supports filtering by target_type, target_id, and batch_id.
    When batch_id is provided, returns audit entries for all criteria
    in that batch (joins through Criteria table).
    """
    # Build count query
    count_stmt = select(func.count()).select_from(AuditLog)

    if batch_id:
        # Join AuditLog → Criteria to filter by batch_id
        count_stmt = (
            count_stmt
            .join(Criteria, col(AuditLog.target_id) == col(Criteria.id))
            .where(
                col(AuditLog.target_type) == "criteria",
                col(Criteria.batch_id) == batch_id
            )
        )
    else:
        # Existing filters (unchanged for backward compatibility)
        if target_type:
            count_stmt = count_stmt.where(AuditLog.target_type == target_type)
        if target_id:
            count_stmt = count_stmt.where(AuditLog.target_id == target_id)

    total = db.exec(count_stmt).one()

    # Build data query (same join logic)
    data_stmt = select(AuditLog)

    if batch_id:
        data_stmt = (
            data_stmt
            .join(Criteria, col(AuditLog.target_id) == col(Criteria.id))
            .where(
                col(AuditLog.target_type) == "criteria",
                col(Criteria.batch_id) == batch_id
            )
        )
    else:
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


def _apply_review_action(  # noqa: C901
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
        "temporal_constraint": criterion.temporal_constraint,
        "numeric_thresholds": criterion.numeric_thresholds,
        "conditions": criterion.conditions,
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
        if body.modified_structured_fields is not None:
            sf = body.modified_structured_fields
            if "temporal_constraint" in sf:
                criterion.temporal_constraint = sf["temporal_constraint"]
            if "numeric_thresholds" in sf:
                criterion.numeric_thresholds = sf["numeric_thresholds"]
            if "conditions" in sf:
                criterion.conditions = sf["conditions"]
            if "field_mappings" in sf:
                # Store field_mappings array in conditions JSONB field
                criterion.conditions = {"field_mappings": sf["field_mappings"]}
        after_value = {
            "text": criterion.text,
            "criteria_type": criterion.criteria_type,
            "category": criterion.category,
            "temporal_constraint": criterion.temporal_constraint,
            "numeric_thresholds": criterion.numeric_thresholds,
            "conditions": criterion.conditions,
        }

    return before_value, after_value


def _update_batch_status(db: Session, batch_id: str) -> None:
    """Update a batch's status based on its criteria review progress.

    Transitions:
    - pending_review -> in_progress (first review submitted)
    - in_progress -> approved (all criteria reviewed, none rejected)
    - in_progress -> rejected (all criteria reviewed, any rejected)
    - in_progress -> reviewed (all criteria reviewed, mixed results)
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

    # First review submitted: pending_review -> in_progress
    if batch.status == "pending_review" and reviewed_count >= 1:
        batch.status = "in_progress"

    # All criteria reviewed: determine final status
    if reviewed_count == total_count and total_count > 0:
        rejected_count = db.exec(
            select(func.count())
            .select_from(Criteria)
            .where(
                Criteria.batch_id == batch.id,
                Criteria.review_status == "rejected",
            )
        ).one()

        approved_count = db.exec(
            select(func.count())
            .select_from(Criteria)
            .where(
                Criteria.batch_id == batch.id,
                Criteria.review_status == "approved",
            )
        ).one()

        # Terminal state transitions
        if rejected_count > 0:
            batch.status = "rejected"  # Any rejected = batch rejected
        elif approved_count == total_count:
            batch.status = "approved"  # All approved = batch approved
        else:
            batch.status = "reviewed"  # Mixed or modified = batch reviewed

    db.add(batch)


def _criterion_to_response(
    criterion: Criteria, entities: list[Entity] | None = None
) -> CriterionResponse:
    """Convert a Criteria model to CriterionResponse."""
    entity_responses = [
        CriterionEntityResponse(
            id=e.id,
            entity_type=e.entity_type,
            text=e.text,
            umls_cui=e.umls_cui,
            snomed_code=e.snomed_code,
            preferred_term=e.preferred_term,
            grounding_confidence=e.grounding_confidence,
            grounding_method=e.grounding_method,
            rxnorm_code=e.rxnorm_code,
            icd10_code=e.icd10_code,
            loinc_code=e.loinc_code,
            hpo_code=e.hpo_code,
        )
        for e in (entities or [])
    ]
    return CriterionResponse(
        id=criterion.id,
        batch_id=criterion.batch_id,
        criteria_type=criterion.criteria_type,
        category=criterion.category,
        text=criterion.text,
        temporal_constraint=criterion.temporal_constraint,
        conditions=(
            criterion.conditions
            if isinstance(criterion.conditions, dict)
            else {"conditions_list": criterion.conditions}
            if isinstance(criterion.conditions, list)
            else None
        ),
        numeric_thresholds=(
            criterion.numeric_thresholds
            if isinstance(criterion.numeric_thresholds, dict)
            else {"thresholds": criterion.numeric_thresholds}
            if isinstance(criterion.numeric_thresholds, list)
            else None
        ),
        assertion_status=criterion.assertion_status,
        confidence=criterion.confidence,
        source_section=criterion.source_section,
        page_number=criterion.page_number,
        review_status=criterion.review_status,
        entities=entity_responses,
        created_at=criterion.created_at,
        updated_at=criterion.updated_at,
    )
