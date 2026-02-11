"""Event envelope and kind definitions."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, TypedDict
from uuid import uuid4


class EventKind(str, Enum):
    """Supported event kinds."""

    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"


class DomainEventKind(str, Enum):
    """Domain-specific event types for the clinical trial pipeline."""

    PROTOCOL_UPLOADED = "protocol_uploaded"
    CRITERIA_EXTRACTED = "criteria_extracted"
    REVIEW_COMPLETED = "review_completed"
    ENTITIES_GROUNDED = "entities_grounded"


class EventEnvelope(TypedDict, total=True):
    """Base event envelope for Pub/Sub or internal events."""

    id: str
    kind: Literal["created", "updated", "deleted"]
    payload: Any
    timestamp: str


class DomainEventEnvelope(TypedDict, total=True):
    """Domain event envelope for transactional outbox pattern."""

    id: str
    event_type: str  # DomainEventKind value
    aggregate_type: str
    aggregate_id: str
    payload: Any
    idempotency_key: str
    timestamp: str


def create_event(
    kind: EventKind,
    payload: Any,
    event_id: str | None = None,
) -> EventEnvelope:
    """Create an event envelope.

    Args:
        kind: Event kind (created, updated, deleted).
        payload: Event payload (must be JSON-serializable).
        event_id: Optional ID; if omitted, a UUID is generated.

    Returns:
        Event envelope dict.

    Example:
        >>> from events_py import EventKind, create_event
        >>> ev = create_event(EventKind.CREATED, {"name": "foo"})
        >>> ev["kind"]
        'created'
    """
    return {
        "id": event_id or str(uuid4()),
        "kind": kind.value,
        "payload": payload,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def create_domain_event(
    event_type: DomainEventKind,
    aggregate_type: str,
    aggregate_id: str,
    payload: Any,
    idempotency_key: str | None = None,
    event_id: str | None = None,
) -> DomainEventEnvelope:
    """Create a domain event envelope for the transactional outbox.

    Args:
        event_type: Domain event kind.
        aggregate_type: Type of aggregate (e.g. "protocol").
        aggregate_id: ID of the affected aggregate.
        payload: Event payload (must be JSON-serializable).
        idempotency_key: Optional dedup key; auto-generated if
            omitted.
        event_id: Optional event ID; auto-generated if omitted.

    Returns:
        Domain event envelope dict.
    """
    eid = event_id or str(uuid4())
    ikey = idempotency_key or (f"{event_type.value}:{aggregate_id}:{uuid4()}")
    return {
        "id": eid,
        "event_type": event_type.value,
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "payload": payload,
        "idempotency_key": ikey,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
