"""Tests for the data integrity check endpoint.

Tests cover:
- Detection of each issue category (orphaned entity, incomplete audit log,
  ungrounded entity, review without audit trail)
- Clean DB baseline (passed=True, issues=[])
- Protocol-scoped checks (issues in protocol A don't affect protocol B check)
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from shared.models import AuditLog, Criteria, CriteriaBatch, Entity, Protocol

# --- Helpers ---


def _make_protocol(db_session, title: str = "Test Protocol") -> Protocol:
    """Create and persist a Protocol for testing."""
    protocol = Protocol(title=title, file_uri="gs://test/protocol.pdf")
    db_session.add(protocol)
    db_session.commit()
    db_session.refresh(protocol)
    return protocol


def _make_batch(
    db_session, protocol_id: str, status: str = "pending_review"
) -> CriteriaBatch:
    """Create and persist a CriteriaBatch for testing."""
    batch = CriteriaBatch(protocol_id=protocol_id, status=status)
    db_session.add(batch)
    db_session.commit()
    db_session.refresh(batch)
    return batch


def _make_criteria(
    db_session,
    batch_id: str,
    review_status: str | None = None,
    text: str = "Patient must be >= 18 years old",
) -> Criteria:
    """Create and persist a Criteria for testing."""
    criterion = Criteria(
        batch_id=batch_id,
        criteria_type="inclusion",
        text=text,
        review_status=review_status,
    )
    db_session.add(criterion)
    db_session.commit()
    db_session.refresh(criterion)
    return criterion


def _make_entity(
    db_session,
    criteria_id: str,
    umls_cui: str | None = "C0001234",
    snomed_code: str | None = None,
    grounding_error: str | None = None,
) -> Entity:
    """Create and persist an Entity for testing."""
    entity = Entity(
        criteria_id=criteria_id,
        entity_type="Condition",
        text="test condition",
        umls_cui=umls_cui,
        snomed_code=snomed_code,
        grounding_error=grounding_error,
    )
    db_session.add(entity)
    db_session.commit()
    db_session.refresh(entity)
    return entity


def _make_audit_log(
    db_session,
    target_id: str,
    target_type: str = "criteria",
    event_type: str = "review_action",
    details: dict | None = None,
) -> AuditLog:
    """Create and persist an AuditLog for testing."""
    if details is None:
        details = {
            "action": "approve",
            "before_value": {"text": "original"},
            "after_value": None,
        }
    log = AuditLog(
        event_type=event_type,
        actor_id="test-user",
        target_type=target_type,
        target_id=target_id,
        details=details,
    )
    db_session.add(log)
    db_session.commit()
    db_session.refresh(log)
    return log


# --- Detection tests ---


class TestIntegrityDetection:
    """Tests that each issue category is correctly detected."""

    def test_detects_orphaned_entity(self, test_client: TestClient, db_session) -> None:
        """Entity with non-existent criteria_id is flagged as orphaned_entity error."""
        # Create entity with a made-up criteria_id (no corresponding Criteria row)
        orphan = Entity(
            criteria_id="nonexistent-criteria-id-000",
            entity_type="Condition",
            text="orphaned entity",
        )
        db_session.add(orphan)
        db_session.commit()

        response = test_client.get("/integrity/check")
        assert response.status_code == 200
        data = response.json()

        orphan_issues = [
            i for i in data["issues"] if i["category"] == "orphaned_entity"
        ]
        assert len(orphan_issues) == 1
        assert orphan_issues[0]["severity"] == "error"
        assert orphan_issues[0]["affected_id"] == orphan.id
        assert data["passed"] is False
        assert data["summary"].get("orphaned_entity") == 1

    def test_detects_missing_audit_before_after(
        self, test_client: TestClient, db_session
    ) -> None:
        """AuditLog review_action missing before/after_value flagged as audit_log."""
        protocol = _make_protocol(db_session)
        batch = _make_batch(db_session, protocol.id)
        criterion = _make_criteria(db_session, batch.id)

        # Create audit log missing before_value and after_value
        _make_audit_log(
            db_session,
            target_id=criterion.id,
            event_type="review_action",
            details={"action": "modify"},  # missing before_value and after_value
        )

        response = test_client.get("/integrity/check")
        assert response.status_code == 200
        data = response.json()

        audit_issues = [i for i in data["issues"] if i["category"] == "audit_log"]
        assert len(audit_issues) == 1
        assert audit_issues[0]["severity"] == "warning"
        assert data["passed"] is False
        assert data["summary"].get("audit_log") == 1

    def test_detects_ungrounded_entity(
        self, test_client: TestClient, db_session
    ) -> None:
        """Entity with no codes and no grounding_error flagged as entity_grounding."""
        protocol = _make_protocol(db_session)
        batch = _make_batch(db_session, protocol.id)
        criterion = _make_criteria(db_session, batch.id)

        # Entity with no codes and no error — silently failed grounding
        _make_entity(
            db_session,
            criteria_id=criterion.id,
            umls_cui=None,
            snomed_code=None,
            grounding_error=None,
        )

        response = test_client.get("/integrity/check")
        assert response.status_code == 200
        data = response.json()

        grounding_issues = [
            i for i in data["issues"] if i["category"] == "entity_grounding"
        ]
        assert len(grounding_issues) == 1
        assert grounding_issues[0]["severity"] == "warning"
        assert data["passed"] is False
        assert data["summary"].get("entity_grounding") == 1

    def test_detects_review_without_audit(
        self, test_client: TestClient, db_session
    ) -> None:
        """Criteria with review_status but no AuditLog flagged as criteria_state."""
        protocol = _make_protocol(db_session)
        batch = _make_batch(db_session, protocol.id)

        # Criteria marked as approved but with no AuditLog entry
        criterion = _make_criteria(db_session, batch.id, review_status="approved")
        # Deliberately do NOT create an AuditLog entry

        response = test_client.get("/integrity/check")
        assert response.status_code == 200
        data = response.json()

        state_issues = [i for i in data["issues"] if i["category"] == "criteria_state"]
        assert len(state_issues) == 1
        assert state_issues[0]["severity"] == "warning"
        assert state_issues[0]["affected_id"] == criterion.id
        assert data["passed"] is False
        assert data["summary"].get("criteria_state") == 1


# --- Baseline tests ---


class TestIntegrityBaseline:
    """Tests for clean-DB baseline and protocol scoping."""

    def test_clean_db_passes(self, test_client: TestClient) -> None:
        """Empty database returns passed=True with no issues."""
        response = test_client.get("/integrity/check")
        assert response.status_code == 200
        data = response.json()

        assert data["passed"] is True
        assert data["issues"] == []
        assert data["summary"] == {}
        assert data["protocol_id"] is None

    def test_protocol_scope(self, test_client: TestClient, db_session) -> None:
        """Issues in protocol A are not visible when checking protocol B."""
        # Protocol A: has an ungrounded entity (creates issue)
        protocol_a = _make_protocol(db_session, title="Protocol A")
        batch_a = _make_batch(db_session, protocol_a.id)
        criterion_a = _make_criteria(db_session, batch_a.id)
        _make_entity(
            db_session,
            criteria_id=criterion_a.id,
            umls_cui=None,
            snomed_code=None,
            grounding_error=None,
        )

        # Protocol B: clean data (grounded entity)
        protocol_b = _make_protocol(db_session, title="Protocol B")
        batch_b = _make_batch(db_session, protocol_b.id)
        criterion_b = _make_criteria(db_session, batch_b.id)
        _make_entity(
            db_session,
            criteria_id=criterion_b.id,
            umls_cui="C0001234",  # grounded — clean
        )

        # Scoped check for protocol B should pass
        response = test_client.get(f"/integrity/check?protocol_id={protocol_b.id}")
        assert response.status_code == 200
        data = response.json()

        assert data["passed"] is True
        assert data["issues"] == []
        assert data["protocol_id"] == protocol_b.id

        # Unscoped check or protocol A check should see the issue
        response_a = test_client.get(f"/integrity/check?protocol_id={protocol_a.id}")
        assert response_a.status_code == 200
        data_a = response_a.json()
        assert data_a["passed"] is False
        assert len(data_a["issues"]) == 1
        assert data_a["issues"][0]["category"] == "entity_grounding"
