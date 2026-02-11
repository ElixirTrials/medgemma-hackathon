"""Unit tests for OutboxProcessor and persist_with_outbox.

Tests handler registration, event dispatch, error handling,
and transactional outbox persistence using in-memory SQLite.
"""

from unittest.mock import MagicMock

import pytest
from shared.models import OutboxEvent, Protocol
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel

from events_py.models import DomainEventKind
from events_py.outbox import OutboxProcessor, persist_with_outbox


@pytest.fixture()
def outbox_engine():
    """Create an in-memory SQLite engine with outbox tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def outbox_session(outbox_engine):
    """Create a session for outbox tests."""
    with Session(outbox_engine) as session:
        yield session


def _create_pending_event(
    session: Session,
    event_type: str = "protocol_uploaded",
    payload: dict | None = None,
) -> OutboxEvent:
    """Insert a pending outbox event and return it."""
    event = OutboxEvent(
        event_type=event_type,
        aggregate_type="protocol",
        aggregate_id="proto-001",
        payload=payload or {"file_uri": "gs://bucket/file.pdf"},
        idempotency_key=f"{event_type}:proto-001:{id(session)}",
        status="pending",
    )
    session.add(event)
    session.commit()
    session.refresh(event)
    return event


class TestOutboxProcessorInit:
    """Tests for OutboxProcessor initialization."""

    def test_stores_config(self, outbox_engine) -> None:
        processor = OutboxProcessor(
            engine=outbox_engine,
            poll_interval=2.0,
            batch_size=50,
        )
        assert processor.engine is outbox_engine
        assert processor.poll_interval == 2.0
        assert processor.batch_size == 50
        assert processor.handlers == {}

    def test_accepts_handlers(self, outbox_engine) -> None:
        handler = MagicMock()
        processor = OutboxProcessor(
            engine=outbox_engine,
            handlers={"test_event": [handler]},
        )
        assert "test_event" in processor.handlers
        assert processor.handlers["test_event"] == [handler]


class TestPollAndProcess:
    """Tests for OutboxProcessor.poll_and_process()."""

    def test_processes_pending_event(
        self, outbox_engine, outbox_session
    ) -> None:
        event = _create_pending_event(outbox_session)
        handler = MagicMock()

        processor = OutboxProcessor(
            engine=outbox_engine,
            handlers={"protocol_uploaded": [handler]},
        )
        count = processor.poll_and_process()

        assert count == 1
        handler.assert_called_once_with(event.payload)

        # Verify event status updated
        outbox_session.expire_all()
        refreshed = outbox_session.get(OutboxEvent, event.id)
        assert refreshed is not None
        assert refreshed.status == "published"
        assert refreshed.published_at is not None

    def test_dispatches_to_multiple_handlers(
        self, outbox_engine, outbox_session
    ) -> None:
        _create_pending_event(outbox_session)
        handler1 = MagicMock()
        handler2 = MagicMock()

        processor = OutboxProcessor(
            engine=outbox_engine,
            handlers={
                "protocol_uploaded": [handler1, handler2],
            },
        )
        count = processor.poll_and_process()

        assert count == 1
        handler1.assert_called_once()
        handler2.assert_called_once()

    def test_no_handlers_still_publishes_event(
        self, outbox_engine, outbox_session
    ) -> None:
        """When no handlers are registered, event is still marked published.

        The processor iterates an empty handler list (no-op), then
        marks the event as published since no exception occurred.
        """
        event = _create_pending_event(outbox_session)

        processor = OutboxProcessor(engine=outbox_engine)
        count = processor.poll_and_process()

        # Empty handler list -> try block succeeds -> published
        assert count == 1
        outbox_session.expire_all()
        refreshed = outbox_session.get(OutboxEvent, event.id)
        assert refreshed is not None
        assert refreshed.status == "published"

    def test_handler_exception_marks_event_failed(
        self, outbox_engine, outbox_session
    ) -> None:
        event = _create_pending_event(outbox_session)
        failing_handler = MagicMock(
            side_effect=RuntimeError("handler error")
        )

        processor = OutboxProcessor(
            engine=outbox_engine,
            handlers={"protocol_uploaded": [failing_handler]},
        )
        count = processor.poll_and_process()

        assert count == 0
        outbox_session.expire_all()
        refreshed = outbox_session.get(OutboxEvent, event.id)
        assert refreshed is not None
        assert refreshed.status == "failed"
        assert refreshed.retry_count == 1

    def test_sqlite_fallback_no_for_update(
        self, outbox_engine, outbox_session
    ) -> None:
        """SQLite does not support FOR UPDATE SKIP LOCKED.

        The processor should use the fallback path without error.
        """
        _create_pending_event(outbox_session)
        handler = MagicMock()

        processor = OutboxProcessor(
            engine=outbox_engine,
            handlers={"protocol_uploaded": [handler]},
        )
        # Should not raise -- SQLite fallback path
        count = processor.poll_and_process()
        assert count == 1


class TestPersistWithOutbox:
    """Tests for persist_with_outbox helper."""

    def test_adds_entity_and_event_to_session(
        self, outbox_engine, outbox_session
    ) -> None:
        protocol = Protocol(
            title="Test Protocol",
            file_uri="gs://bucket/test.pdf",
        )
        outbox_event = persist_with_outbox(
            session=outbox_session,
            entity=protocol,
            event_type=DomainEventKind.PROTOCOL_UPLOADED,
            aggregate_type="protocol",
            aggregate_id=protocol.id,
            payload={"file_uri": protocol.file_uri},
        )
        outbox_session.commit()

        assert outbox_event.event_type == "protocol_uploaded"
        assert outbox_event.aggregate_type == "protocol"
        assert outbox_event.status == "pending"
        assert outbox_event.idempotency_key is not None
        assert len(outbox_event.idempotency_key) > 0

        # Verify protocol was also persisted
        saved = outbox_session.get(Protocol, protocol.id)
        assert saved is not None
        assert saved.title == "Test Protocol"

    def test_generates_idempotency_key_when_not_provided(
        self, outbox_engine, outbox_session
    ) -> None:
        protocol = Protocol(
            title="Test", file_uri="gs://b/f.pdf"
        )
        event = persist_with_outbox(
            session=outbox_session,
            entity=protocol,
            event_type=DomainEventKind.PROTOCOL_UPLOADED,
            aggregate_type="protocol",
            aggregate_id=protocol.id,
            payload={},
        )
        assert event.idempotency_key.startswith(
            "protocol_uploaded:"
        )

    def test_uses_provided_idempotency_key(
        self, outbox_engine, outbox_session
    ) -> None:
        protocol = Protocol(
            title="Test", file_uri="gs://b/f.pdf"
        )
        event = persist_with_outbox(
            session=outbox_session,
            entity=protocol,
            event_type=DomainEventKind.PROTOCOL_UPLOADED,
            aggregate_type="protocol",
            aggregate_id=protocol.id,
            payload={},
            idempotency_key="custom-key-123",
        )
        assert event.idempotency_key == "custom-key-123"
