"""Unit tests for shared SQLModel data models.

Tests model instantiation, field defaults, and JSON column behavior
without database persistence (in-memory only).
"""

from shared.models import (
    AuditLog,
    Criteria,
    CriteriaBatch,
    Entity,
    OutboxEvent,
    Protocol,
    Review,
)


class TestProtocolModel:
    """Tests for Protocol SQLModel."""

    def test_instantiation_with_required_fields(self) -> None:
        p = Protocol(title="Phase III Diabetes Trial", file_uri="gs://bucket/file.pdf")
        assert p.title == "Phase III Diabetes Trial"
        assert p.file_uri == "gs://bucket/file.pdf"

    def test_id_auto_generated(self) -> None:
        p = Protocol(title="Test", file_uri="gs://b/f.pdf")
        assert p.id is not None
        assert len(p.id) > 0

    def test_default_status(self) -> None:
        p = Protocol(title="Test", file_uri="gs://b/f.pdf")
        assert p.status == "uploaded"

    def test_optional_fields_default_none(self) -> None:
        p = Protocol(title="Test", file_uri="gs://b/f.pdf")
        assert p.page_count is None
        assert p.quality_score is None

    def test_metadata_defaults_to_empty_dict(self) -> None:
        p = Protocol(title="Test", file_uri="gs://b/f.pdf")
        assert p.metadata_ == {}


class TestCriteriaBatchModel:
    """Tests for CriteriaBatch SQLModel."""

    def test_instantiation(self) -> None:
        cb = CriteriaBatch(protocol_id="proto-001")
        assert cb.protocol_id == "proto-001"
        assert cb.id is not None

    def test_default_status(self) -> None:
        cb = CriteriaBatch(protocol_id="proto-001")
        assert cb.status == "pending_review"

    def test_extraction_model_default_none(self) -> None:
        cb = CriteriaBatch(protocol_id="proto-001")
        assert cb.extraction_model is None


class TestCriteriaModel:
    """Tests for Criteria SQLModel."""

    def test_instantiation_with_required_fields(self) -> None:
        c = Criteria(
            batch_id="batch-001",
            criteria_type="inclusion",
            text="Age >= 18 years",
            confidence=0.95,
        )
        assert c.batch_id == "batch-001"
        assert c.criteria_type == "inclusion"
        assert c.text == "Age >= 18 years"
        assert c.confidence == 0.95

    def test_json_fields_default_none(self) -> None:
        c = Criteria(
            batch_id="batch-001",
            criteria_type="inclusion",
            text="test",
        )
        assert c.temporal_constraint is None
        assert c.conditions is None
        assert c.numeric_thresholds is None

    def test_json_fields_accept_dicts(self) -> None:
        c = Criteria(
            batch_id="batch-001",
            criteria_type="exclusion",
            text="HbA1c < 8%",
            temporal_constraint={"duration": "30 days", "relation": "within"},
            conditions={"deps": ["if diabetic"]},
            numeric_thresholds={"thresholds": [{"value": 8.0, "unit": "%"}]},
        )
        assert c.temporal_constraint is not None
        assert c.conditions is not None
        assert c.numeric_thresholds is not None


class TestEntityModel:
    """Tests for Entity SQLModel."""

    def test_instantiation(self) -> None:
        e = Entity(
            criteria_id="crit-001",
            entity_type="Condition",
            text="diabetes mellitus",
        )
        assert e.criteria_id == "crit-001"
        assert e.entity_type == "Condition"
        assert e.text == "diabetes mellitus"
        assert e.id is not None

    def test_umls_fields_default_none(self) -> None:
        e = Entity(
            criteria_id="crit-001",
            entity_type="Medication",
            text="metformin",
        )
        assert e.umls_cui is None
        assert e.snomed_code is None
        assert e.preferred_term is None
        assert e.grounding_confidence is None
        assert e.grounding_method is None

    def test_context_window_accepts_dict(self) -> None:
        e = Entity(
            criteria_id="crit-001",
            entity_type="Condition",
            text="test",
            context_window={"text": "Patient has test condition"},
        )
        assert e.context_window == {"text": "Patient has test condition"}


class TestReviewModel:
    """Tests for Review SQLModel."""

    def test_instantiation(self) -> None:
        r = Review(
            reviewer_id="user-001",
            target_type="criteria",
            target_id="crit-001",
            action="approve",
        )
        assert r.reviewer_id == "user-001"
        assert r.target_type == "criteria"
        assert r.action == "approve"
        assert r.id is not None

    def test_json_fields_accept_dicts(self) -> None:
        r = Review(
            reviewer_id="user-001",
            target_type="entity",
            target_id="ent-001",
            action="edit",
            before_value={"text": "old value"},
            after_value={"text": "new value"},
        )
        assert r.before_value == {"text": "old value"}
        assert r.after_value == {"text": "new value"}

    def test_optional_comment(self) -> None:
        r = Review(
            reviewer_id="user-001",
            target_type="criteria",
            target_id="crit-001",
            action="reject",
            comment="Not a valid criterion",
        )
        assert r.comment == "Not a valid criterion"


class TestAuditLogModel:
    """Tests for AuditLog SQLModel."""

    def test_instantiation(self) -> None:
        al = AuditLog(
            event_type="criteria_extracted",
            details={"batch_id": "batch-001", "count": 5},
        )
        assert al.event_type == "criteria_extracted"
        assert al.details == {"batch_id": "batch-001", "count": 5}
        assert al.id is not None

    def test_actor_id_optional(self) -> None:
        al = AuditLog(event_type="system_event")
        assert al.actor_id is None


class TestOutboxEventModel:
    """Tests for OutboxEvent SQLModel."""

    def test_instantiation(self) -> None:
        oe = OutboxEvent(
            event_type="protocol_uploaded",
            aggregate_type="protocol",
            aggregate_id="proto-001",
            payload={"file_uri": "gs://bucket/file.pdf"},
            idempotency_key="protocol_uploaded:proto-001:unique-key",
        )
        assert oe.event_type == "protocol_uploaded"
        assert oe.aggregate_type == "protocol"
        assert oe.aggregate_id == "proto-001"
        assert oe.payload == {"file_uri": "gs://bucket/file.pdf"}

    def test_default_status_pending(self) -> None:
        oe = OutboxEvent(
            event_type="test",
            aggregate_type="test",
            aggregate_id="t-001",
            payload={},
            idempotency_key="test:t-001:1",
        )
        assert oe.status == "pending"
        assert oe.retry_count == 0
        assert oe.published_at is None
