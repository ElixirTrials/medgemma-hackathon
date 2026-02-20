"""Export endpoints for protocol criteria in standard formats.

Provides CIRCE (OHDSI), FHIR Group, and evaluation SQL exports
for protocols that have completed structured criteria processing.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlmodel import Session

from api_service.dependencies import get_db
from api_service.exporters import load_protocol_export_data
from api_service.exporters.circe_builder import build_circe_export
from api_service.exporters.evaluation_sql_builder import build_evaluation_sql
from api_service.exporters.fhir_group_builder import build_fhir_group_export

router = APIRouter(prefix="/protocols", tags=["exports"])


class ExportStats(BaseModel):
    """Summary statistics for an export."""

    criteria_count: int
    atomic_count: int
    composite_count: int
    relationship_count: int


class CirceExportResponse(BaseModel):
    """CIRCE CohortExpression export response."""

    expression: dict[str, Any]
    stats: ExportStats


class FhirGroupExportResponse(BaseModel):
    """FHIR Group resource export response."""

    resource: dict[str, Any]
    stats: ExportStats


def _get_export_data_or_404(db: Session, protocol_id: str):
    """Load export data or raise 404."""
    data = load_protocol_export_data(db, protocol_id)
    if data is None:
        raise HTTPException(
            status_code=404,
            detail=f"Protocol {protocol_id} not found or has no structured criteria",
        )
    return data


def _make_stats(data) -> ExportStats:
    """Build export stats from loaded data."""
    return ExportStats(
        criteria_count=len(data.criteria),
        atomic_count=len(data.atomics),
        composite_count=len(data.composites),
        relationship_count=len(data.relationships),
    )


@router.get(
    "/{protocol_id}/export/circe",
    response_model=CirceExportResponse,
)
def export_circe(
    protocol_id: str,
    db: Session = Depends(get_db),
) -> CirceExportResponse:
    """Export protocol criteria as OHDSI CIRCE CohortExpression JSON."""
    data = _get_export_data_or_404(db, protocol_id)
    expression = build_circe_export(data)
    return CirceExportResponse(
        expression=expression,
        stats=_make_stats(data),
    )


@router.get(
    "/{protocol_id}/export/fhir-group",
    response_model=FhirGroupExportResponse,
)
def export_fhir_group(
    protocol_id: str,
    db: Session = Depends(get_db),
) -> FhirGroupExportResponse:
    """Export protocol criteria as FHIR R4 Group resource."""
    data = _get_export_data_or_404(db, protocol_id)
    resource = build_fhir_group_export(data)
    return FhirGroupExportResponse(
        resource=resource,
        stats=_make_stats(data),
    )


@router.get(
    "/{protocol_id}/export/evaluation-sql",
    response_class=PlainTextResponse,
)
def export_evaluation_sql(
    protocol_id: str,
    db: Session = Depends(get_db),
) -> PlainTextResponse:
    """Export protocol criteria as OMOP CDM evaluation SQL."""
    data = _get_export_data_or_404(db, protocol_id)
    sql = build_evaluation_sql(data)
    return PlainTextResponse(content=sql, media_type="text/plain")
