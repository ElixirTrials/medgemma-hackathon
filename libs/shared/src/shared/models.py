"""Shared data models for the clinical trial criteria extraction system."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict
from uuid import uuid4

from sqlalchemy import JSON, Column, DateTime, String, Text, func
from sqlmodel import Field, SQLModel


def _ts_col() -> Column:  # type: ignore[type-arg]
    """Create a created_at timestamp column with server default."""
    return Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


def _ts_col_update() -> Column:  # type: ignore[type-arg]
    """Create an updated_at timestamp column with server default and onupdate."""
    return Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ProtocolStatus(str, Enum):
    """Protocol processing status enum."""

    UPLOADED = "uploaded"
    PENDING = "pending"
    EXTRACTING = "extracting"
    EXTRACTION_FAILED = "extraction_failed"
    GROUNDING = "grounding"
    GROUNDING_FAILED = "grounding_failed"
    PENDING_REVIEW = "pending_review"
    COMPLETE = "complete"
    DEAD_LETTER = "dead_letter"
    ARCHIVED = "archived"


class Protocol(SQLModel, table=True):
    """Uploaded clinical trial protocol PDF."""

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    title: str = Field()
    file_uri: str = Field()
    status: str = Field(default=ProtocolStatus.UPLOADED, index=True)
    page_count: int | None = Field(default=None)
    quality_score: float | None = Field(default=None)
    error_reason: str | None = Field(default=None)
    metadata_: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(sa_column=_ts_col())
    updated_at: datetime = Field(sa_column=_ts_col_update())


class CriteriaBatch(SQLModel, table=True):
    """A batch of criteria extracted from a protocol."""

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    protocol_id: str = Field(foreign_key="protocol.id", index=True)
    status: str = Field(default="pending_review", index=True)
    extraction_model: str | None = Field(default=None)
    created_at: datetime = Field(sa_column=_ts_col())
    updated_at: datetime = Field(sa_column=_ts_col_update())
    is_archived: bool = Field(default=False, index=True)


class Criteria(SQLModel, table=True):
    """Individual inclusion/exclusion criterion."""

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    batch_id: str = Field(foreign_key="criteriabatch.id", index=True)
    criteria_type: str = Field()
    category: str | None = Field(default=None)
    text: str = Field(sa_column=Column(Text, nullable=False))
    temporal_constraint: Dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON)
    )
    conditions: Dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    numeric_thresholds: Dict[str, Any] | None = Field(
        default=None, sa_column=Column(JSON)
    )
    assertion_status: str | None = Field(default=None)
    confidence: float = Field(default=1.0)
    source_section: str | None = Field(default=None)
    page_number: int | None = Field(default=None)
    review_status: str | None = Field(default=None)
    created_at: datetime = Field(sa_column=_ts_col())
    updated_at: datetime = Field(sa_column=_ts_col_update())


class Entity(SQLModel, table=True):
    """Medical entity extracted from criteria."""

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    criteria_id: str = Field(foreign_key="criteria.id", index=True)
    entity_type: str = Field(index=True)
    text: str = Field()
    span_start: int | None = Field(default=None)
    span_end: int | None = Field(default=None)
    umls_cui: str | None = Field(default=None)
    snomed_code: str | None = Field(default=None)
    preferred_term: str | None = Field(default=None)
    grounding_confidence: float | None = Field(default=None)
    grounding_method: str | None = Field(default=None)
    review_status: str | None = Field(default=None)
    context_window: Dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    # Multi-terminology code columns (Phase 32)
    rxnorm_code: str | None = Field(default=None, index=True)
    icd10_code: str | None = Field(default=None, index=True)
    loinc_code: str | None = Field(default=None, index=True)
    hpo_code: str | None = Field(default=None, index=True)
    grounding_system: str | None = Field(default=None)
    grounding_error: str | None = Field(default=None)
    # OMOP dual grounding columns (Phase 1a)
    omop_concept_id: str | None = Field(default=None, index=True)
    reconciliation_status: str | None = Field(default=None)
    created_at: datetime = Field(sa_column=_ts_col())
    updated_at: datetime = Field(sa_column=_ts_col_update())


class Review(SQLModel, table=True):
    """Human review action on a criteria or entity."""

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    reviewer_id: str = Field(index=True)
    target_type: str = Field()
    target_id: str = Field(index=True)
    action: str = Field()
    before_value: Dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    after_value: Dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    comment: str | None = Field(default=None)
    created_at: datetime = Field(sa_column=_ts_col())


class AuditLog(SQLModel, table=True):
    """Immutable log of all system events."""

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    event_type: str = Field(index=True)
    actor_id: str | None = Field(default=None, index=True)
    target_type: str | None = Field(default=None)
    target_id: str | None = Field(default=None)
    details: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(sa_column=_ts_col())


class User(SQLModel, table=True):
    """Authenticated user account."""

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    email: str = Field(
        sa_column=Column(String, unique=True, nullable=False, index=True)
    )
    name: str | None = Field(default=None)
    picture_url: str | None = Field(default=None)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(sa_column=_ts_col())
    updated_at: datetime = Field(sa_column=_ts_col_update())


class OutboxEvent(SQLModel, table=True):
    """Transactional outbox for event publishing."""

    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    event_type: str = Field(index=True)
    aggregate_type: str = Field()
    aggregate_id: str = Field(index=True)
    payload: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    idempotency_key: str = Field(sa_column=Column(String, unique=True, nullable=False))
    status: str = Field(default="pending", index=True)
    retry_count: int = Field(default=0)
    published_at: datetime | None = Field(default=None)
    created_at: datetime = Field(sa_column=_ts_col())
