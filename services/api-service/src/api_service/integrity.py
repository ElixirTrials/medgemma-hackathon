"""FastAPI router for data integrity checks.

Provides a read-only endpoint that detects data quality issues across
the criteria extraction pipeline:
- Orphaned entities (FK violations)
- Incomplete audit logs (missing before_value/after_value)
- Ungrounded entities (no codes AND no error recorded)
- Reviews without audit trail

All checks are READ-ONLY -- this module never modifies data.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from shared.models import AuditLog, Criteria, CriteriaBatch, Entity
from sqlmodel import Session, col, select

from api_service.dependencies import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrity", tags=["integrity"])


# --- Response models ---

_IssueCategory = Literal[
    "criteria_state", "audit_log", "entity_grounding", "orphaned_entity"
]


class IntegrityIssue(BaseModel):
    """A single data integrity issue found during the check."""

    category: _IssueCategory
    severity: Literal["error", "warning"]
    description: str
    affected_id: str | None


class IntegrityCheckResponse(BaseModel):
    """Full result of an integrity check run."""

    protocol_id: str | None
    checked_at: datetime
    issues: list[IntegrityIssue]
    summary: dict[str, int]
    passed: bool


# --- Scoping helper ---


def _get_scoped_criteria_ids(db: Session, protocol_id: str) -> list[str] | None:
    """Return criteria IDs scoped to a protocol, or None if unscoped.

    Returns an empty list if the protocol has no batches/criteria.
    Returns None when protocol_id is not provided (unscoped).
    """
    batch_stmt = select(CriteriaBatch).where(CriteriaBatch.protocol_id == protocol_id)
    batches = db.exec(batch_stmt).all()
    batch_ids = [b.id for b in batches]

    if not batch_ids:
        return []

    criteria_stmt = select(Criteria).where(col(Criteria.batch_id).in_(batch_ids))
    scoped = db.exec(criteria_stmt).all()
    return [c.id for c in scoped]


# --- Individual check functions ---


def _check_orphaned_entities(
    db: Session, scoped_criteria_ids: list[str] | None
) -> list[IntegrityIssue]:
    """Check 1 (orphaned_entity, error): Entity rows with no matching Criteria row."""
    stmt = select(Entity).where(~col(Entity.criteria_id).in_(select(col(Criteria.id))))
    if scoped_criteria_ids is not None:
        if not scoped_criteria_ids:
            return []
        stmt = stmt.where(col(Entity.criteria_id).in_(scoped_criteria_ids))

    issues = []
    for entity in db.exec(stmt).all():
        issues.append(
            IntegrityIssue(
                category="orphaned_entity",
                severity="error",
                description=(
                    f"Entity {entity.id!r} references criteria_id "
                    f"{entity.criteria_id!r} which does not exist "
                    "in the Criteria table (FK violation)"
                ),
                affected_id=entity.id,
            )
        )
    return issues


def _check_incomplete_audit_logs(
    db: Session, scoped_criteria_ids: list[str] | None
) -> list[IntegrityIssue]:
    """Check 2 (audit_log, warning): review_action entries missing keys."""
    stmt = select(AuditLog).where(AuditLog.event_type == "review_action")
    if scoped_criteria_ids is not None:
        if not scoped_criteria_ids:
            return []
        stmt = stmt.where(col(AuditLog.target_id).in_(scoped_criteria_ids))

    issues = []
    for entry in db.exec(stmt).all():
        details = entry.details or {}
        missing = [k for k in ("before_value", "after_value") if k not in details]
        if missing:
            issues.append(
                IntegrityIssue(
                    category="audit_log",
                    severity="warning",
                    description=(
                        f"AuditLog {entry.id!r} "
                        f"(target_id={entry.target_id!r}) "
                        f"is missing required keys: {missing}"
                    ),
                    affected_id=entry.id,
                )
            )
    return issues


def _check_ungrounded_entities(
    db: Session, scoped_criteria_ids: list[str] | None
) -> list[IntegrityIssue]:
    """Check 3 (entity_grounding, warning): Entities with no codes and no error."""
    stmt = select(Entity).where(
        col(Entity.umls_cui).is_(None),
        col(Entity.snomed_code).is_(None),
        col(Entity.grounding_error).is_(None),
    )
    if scoped_criteria_ids is not None:
        if not scoped_criteria_ids:
            return []
        stmt = stmt.where(col(Entity.criteria_id).in_(scoped_criteria_ids))

    issues = []
    for entity in db.exec(stmt).all():
        issues.append(
            IntegrityIssue(
                category="entity_grounding",
                severity="warning",
                description=(
                    f"Entity {entity.id!r} ({entity.text!r}) has no "
                    "UMLS CUI, no SNOMED code, and no grounding_error "
                    "-- grounding may have silently failed"
                ),
                affected_id=entity.id,
            )
        )
    return issues


def _check_reviews_without_audit(
    db: Session, scoped_criteria_ids: list[str] | None
) -> list[IntegrityIssue]:
    """Check 4 (criteria_state, warning): Reviewed criteria with no AuditLog."""
    stmt = select(Criteria).where(col(Criteria.review_status).isnot(None))
    if scoped_criteria_ids is not None:
        if not scoped_criteria_ids:
            return []
        stmt = stmt.where(col(Criteria.id).in_(scoped_criteria_ids))

    issues = []
    for criterion in db.exec(stmt).all():
        audit_stmt = select(AuditLog).where(
            AuditLog.target_type == "criteria",
            AuditLog.target_id == criterion.id,
        )
        if db.exec(audit_stmt).first() is None:
            issues.append(
                IntegrityIssue(
                    category="criteria_state",
                    severity="warning",
                    description=(
                        f"Criteria {criterion.id!r} has "
                        f"review_status={criterion.review_status!r} "
                        "but no corresponding AuditLog entry "
                        "(review without audit trail)"
                    ),
                    affected_id=criterion.id,
                )
            )
    return issues


# --- Endpoint ---


@router.get("/check", response_model=IntegrityCheckResponse)
def check_integrity(
    protocol_id: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> IntegrityCheckResponse:
    """Run all data integrity checks and return a structured issue list.

    Optionally scope checks to a single protocol via protocol_id.
    Checks performed (all READ-ONLY):
    1. orphaned_entity (error): Entity rows with no matching Criteria
    2. audit_log (warning): review_action entries missing keys
    3. entity_grounding (warning): Entities with no codes and no error
    4. criteria_state (warning): Reviewed criteria with no AuditLog
    """
    scoped_criteria_ids: list[str] | None = None
    if protocol_id is not None:
        scoped_criteria_ids = _get_scoped_criteria_ids(db, protocol_id)

    issues: list[IntegrityIssue] = []
    issues.extend(_check_orphaned_entities(db, scoped_criteria_ids))
    issues.extend(_check_incomplete_audit_logs(db, scoped_criteria_ids))
    issues.extend(_check_ungrounded_entities(db, scoped_criteria_ids))
    issues.extend(_check_reviews_without_audit(db, scoped_criteria_ids))

    summary: dict[str, int] = {}
    for issue in issues:
        summary[issue.category] = summary.get(issue.category, 0) + 1

    return IntegrityCheckResponse(
        protocol_id=protocol_id,
        checked_at=datetime.now(tz=timezone.utc),
        issues=issues,
        summary=summary,
        passed=len(issues) == 0,
    )
