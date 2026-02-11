"""FastAPI router for full-text search over criteria.

Provides endpoint:
- GET /criteria/search: Full-text search with filters and pagination
"""

from __future__ import annotations

import logging
import os
from math import ceil
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from shared.models import Criteria, CriteriaBatch, Protocol
from sqlalchemy import func as sa_func
from sqlalchemy import text as sa_text
from sqlmodel import Session, col, select

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


def _build_search_query(
    q: str,
    use_postgres_fts: bool,
    protocol_id: str | None,
    criteria_type: str | None,
    review_status: str | None,
) -> Any:
    """Build the search query with filters."""
    stmt = (
        select(Criteria, CriteriaBatch, Protocol)
        .join(
            CriteriaBatch,
            col(Criteria.batch_id) == col(CriteriaBatch.id),
        )
        .join(
            Protocol,
            col(CriteriaBatch.protocol_id) == col(Protocol.id),
        )
    )

    # Apply text search filter
    if use_postgres_fts:
        tsvector = sa_func.to_tsvector(
            sa_text("'english'"), col(Criteria.text)
        )
        tsquery = sa_func.plainto_tsquery(sa_text("'english'"), q)
        stmt = stmt.where(tsvector.op("@@")(tsquery))
    else:
        stmt = stmt.where(col(Criteria.text).contains(q))

    # Apply optional filters
    if protocol_id:
        stmt = stmt.where(
            col(CriteriaBatch.protocol_id) == protocol_id
        )
    if criteria_type:
        stmt = stmt.where(
            col(Criteria.criteria_type) == criteria_type
        )
    if review_status:
        stmt = stmt.where(
            col(Criteria.review_status) == review_status
        )

    return stmt


@router.get("/search", response_model=SearchResponse)
def search_criteria(
    q: str = Query(..., min_length=1),
    protocol_id: str | None = Query(default=None),
    criteria_type: str | None = Query(default=None),
    review_status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),  # noqa: ARG001
) -> SearchResponse:
    """Full-text search over criteria with optional filters.

    Uses PostgreSQL full-text search with GIN index for performance.
    Falls back to LIKE search for SQLite dev environments.
    """
    database_url = os.environ.get("DATABASE_URL", "")
    use_postgres_fts = database_url.startswith("postgresql")

    if not use_postgres_fts:
        logger.warning(
            "Full-text search requires PostgreSQL; using LIKE fallback"
        )

    stmt = _build_search_query(
        q, use_postgres_fts, protocol_id, criteria_type, review_status
    )

    # Count total results
    count_stmt = select(sa_func.count()).select_from(
        stmt.subquery()
    )
    total = db.exec(count_stmt).one()

    # Apply ordering
    if use_postgres_fts:
        tsvector = sa_func.to_tsvector(
            sa_text("'english'"), col(Criteria.text)
        )
        tsquery = sa_func.plainto_tsquery(sa_text("'english'"), q)
        rank = sa_func.ts_rank(tsvector, tsquery)
        stmt = stmt.order_by(rank.desc())
    else:
        stmt = stmt.order_by(col(Criteria.confidence).desc())

    # Paginate
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)

    results = db.exec(stmt).all()
    pages = ceil(total / page_size) if total > 0 else 1

    items = []
    for row in results:
        criteria_obj: Criteria = row[0]  # type: ignore[index]
        batch_obj: CriteriaBatch = row[1]  # type: ignore[index]
        protocol_obj: Protocol = row[2]  # type: ignore[index]
        items.append(
            SearchResult(
                id=criteria_obj.id,
                batch_id=criteria_obj.batch_id,
                protocol_id=batch_obj.protocol_id,
                protocol_title=protocol_obj.title or "",
                criteria_type=criteria_obj.criteria_type,
                text=criteria_obj.text,
                confidence=criteria_obj.confidence,
                review_status=criteria_obj.review_status,
                rank=1.0,
            )
        )

    return SearchResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
        query=q,
    )
