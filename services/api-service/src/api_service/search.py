"""FastAPI router for full-text search over criteria.

Provides endpoint:
- GET /criteria/search: Full-text search with filters and pagination
"""

from __future__ import annotations

import logging
import os
from math import ceil

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from shared.models import Criteria, CriteriaBatch, Protocol
from sqlalchemy import String, cast
from sqlalchemy import func as sa_func
from sqlmodel import Session, select

from api_service.dependencies import get_current_user, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/criteria", tags=["search"])


# --- Response models ---


class SearchResult(BaseModel):
    """Single search result with protocol context."""

    id: str
    batch_id: str
    protocol_id: str
    protocol_title: str
    criteria_type: str
    text: str
    confidence: float
    review_status: str | None
    rank: float


class SearchResponse(BaseModel):
    """Paginated search results."""

    items: list[SearchResult]
    total: int
    page: int
    page_size: int
    pages: int
    query: str


# --- Endpoints ---


@router.get("/search", response_model=SearchResponse)
def search_criteria(
    q: str = Query(..., min_length=1),
    protocol_id: str | None = Query(default=None),
    criteria_type: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> SearchResponse:
    """Full-text search over criteria with optional filters.

    Uses PostgreSQL full-text search with GIN index for performance.
    Falls back to LIKE search for SQLite dev environments.
    """
    database_url = os.environ.get("DATABASE_URL", "")
    use_postgres_fts = database_url.startswith("postgresql")

    if not use_postgres_fts:
        logger.warning("Full-text search requires PostgreSQL; using LIKE fallback")

    # Build base query joining Criteria -> CriteriaBatch -> Protocol
    base_stmt = (
        select(
            Criteria.id,
            Criteria.batch_id,
            Criteria.criteria_type,
            Criteria.text,
            Criteria.confidence,
            Criteria.review_status,
            CriteriaBatch.protocol_id,
            Protocol.title.label("protocol_title"),  # type: ignore[attr-defined]
        )
        .join(CriteriaBatch, Criteria.batch_id == CriteriaBatch.id)
        .join(Protocol, CriteriaBatch.protocol_id == Protocol.id)
    )

    # Apply text search
    if use_postgres_fts:
        # PostgreSQL full-text search
        tsvector = sa_func.to_tsvector("english", Criteria.text)
        tsquery = sa_func.plainto_tsquery("english", q)
        rank = sa_func.ts_rank(tsvector, tsquery)

        # Add search condition
        base_stmt = base_stmt.where(tsvector.op("@@")(tsquery))

        # Add rank column for ordering
        stmt_with_rank = select(
            Criteria.id,
            Criteria.batch_id,
            Criteria.criteria_type,
            Criteria.text,
            Criteria.confidence,
            Criteria.review_status,
            CriteriaBatch.protocol_id,
            Protocol.title.label("protocol_title"),  # type: ignore[attr-defined]
            rank.label("rank"),
        ).select_from(base_stmt.subquery())

    else:
        # SQLite LIKE fallback
        base_stmt = base_stmt.where(Criteria.text.contains(q))
        # Add constant rank for SQLite
        stmt_with_rank = select(
            Criteria.id,
            Criteria.batch_id,
            Criteria.criteria_type,
            Criteria.text,
            Criteria.confidence,
            Criteria.review_status,
            CriteriaBatch.protocol_id,
            Protocol.title.label("protocol_title"),  # type: ignore[attr-defined]
            cast(1.0, String).label("rank"),
        ).select_from(base_stmt.subquery())

    # Apply optional filters
    if protocol_id:
        stmt_with_rank = stmt_with_rank.where(
            CriteriaBatch.protocol_id == protocol_id
        )
    if criteria_type:
        stmt_with_rank = stmt_with_rank.where(
            Criteria.criteria_type == criteria_type
        )
    if review_status:
        stmt_with_rank = stmt_with_rank.where(
            Criteria.review_status == review_status
        )

    # Count total results
    count_stmt = select(sa_func.count()).select_from(stmt_with_rank.subquery())
    total = db.exec(count_stmt).one()

    # Apply ordering and pagination
    if use_postgres_fts:
        stmt_with_rank = stmt_with_rank.order_by(
            cast(stmt_with_rank.selected_columns.rank, String).desc()
        )
    else:
        # SQLite fallback - no meaningful rank ordering
        stmt_with_rank = stmt_with_rank.order_by(Criteria.confidence.desc())

    stmt_with_rank = stmt_with_rank.offset((page - 1) * page_size).limit(page_size)

    results = db.exec(stmt_with_rank).all()
    pages = ceil(total / page_size) if total > 0 else 1

    items = [
        SearchResult(
            id=row.id,
            batch_id=row.batch_id,
            protocol_id=row.protocol_id,
            protocol_title=row.protocol_title,
            criteria_type=row.criteria_type,
            text=row.text,
            confidence=row.confidence,
            review_status=row.review_status,
            rank=float(row.rank) if use_postgres_fts else 1.0,
        )
        for row in results
    ]

    return SearchResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        query=q,
    )
