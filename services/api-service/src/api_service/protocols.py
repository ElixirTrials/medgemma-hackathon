"""FastAPI router for protocol upload, confirmation, listing, and detail.

Provides endpoints for:
- POST /protocols/upload: Generate signed URL for direct browser-to-GCS upload
- POST /protocols/{id}/confirm-upload: Confirm and quality-check
- GET /protocols: Paginated protocol list with optional status filter
- GET /protocols/{protocol_id}: Protocol detail view with quality metadata
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timedelta, timezone
from math import ceil

from events_py.models import DomainEventKind
from events_py.outbox import persist_with_outbox
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from shared.models import Protocol
from shared.resilience import gemini_breaker
from sqlmodel import Session, func, select

from api_service.dependencies import get_db
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

    # Persist protocol + outbox event atomically
    persist_with_outbox(
        session=db,
        entity=protocol,
        event_type=DomainEventKind.PROTOCOL_UPLOADED,
        aggregate_type="protocol",
        aggregate_id=protocol.id,
        payload={
            "protocol_id": protocol.id,
            "title": title,
            "file_uri": gcs_path,
        },
    )
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

    db.add(protocol)
    db.commit()
    db.refresh(protocol)

    return _protocol_to_response(protocol)


@router.post("/{protocol_id}/retry", response_model=RetryResponse)
def retry_protocol(
    protocol_id: str,
    db: Session = Depends(get_db),
) -> RetryResponse:
    """Retry a failed protocol by resetting status and creating a new outbox event.

    Accepts protocols in extraction_failed, grounding_failed, or dead_letter states.
    Resets the protocol status to uploaded and creates a PROTOCOL_UPLOADED event
    to re-trigger the processing pipeline.
    """
    protocol = db.get(Protocol, protocol_id)
    if not protocol:
        raise HTTPException(
            status_code=404,
            detail=f"Protocol {protocol_id} not found",
        )

    # Validate protocol is in a retryable state
    retryable_states = ["extraction_failed", "grounding_failed", "dead_letter"]
    if protocol.status not in retryable_states:
        raise HTTPException(
            status_code=400,
            detail=f"Protocol is not in a retryable state (current: {protocol.status})",
        )

    # Reset protocol status
    protocol.status = "uploaded"
    protocol.error_reason = None

    # Clear error metadata if present
    if "error" in protocol.metadata_:
        metadata_copy = protocol.metadata_.copy()
        del metadata_copy["error"]
        protocol.metadata_ = metadata_copy

    # Create new outbox event to re-trigger pipeline
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

    return RetryResponse(status="retry_queued", protocol_id=protocol_id)


@router.get("", response_model=ProtocolListResponse)
def list_protocols(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> ProtocolListResponse:
    """List protocols with pagination and optional status filter.

    Returns a paginated list sorted by creation date (newest first).
    Includes total count, page number, page size, and total pages.
    Excludes archived protocols from default view unless explicitly filtered.
    """
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


# --- Helpers ---


def _protocol_to_response(protocol: Protocol) -> ProtocolResponse:
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
