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
from datetime import datetime
from math import ceil

from events_py.models import DomainEventKind
from events_py.outbox import persist_with_outbox
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from shared.models import Protocol
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

    return UploadResponse(
        protocol_id=protocol.id,
        upload_url=signed_url,
        gcs_path=gcs_path,
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
    """
    # Build count query
    count_stmt = select(func.count()).select_from(Protocol)
    if status:
        count_stmt = count_stmt.where(Protocol.status == status)
    total = db.exec(count_stmt).one()

    # Build data query
    data_stmt = select(Protocol)
    if status:
        data_stmt = data_stmt.where(Protocol.status == status)
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
    """Get protocol detail including quality score and metadata."""
    protocol = db.get(Protocol, protocol_id)
    if not protocol:
        raise HTTPException(
            status_code=404,
            detail=f"Protocol {protocol_id} not found",
        )
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
