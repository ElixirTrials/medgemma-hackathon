"""FastAPI router for protocol upload, confirmation, listing, and detail.

Provides endpoints for:
- POST /protocols/upload: Generate signed URL for direct browser-to-GCS upload
- POST /protocols/{id}/confirm-upload: Confirm and quality-check
- GET /protocols: Paginated protocol list with optional status filter
- GET /protocols/{protocol_id}: Protocol detail view with quality metadata
- POST /protocols/{protocol_id}/retry: Resume failed protocol from LangGraph checkpoint
- GET /protocols/{protocol_id}/batches: All batches including archived (timeline)
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timedelta, timezone
from math import ceil
from typing import Any

from events_py.models import DomainEventKind
from events_py.outbox import persist_with_outbox
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from shared.models import Criteria, CriteriaBatch, Protocol, Review
from shared.resilience import gemini_breaker
from sqlmodel import Session, col, func, select

from api_service.dependencies import get_db
from api_service.fuzzy_matching import inherit_reviews_for_batch
from api_service.gcs import (
    generate_upload_url,
    set_blob_metadata,
)
from api_service.quality import (
    compute_quality_score,
    quality_result_to_metadata,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/protocols", tags=["protocols"])


# --- Request/Response models ---


class UploadRequest(BaseModel):
    """Request body for initiating a protocol PDF upload."""

    filename: str
    content_type: str = "application/pdf"
    file_size_bytes: int


class UploadResponse(BaseModel):
    """Response with signed upload URL and protocol metadata."""

    protocol_id: str
    upload_url: str
    gcs_path: str
    warning: str | None = None


class ConfirmUploadRequest(BaseModel):
    """Request body for confirming upload and triggering quality analysis.

    The pdf_bytes_base64 field is optional. If provided, the server
    decodes it and runs quality analysis. If omitted, quality scoring
    is skipped (useful when the browser uploaded directly to GCS).
    """

    pdf_bytes_base64: str | None = None


class ProtocolResponse(BaseModel):
    """Response model for a single protocol."""

    id: str
    title: str
    file_uri: str
    status: str
    page_count: int | None
    quality_score: float | None
    metadata_: dict
    created_at: datetime
    updated_at: datetime
    error_reason: str | None = None
    version_count: int = 1


class ProtocolListResponse(BaseModel):
    """Paginated list of protocols."""

    items: list[ProtocolResponse]
    total: int
    page: int
    page_size: int
    pages: int


class RetryResponse(BaseModel):
    """Response for retry endpoint."""

    status: str
    protocol_id: str


class ReExtractResponse(BaseModel):
    """Response for re-extraction endpoint."""

    status: str
    protocol_id: str
    archived_batches: int


class BatchSummaryResponse(BaseModel):
    """Response model for a single batch summary in the protocol timeline.

    Includes ALL batches (archived and non-archived) ordered chronologically.
    Used by the batch timeline view to show re-extraction history.
    """

    id: str
    protocol_id: str
    status: str
    is_archived: bool
    criteria_count: int
    reviewed_count: int
    extraction_model: str | None
    created_at: datetime


# --- Endpoints ---


@router.post("/upload", response_model=UploadResponse)
def upload_protocol(
    body: UploadRequest,
    db: Session = Depends(get_db),
) -> UploadResponse:
    """Generate a signed URL for uploading a protocol PDF.

    Validates the content type (must be PDF) and file size (max 50MB),
    creates a Protocol record in the database, and returns a signed
    URL for direct browser upload to GCS.
    """
    # Validate content type
    if body.content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail="Only PDF files are accepted",
        )

    # Validate file size (50MB limit)
    max_size = 50 * 1024 * 1024
    if body.file_size_bytes > max_size:
        raise HTTPException(
            status_code=400,
            detail="File size exceeds 50MB limit",
        )

    # Generate signed upload URL
    signed_url, gcs_path = generate_upload_url(
        filename=body.filename,
        content_type=body.content_type,
    )

    # Create protocol record with title from filename (strip .pdf)
    title = body.filename
    if title.lower().endswith(".pdf"):
        title = title[:-4]

    protocol = Protocol(
        title=title,
        file_uri=gcs_path,
        status="uploaded",
    )

    # Persist protocol record only — the ProtocolUploaded event is deferred
    # to confirm-upload so the file actually exists when the processor runs.
    db.add(protocol)
    db.commit()

    # Check circuit breaker states — if critical services are down,
    # mark protocol as pending with warning (per locked decision)
    processing_warning: str | None = None
    if gemini_breaker.current_state != "closed":
        protocol.status = "pending"
        processing_warning = "Processing delayed — AI service temporarily unavailable"
        protocol.metadata_ = {
            **protocol.metadata_,
            "processing_warning": processing_warning,
        }
        db.add(protocol)
        db.commit()

    return UploadResponse(
        protocol_id=protocol.id,
        upload_url=signed_url,
        gcs_path=gcs_path,
        warning=processing_warning,
    )


@router.post(
    "/{protocol_id}/confirm-upload",
    response_model=ProtocolResponse,
)
def confirm_upload(
    protocol_id: str,
    body: ConfirmUploadRequest,
    db: Session = Depends(get_db),
) -> ProtocolResponse:
    """Confirm a protocol upload and optionally trigger quality analysis.

    Looks up the protocol by ID. If pdf_bytes_base64 is provided,
    decodes the PDF bytes and computes a quality score including
    text extractability, page count, and encoding type.
    """
    protocol = db.get(Protocol, protocol_id)
    if not protocol:
        raise HTTPException(
            status_code=404,
            detail=f"Protocol {protocol_id} not found",
        )

    if body.pdf_bytes_base64:
        try:
            pdf_bytes = base64.b64decode(body.pdf_bytes_base64)
            result = compute_quality_score(pdf_bytes)

            protocol.quality_score = result.overall_score
            protocol.page_count = result.page_count
            protocol.metadata_ = {"quality": result.model_dump()}

            # Store quality metadata on GCS blob (best-effort)
            try:
                set_blob_metadata(
                    protocol.file_uri,
                    quality_result_to_metadata(result),
                )
            except Exception:
                logger.warning(
                    "Failed to set GCS metadata for %s",
                    protocol.file_uri,
                    exc_info=True,
                )
        except Exception:
            logger.warning(
                "Failed to compute quality score for protocol %s",
                protocol_id,
                exc_info=True,
            )

    # Now that the file is confirmed uploaded, publish the outbox event
    # to trigger the protocol processor pipeline.
    persist_with_outbox(
        session=db,
        entity=protocol,
        event_type=DomainEventKind.PROTOCOL_UPLOADED,
        aggregate_type="protocol",
        aggregate_id=protocol.id,
        payload={
            "protocol_id": protocol.id,
            "title": protocol.title,
            "file_uri": protocol.file_uri,
        },
    )
    db.commit()
    db.refresh(protocol)

    return _protocol_to_response(protocol)


@router.post("/{protocol_id}/retry", response_model=RetryResponse)
async def retry_protocol(
    protocol_id: str,
    db: Session = Depends(get_db),
) -> RetryResponse:
    """Retry a failed protocol by resuming from the last LangGraph checkpoint.

    Accepts protocols in extraction_failed, grounding_failed, or dead_letter states.
    Updates the protocol status to processing, then resumes the pipeline from the
    last successful checkpoint (via LangGraph PostgresSaver) — skipping nodes
    that already succeeded (ingest, extract, parse) and retrying from the failed node.

    This does NOT create a new outbox event. The retry goes directly through
    the graph using the saved checkpoint. Initial pipeline runs still use the
    outbox trigger pattern (handle_protocol_uploaded).
    """
    protocol = db.get(Protocol, protocol_id)
    if not protocol:
        raise HTTPException(
            status_code=404,
            detail=f"Protocol {protocol_id} not found",
        )

    retryable_states = ["extraction_failed", "grounding_failed", "dead_letter"]
    if protocol.status not in retryable_states:
        raise HTTPException(
            status_code=400,
            detail=f"Protocol is not in a retryable state (current: {protocol.status})",
        )

    previous_status = protocol.status
    protocol.status = "processing"
    protocol.error_reason = None
    db.add(protocol)
    db.commit()

    try:
        from protocol_processor.trigger import retry_from_checkpoint

        await retry_from_checkpoint(protocol_id)
    except Exception as e:
        protocol.status = previous_status
        protocol.error_reason = str(e)[:500]
        db.add(protocol)
        db.commit()
        logger.error("Retry failed for protocol %s: %s", protocol_id, e)

    return RetryResponse(status="retry_started", protocol_id=protocol_id)


@router.post("/{protocol_id}/archive", response_model=ProtocolResponse)
def archive_protocol(
    protocol_id: str,
    db: Session = Depends(get_db),
) -> ProtocolResponse:
    """Archive a failed or dead-letter protocol.

    Only protocols in dead_letter, extraction_failed, or grounding_failed
    states may be manually archived. Returns 400 for non-archivable states.
    """
    protocol = db.get(Protocol, protocol_id)
    if not protocol:
        raise HTTPException(
            status_code=404,
            detail=f"Protocol {protocol_id} not found",
        )

    archivable_states = {"dead_letter", "extraction_failed", "grounding_failed"}
    if protocol.status not in archivable_states:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Protocol cannot be archived from state '{protocol.status}'. "
                "Archivable states: " + ", ".join(sorted(archivable_states))
            ),
        )

    protocol.status = "archived"
    db.add(protocol)
    db.commit()
    db.refresh(protocol)

    return _protocol_to_response(protocol)


@router.post("/{protocol_id}/re-extract", response_model=ReExtractResponse)
def re_extract_protocol(
    protocol_id: str,
    db: Session = Depends(get_db),
) -> ReExtractResponse:
    """Trigger re-extraction on an existing protocol without re-uploading the PDF.

    Archives all existing non-archived batches for this protocol (preserves them
    in the database but hides them from the dashboard and review page). Collects
    reviewed criteria from the archived batches to enable review inheritance.
    Triggers the extraction pipeline via outbox event (same flow as initial upload).

    The extraction pipeline will create a new batch. Review decisions from archived
    criteria are auto-inherited for criteria with >90% fuzzy text match (same type).

    Returns 404 if protocol not found.
    Returns 409 if protocol is in a processing state (extracting, grounding) to
    prevent race conditions — only terminal states are re-extractable.
    """
    protocol = db.get(Protocol, protocol_id)
    if not protocol:
        raise HTTPException(
            status_code=404,
            detail=f"Protocol {protocol_id} not found",
        )

    # Only allow re-extraction from terminal states — prevent race conditions
    # with an in-progress pipeline run (Pitfall 5 from RESEARCH.md)
    terminal_states = {
        "pending_review",
        "complete",
        "extraction_failed",
        "grounding_failed",
        "dead_letter",
    }
    if protocol.status not in terminal_states:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Protocol is not in a terminal state (current: {protocol.status}). "
                "Re-extraction is only allowed for: "
                + ", ".join(sorted(terminal_states))
            ),
        )

    # Find all non-archived batches for this protocol
    existing_batches = db.exec(
        select(CriteriaBatch).where(
            CriteriaBatch.protocol_id == protocol_id,
            CriteriaBatch.is_archived == False,  # noqa: E712
        )
    ).all()

    # Collect reviewed criteria from batches being archived (for inheritance)
    archived_reviewed_criteria: list[dict[str, Any]] = []
    for batch in existing_batches:
        criteria = db.exec(
            select(Criteria).where(
                Criteria.batch_id == batch.id,
                col(Criteria.review_status).isnot(None),
            )
        ).all()
        for criterion in criteria:
            archived_reviewed_criteria.append(
                {
                    "id": criterion.id,
                    "text": criterion.text,
                    "criteria_type": criterion.criteria_type,
                    "review_status": criterion.review_status,
                    "reviewed_by": None,  # Review reviewer_id tracked in Review table
                }
            )

    # Archive all existing non-archived batches
    archived_count = len(existing_batches)
    for batch in existing_batches:
        batch.is_archived = True
        db.add(batch)

    logger.info(
        "Archiving %d batch(es) for protocol %s before re-extraction "
        "(collected %d reviewed criteria for inheritance)",
        archived_count,
        protocol_id,
        len(archived_reviewed_criteria),
    )

    # Update protocol status to extracting and trigger extraction pipeline
    protocol.status = "extracting"
    protocol.error_reason = None

    # Trigger extraction via outbox event — reuses existing pipeline
    # (same as initial upload flow). Include archived reviewed criteria in
    # payload so the persist node can apply review inheritance after batch creation.
    persist_with_outbox(
        session=db,
        entity=protocol,
        event_type=DomainEventKind.PROTOCOL_UPLOADED,
        aggregate_type="protocol",
        aggregate_id=protocol.id,
        payload={
            "protocol_id": protocol.id,
            "title": protocol.title,
            "file_uri": protocol.file_uri,
            "archived_reviewed_criteria": archived_reviewed_criteria,
        },
    )

    db.commit()

    return ReExtractResponse(
        status="extracting",
        protocol_id=protocol_id,
        archived_batches=archived_count,
    )


@router.get("", response_model=ProtocolListResponse)
def list_protocols(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    deduplicate: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> ProtocolListResponse:
    """List protocols with pagination and optional status filter.

    Returns a paginated list sorted by creation date (newest first).
    Includes total count, page number, page size, and total pages.
    Excludes archived protocols from default view unless explicitly filtered.

    When deduplicate=True, returns one protocol per unique title (the latest
    version) with a version_count field indicating how many versions exist.
    Archived protocols are excluded from deduplication queries.
    """
    if deduplicate:
        return _list_protocols_deduplicated(page, page_size, status, db)

    # Build count query
    count_stmt = select(func.count()).select_from(Protocol)
    if status:
        count_stmt = count_stmt.where(Protocol.status == status)
    else:
        # Exclude archived protocols from default view
        count_stmt = count_stmt.where(Protocol.status != "archived")
    total = db.exec(count_stmt).one()

    # Build data query
    data_stmt = select(Protocol)
    if status:
        data_stmt = data_stmt.where(Protocol.status == status)
    else:
        # Exclude archived protocols from default view
        data_stmt = data_stmt.where(Protocol.status != "archived")
    data_stmt = (
        data_stmt.offset((page - 1) * page_size)
        .limit(page_size)
        .order_by(Protocol.created_at.desc())  # type: ignore[attr-defined]
    )

    protocols = db.exec(data_stmt).all()
    pages = ceil(total / page_size) if total > 0 else 1

    return ProtocolListResponse(
        items=[_protocol_to_response(p) for p in protocols],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


def _list_protocols_deduplicated(
    page: int,
    page_size: int,
    status: str | None,
    db: Session,
) -> ProtocolListResponse:
    """Return one protocol per unique title (latest version) with version_count.

    Excludes archived protocols. When status filter is provided, only titles
    whose latest version matches that status are returned.
    """
    # Subquery: latest created_at per title (excluding archived)
    latest_subq = (
        select(Protocol.title, func.max(Protocol.created_at).label("max_created"))
        .where(Protocol.status != "archived")
        .group_by(Protocol.title)
        .subquery()
    )

    # Count subquery: number of (non-archived) versions per title
    count_subq = (
        select(Protocol.title, func.count(col(Protocol.id)).label("version_count"))
        .where(Protocol.status != "archived")
        .group_by(Protocol.title)
        .subquery()
    )

    # Join Protocol to latest_subq to get the canonical (newest) row per title
    dedup_stmt = select(Protocol).join(
        latest_subq,
        (col(Protocol.title) == latest_subq.c.title)
        & (col(Protocol.created_at) == latest_subq.c.max_created),
    )

    if status:
        dedup_stmt = dedup_stmt.where(Protocol.status == status)

    # Count total unique titles (for pagination)
    count_stmt = select(func.count()).select_from(dedup_stmt.subquery())
    total = db.exec(count_stmt).one()

    # Apply pagination and ordering
    dedup_stmt = (
        dedup_stmt.order_by(Protocol.created_at.desc())  # type: ignore[attr-defined]
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    protocols = db.exec(dedup_stmt).all()
    pages = ceil(total / page_size) if total > 0 else 1

    # Build version_count lookup from count subquery
    version_counts: dict[str, int] = {
        row[0]: row[1]
        for row in db.exec(select(count_subq.c.title, count_subq.c.version_count)).all()
    }

    return ProtocolListResponse(
        items=[
            _protocol_to_response(p, version_count=version_counts.get(p.title, 1))
            for p in protocols
        ],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/{protocol_id}", response_model=ProtocolResponse)
def get_protocol(
    protocol_id: str,
    db: Session = Depends(get_db),
) -> ProtocolResponse:
    """Get protocol detail including quality score and metadata.

    Performs lazy archival: if a protocol is in dead_letter status and
    hasn't been updated in 7+ days, it is automatically transitioned to archived.
    """
    protocol = db.get(Protocol, protocol_id)
    if not protocol:
        raise HTTPException(
            status_code=404,
            detail=f"Protocol {protocol_id} not found",
        )

    # Check for dead-letter archival
    _check_dead_letter_archival(protocol, db)

    return _protocol_to_response(protocol)


@router.get(
    "/{protocol_id}/batches",
    response_model=list[BatchSummaryResponse],
)
def list_protocol_batches(
    protocol_id: str,
    db: Session = Depends(get_db),
) -> list[BatchSummaryResponse]:
    """List ALL batches for a protocol including archived ones.

    Returns batches in chronological order (oldest first) for the batch
    timeline view. Unlike GET /reviews/batches which excludes archived
    batches for the review workflow, this endpoint includes them so that
    reviewers can see the full re-extraction history.

    This is intentionally separate from the existing batch listing endpoint
    to preserve the review workflow's correct exclusion of archived batches
    (per research anti-pattern guidance).

    Returns 404 if protocol doesn't exist.
    """
    # Verify protocol exists
    protocol = db.get(Protocol, protocol_id)
    if not protocol:
        raise HTTPException(
            status_code=404,
            detail=f"Protocol {protocol_id} not found",
        )

    # Load ALL batches for this protocol (no is_archived filter)
    # ordered chronologically ascending for timeline display
    batches = db.exec(
        select(CriteriaBatch)
        .where(CriteriaBatch.protocol_id == protocol_id)
        .order_by(col(CriteriaBatch.created_at).asc())
    ).all()

    if not batches:
        return []

    # Batch-load criteria counts to avoid N+1 queries
    batch_ids = [b.id for b in batches]

    # Total criteria count per batch
    total_counts_stmt = (
        select(Criteria.batch_id, func.count(col(Criteria.id)).label("cnt"))
        .where(col(Criteria.batch_id).in_(batch_ids))
        .group_by(Criteria.batch_id)
    )
    total_counts: dict[str, int] = {
        row[0]: row[1] for row in db.exec(total_counts_stmt).all()
    }

    # Reviewed criteria count per batch (review_status IS NOT NULL)
    reviewed_counts_stmt = (
        select(Criteria.batch_id, func.count(col(Criteria.id)).label("cnt"))
        .where(
            col(Criteria.batch_id).in_(batch_ids),
            col(Criteria.review_status).isnot(None),
        )
        .group_by(Criteria.batch_id)
    )
    reviewed_counts: dict[str, int] = {
        row[0]: row[1] for row in db.exec(reviewed_counts_stmt).all()
    }

    return [
        BatchSummaryResponse(
            id=batch.id,
            protocol_id=batch.protocol_id,
            status=batch.status,
            is_archived=batch.is_archived,
            criteria_count=total_counts.get(batch.id, 0),
            reviewed_count=reviewed_counts.get(batch.id, 0),
            extraction_model=batch.extraction_model,
            created_at=batch.created_at,
        )
        for batch in batches
    ]


# --- Helpers ---


def _protocol_to_response(
    protocol: Protocol, version_count: int = 1
) -> ProtocolResponse:
    """Convert a Protocol model to ProtocolResponse."""
    return ProtocolResponse(
        id=protocol.id,
        title=protocol.title,
        file_uri=protocol.file_uri,
        status=protocol.status,
        page_count=protocol.page_count,
        quality_score=protocol.quality_score,
        metadata_=protocol.metadata_,
        created_at=protocol.created_at,
        updated_at=protocol.updated_at,
        error_reason=protocol.error_reason,
        version_count=version_count,
    )


def _check_dead_letter_archival(protocol: Protocol, session: Session) -> None:
    """Check if a dead-letter protocol should be archived.

    Archives protocols that have been in dead_letter status for more than 7 days
    since their last update. This is a lazy archival strategy triggered on access.
    """
    if protocol.status != "dead_letter":
        return

    # Check if updated_at is more than 7 days ago
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    if protocol.updated_at < cutoff:
        logger.info(
            "Archiving dead-letter protocol %s (last updated: %s)",
            protocol.id,
            protocol.updated_at,
        )
        protocol.status = "archived"
        session.add(protocol)
        session.commit()


def apply_review_inheritance(
    db: Session,
    protocol_id: str,
    archived_criteria: list[dict[str, Any]],
) -> None:
    """Auto-inherit review decisions from archived criteria to new batch criteria.

    Finds the newest non-archived batch for the protocol, then uses fuzzy
    matching to identify matching criteria from the archived set. For each
    match above the 90% threshold (same criteria_type), copies the review
    decision to the new criterion and creates a Review record.

    Called from the extraction pipeline after new batch/criteria are persisted
    (e.g., from persist_node in extraction-service when archived_reviewed_criteria
    is present in the outbox payload).

    Args:
        db: Database session.
        protocol_id: Protocol to apply inheritance for.
        archived_criteria: List of criterion dicts from archived batches.
            Must have: id, text, criteria_type, review_status.
    """
    if not archived_criteria:
        return

    # Find the newest non-archived batch for this protocol
    newest_batch = db.exec(
        select(CriteriaBatch)
        .where(
            CriteriaBatch.protocol_id == protocol_id,
            CriteriaBatch.is_archived == False,  # noqa: E712
        )
        .order_by(col(CriteriaBatch.created_at).desc())
        .limit(1)
    ).first()

    if not newest_batch:
        logger.warning(
            "No non-archived batch found for protocol %s — skipping inheritance",
            protocol_id,
        )
        return

    # Load new criteria from the newest batch
    new_criteria_list = db.exec(
        select(Criteria).where(Criteria.batch_id == newest_batch.id)
    ).all()

    if not new_criteria_list:
        return

    # Convert new criteria to dicts for fuzzy matching
    new_criteria_dicts = [
        {
            "id": c.id,
            "text": c.text,
            "criteria_type": c.criteria_type,
        }
        for c in new_criteria_list
    ]

    # Run fuzzy matching to find inheritance candidates
    matches = inherit_reviews_for_batch(
        new_criteria=new_criteria_dicts,
        archived_criteria=archived_criteria,
    )

    if not matches:
        logger.info(
            "No review decisions inherited for protocol %s (0 matches found)",
            protocol_id,
        )
        return

    # Build lookup for fast criterion access
    criteria_by_id = {c.id: c for c in new_criteria_list}

    # Apply inheritance: update criterion status and create Review records
    inherited = 0
    for match in matches:
        criterion = criteria_by_id.get(match["new_criterion_id"])
        if not criterion:
            continue

        criterion.review_status = match["review_status"]
        db.add(criterion)

        # Create Review record documenting the auto-inheritance
        review = Review(
            reviewer_id="system:re-extraction-inheritance",
            target_type="criteria",
            target_id=criterion.id,
            action=match["review_status"],  # e.g., "approved", "rejected", "modified"
            before_value={"review_status": None},
            after_value={
                "review_status": match["review_status"],
                "inherited_from": match["old_criterion_id"],
                "match_score": match["match_score"],
            },
            comment=(
                f"Auto-inherited from archived criterion {match['old_criterion_id']} "
                f"(fuzzy match score: {match['match_score']:.1f}%)"
            ),
        )
        db.add(review)
        inherited += 1

    db.commit()

    logger.info(
        "Inherited %d/%d review decisions for protocol %s",
        inherited,
        len(new_criteria_list),
        protocol_id,
    )
