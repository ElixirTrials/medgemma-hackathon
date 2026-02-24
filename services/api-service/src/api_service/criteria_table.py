"""Criteria table API: paginated, filterable, sortable structured criteria view."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from shared.models import Criteria, CriteriaBatch, Entity, Protocol
from sqlmodel import Session, col, func, select

from api_service.dependencies import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/criteria", tags=["criteria-table"])

_SORT_BY_PATTERN = "^(confidence|criteria_type|category|page_number|review_status)$"


class EntitySummary(BaseModel):
    """Compact entity representation for the criteria table."""

    id: str
    entity_type: str
    text: str
    grounding_code: str | None = None
    grounding_system: str | None = None
    preferred_term: str | None = None
    grounding_confidence: float | None = None


class StructuredCriterionRow(BaseModel):
    """Single row in the structured criteria table."""

    id: str
    protocol_id: str | None = None
    protocol_title: str | None = None
    text: str
    criteria_type: str
    category: str | None = None
    confidence: float
    assertion_status: str | None = None
    entities: list[EntitySummary] = []
    field_mappings: list[dict[str, Any]] = []
    structured_criterion: dict[str, Any] | None = None
    review_status: str | None = None
    page_number: int | None = None
    source_section: str | None = None


class StructuredCriteriaResponse(BaseModel):
    """Paginated response for the criteria table."""

    items: list[StructuredCriterionRow]
    total: int
    page: int
    page_size: int
    pages: int


def _pick_grounding_code(ent: Entity) -> str | None:
    """Pick the first non-null grounding code from an entity."""
    return (
        ent.snomed_code
        or ent.umls_cui
        or ent.rxnorm_code
        or ent.icd10_code
        or ent.loinc_code
        or ent.hpo_code
    )


def _build_base_query():  # noqa: ANN202
    """Build base SELECT joining Criteria -> Batch -> Protocol."""
    return (
        select(Criteria, CriteriaBatch.protocol_id, Protocol.title)
        .join(
            CriteriaBatch,
            col(Criteria.batch_id) == col(CriteriaBatch.id),
        )
        .join(
            Protocol,
            col(CriteriaBatch.protocol_id) == col(Protocol.id),
        )
        .where(col(CriteriaBatch.is_archived) == False)  # noqa: E712
    )


def _apply_filters(query, *, criteria_type, category, protocol_id, min_confidence):  # noqa: ANN001, ANN202
    """Apply optional WHERE clauses to the query."""
    if criteria_type:
        query = query.where(col(Criteria.criteria_type) == criteria_type)
    if category:
        query = query.where(col(Criteria.category) == category)
    if protocol_id:
        query = query.where(col(CriteriaBatch.protocol_id) == protocol_id)
    if min_confidence is not None:
        query = query.where(col(Criteria.confidence) >= min_confidence)
    return query


def _load_entities(
    db: Session,
    criteria_ids: list[str],
) -> dict[str, list[EntitySummary]]:
    """Batch-load entities and group by criteria_id."""
    entities_q = select(Entity).where(col(Entity.criteria_id).in_(criteria_ids))
    entities = db.exec(entities_q).all()

    entity_map: dict[str, list[EntitySummary]] = {}
    for ent in entities:
        summary = EntitySummary(
            id=ent.id,
            entity_type=ent.entity_type,
            text=ent.text,
            grounding_code=_pick_grounding_code(ent),
            grounding_system=ent.grounding_system,
            preferred_term=ent.preferred_term,
            grounding_confidence=ent.grounding_confidence,
        )
        entity_map.setdefault(ent.criteria_id, []).append(summary)
    return entity_map


@router.get(
    "/structured",
    response_model=StructuredCriteriaResponse,
)
def get_structured_criteria(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    criteria_type: str | None = Query(None),
    category: str | None = Query(None),
    protocol_id: str | None = Query(None),
    min_confidence: float | None = Query(None, ge=0.0, le=1.0),
    sort_by: str = Query("confidence", pattern=_SORT_BY_PATTERN),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    has_grounding: bool | None = Query(None),
) -> StructuredCriteriaResponse:
    """Paginated, filterable, sortable structured criteria."""
    query = _build_base_query()
    query = _apply_filters(
        query,
        criteria_type=criteria_type,
        category=category,
        protocol_id=protocol_id,
        min_confidence=min_confidence,
    )

    # Count total
    count_q = select(func.count()).select_from(query.subquery())
    total = db.exec(count_q).one()

    # Sort
    sort_col = getattr(Criteria, sort_by, Criteria.confidence)
    if sort_order == "desc":
        query = query.order_by(col(sort_col).desc())
    else:
        query = query.order_by(col(sort_col).asc())

    # Paginate
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    results = db.exec(query).all()

    # Build response rows
    items: list[StructuredCriterionRow] = []
    criteria_ids: list[str] = []

    for row in results:
        criterion, proto_id, proto_title = row[0], row[1], row[2]
        criteria_ids.append(criterion.id)

        field_mappings: list[dict[str, Any]] = []
        conds = criterion.conditions
        if conds and isinstance(conds, dict):
            fm = conds.get("field_mappings", [])
            if isinstance(fm, list):
                field_mappings = fm

        items.append(
            StructuredCriterionRow(
                id=criterion.id,
                protocol_id=proto_id,
                protocol_title=proto_title,
                text=criterion.text,
                criteria_type=criterion.criteria_type,
                category=criterion.category,
                confidence=criterion.confidence,
                assertion_status=criterion.assertion_status,
                field_mappings=field_mappings,
                structured_criterion=criterion.structured_criterion,
                review_status=criterion.review_status,
                page_number=criterion.page_number,
                source_section=criterion.source_section,
            )
        )

    # Batch-load entities
    if criteria_ids:
        entity_map = _load_entities(db, criteria_ids)
        for item in items:
            item.entities = entity_map.get(item.id, [])

    # Filter by grounding post-query
    if has_grounding is not None:
        if has_grounding:
            items = [i for i in items if any(e.grounding_code for e in i.entities)]
        else:
            items = [i for i in items if not any(e.grounding_code for e in i.entities)]
        total = len(items)

    pages = max(1, (total + page_size - 1) // page_size)

    return StructuredCriteriaResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )
