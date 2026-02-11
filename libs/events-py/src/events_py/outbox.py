"""Outbox processor for publishing pending domain events.

Implements the transactional outbox pattern with at-least-once delivery.
The OutboxProcessor polls the outbox table for pending events and dispatches
them to registered handlers. The persist_with_outbox helper enables atomic
entity + event writes in a single database transaction.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

from shared.models import OutboxEvent
from sqlalchemy import Engine
from sqlmodel import Session, select

from events_py.models import DomainEventKind

logger = logging.getLogger(__name__)


class OutboxProcessor:
    """Processes pending outbox events with at-least-once delivery.

    Usage:
        processor = OutboxProcessor(engine, handlers={
            "protocol_uploaded": [handle_protocol_uploaded],
        })
        await processor.start()  # Runs polling loop
        await processor.stop()   # Graceful shutdown
    """

    def __init__(
        self,
        engine: Engine,
        handlers: dict[str, list[Callable[..., Any]]] | None = None,
        poll_interval: float = 1.0,
        batch_size: int = 100,
    ) -> None:
        """Initialize the outbox processor.

        Args:
            engine: SQLAlchemy database engine.
            handlers: Maps event_type string to handler callbacks.
            poll_interval: Seconds between polls.
            batch_size: Max events per poll cycle.
        """
        self.engine = engine
        self.handlers: dict[str, list[Callable[..., Any]]] = handlers or {}
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        self._shutdown_event = asyncio.Event()

    def poll_and_process(self) -> int:
        """Poll for pending events and process them.

        Returns:
            Number of events processed in this poll cycle.
        """
        processed = 0
        with Session(self.engine) as session:
            statement = (
                select(OutboxEvent)
                .where(OutboxEvent.status == "pending")
                .order_by(OutboxEvent.created_at.asc())  # type: ignore[attr-defined]
                .limit(self.batch_size)
            )

            # Use FOR UPDATE SKIP LOCKED on PostgreSQL
            # for concurrent processor safety
            db_url = str(self.engine.url)
            if "postgresql" in db_url:
                statement = statement.with_for_update(skip_locked=True)

            events = session.exec(statement).all()

            for event in events:
                event_handlers = self.handlers.get(event.event_type, [])

                if not event_handlers:
                    logger.debug(
                        "No handlers for event type: %s",
                        event.event_type,
                    )

                try:
                    for handler in event_handlers:
                        handler(event.payload)

                    event.status = "published"
                    event.published_at = datetime.now(timezone.utc)
                    session.add(event)
                    processed += 1

                    logger.info(
                        "Published event %s (type=%s)",
                        event.id,
                        event.event_type,
                    )
                except Exception:
                    event.status = "failed"
                    event.retry_count += 1
                    session.add(event)
                    logger.exception(
                        "Failed to process event %s (type=%s, retry_count=%d)",
                        event.id,
                        event.event_type,
                        event.retry_count,
                    )

            session.commit()

        return processed

    async def start(self) -> None:
        """Run the polling loop until stop() is called."""
        logger.info(
            "Outbox processor started (interval=%.1fs, batch_size=%d)",
            self.poll_interval,
            self.batch_size,
        )
        while not self._shutdown_event.is_set():
            try:
                count = await asyncio.get_event_loop().run_in_executor(
                    None, self.poll_and_process
                )
                if count > 0:
                    logger.info("Processed %d outbox events", count)
            except Exception:
                logger.exception("Error in outbox processor poll cycle")
            try:
                await asyncio.wait_for(
                    self._shutdown_event.wait(),
                    timeout=self.poll_interval,
                )
            except asyncio.TimeoutError:
                pass
        logger.info("Outbox processor stopped")

    async def stop(self) -> None:
        """Signal the processor to stop after current poll."""
        logger.info("Outbox processor shutdown requested")
        self._shutdown_event.set()


def persist_with_outbox(
    session: Session,
    entity: Any,
    event_type: DomainEventKind,
    aggregate_type: str,
    aggregate_id: str,
    payload: dict[str, Any],
    idempotency_key: str | None = None,
) -> OutboxEvent:
    """Persist an entity and its outbox event in the same transaction.

    The caller is responsible for committing the session.

    Args:
        session: Active SQLModel session (not yet committed).
        entity: The SQLModel entity to persist.
        event_type: Domain event kind.
        aggregate_type: Type of aggregate (e.g. "protocol").
        aggregate_id: ID of the affected aggregate.
        payload: Event payload dict.
        idempotency_key: Dedup key; auto-generated if omitted.

    Returns:
        The created OutboxEvent (uncommitted).
    """
    ikey = idempotency_key or (f"{event_type.value}:{aggregate_id}:{uuid4()}")

    outbox_event = OutboxEvent(
        event_type=event_type.value,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=payload,
        idempotency_key=ikey,
        status="pending",
    )

    session.add(entity)
    session.add(outbox_event)

    return outbox_event
