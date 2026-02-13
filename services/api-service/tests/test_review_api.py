"""Integration tests for review API (batches, criteria, action, pdf-url, audit-log)."""

from unittest.mock import patch

from shared.models import Criteria, CriteriaBatch, Protocol, Review
from sqlmodel import select


def _add_protocol(db_session, title: str = "Test Protocol") -> Protocol:
    p = Protocol(title=title, file_uri="gs://bucket/protocol.pdf")
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


def _add_batch(
    db_session, protocol_id: str, status: str = "pending_review"
) -> CriteriaBatch:
    b = CriteriaBatch(protocol_id=protocol_id, status=status)
    db_session.add(b)
    db_session.commit()
    db_session.refresh(b)
    return b


def _add_criterion(
    db_session,
    batch_id: str,
    text: str = "Criterion text",
    confidence: float = 0.8,
    review_status: str | None = None,
) -> Criteria:
    c = Criteria(
        batch_id=batch_id,
        criteria_type="inclusion",
        category="demographic",
        text=text,
        confidence=confidence,
        review_status=review_status,
    )
    db_session.add(c)
    db_session.commit()
    db_session.refresh(c)
    return c


class TestListBatches:
    """GET /reviews/batches."""

    def test_list_batches_pagination(self, test_client, db_session) -> None:
        p = _add_protocol(db_session)
        b = _add_batch(db_session, p.id)
        _add_criterion(db_session, b.id)
        r = test_client.get("/reviews/batches?page=1&page_size=20")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1
        assert len(data["items"]) >= 1
        assert data["items"][0]["protocol_title"] == "Test Protocol"
        assert data["items"][0]["criteria_count"] == 1
        assert "reviewed_count" in data["items"][0]

    def test_list_batches_status_filter(self, test_client, db_session) -> None:
        p = _add_protocol(db_session)
        _add_batch(db_session, p.id, status="pending_review")
        r = test_client.get("/reviews/batches?status=pending_review")
        assert r.status_code == 200
        assert r.json()["total"] >= 1

    def test_reviewed_count_excludes_null(self, test_client, db_session) -> None:
        p = _add_protocol(db_session)
        b = _add_batch(db_session, p.id)
        _add_criterion(db_session, b.id, review_status=None)
        _add_criterion(db_session, b.id, review_status="approved")
        r = test_client.get("/reviews/batches")
        assert r.status_code == 200
        items = r.json()["items"]
        batch_item = next((x for x in items if x["id"] == b.id), None)
        assert batch_item is not None
        assert batch_item["reviewed_count"] == 1


class TestListBatchCriteria:
    """GET /reviews/batches/{batch_id}/criteria."""

    def test_list_criteria_default_sort(self, test_client, db_session) -> None:
        p = _add_protocol(db_session)
        b = _add_batch(db_session, p.id)
        _add_criterion(db_session, b.id, confidence=0.5)
        _add_criterion(db_session, b.id, confidence=0.9)
        r = test_client.get(f"/reviews/batches/{b.id}/criteria")
        assert r.status_code == 200
        criteria = r.json()
        assert len(criteria) == 2
        assert criteria[0]["confidence"] <= criteria[1]["confidence"]

    def test_list_criteria_sort_desc(self, test_client, db_session) -> None:
        p = _add_protocol(db_session)
        b = _add_batch(db_session, p.id)
        _add_criterion(db_session, b.id)
        r = test_client.get(
            f"/reviews/batches/{b.id}/criteria?sort_by=created_at&sort_order=desc"
        )
        assert r.status_code == 200

    def test_list_criteria_404(self, test_client) -> None:
        r = test_client.get("/reviews/batches/unknown-id/criteria")
        assert r.status_code == 404


class TestSubmitReviewAction:
    """POST /reviews/criteria/{criteria_id}/action."""

    def test_approve_creates_review_and_audit(self, test_client, db_session) -> None:
        p = _add_protocol(db_session)
        b = _add_batch(db_session, p.id)
        c = _add_criterion(db_session, b.id)
        r = test_client.post(
            f"/reviews/criteria/{c.id}/action",
            json={"action": "approve", "reviewer_id": "user-1"},
        )
        assert r.status_code == 200
        assert r.json()["review_status"] == "approved"
        db_session.refresh(c)
        assert c.review_status == "approved"
        logs = db_session.exec(select(Review).where(Review.target_id == c.id)).all()
        assert len(logs) >= 1

    def test_reject_sets_status(self, test_client, db_session) -> None:
        p = _add_protocol(db_session)
        b = _add_batch(db_session, p.id)
        c = _add_criterion(db_session, b.id)
        r = test_client.post(
            f"/reviews/criteria/{c.id}/action",
            json={"action": "reject", "reviewer_id": "user-1"},
        )
        assert r.status_code == 200
        assert r.json()["review_status"] == "rejected"

    def test_modify_updates_text(self, test_client, db_session) -> None:
        p = _add_protocol(db_session)
        b = _add_batch(db_session, p.id)
        c = _add_criterion(db_session, b.id, text="Original")
        r = test_client.post(
            f"/reviews/criteria/{c.id}/action",
            json={
                "action": "modify",
                "reviewer_id": "user-1",
                "modified_text": "Updated text",
            },
        )
        assert r.status_code == 200
        assert r.json()["text"] == "Updated text"

    def test_action_404(self, test_client) -> None:
        r = test_client.post(
            "/reviews/criteria/unknown-id/action",
            json={"action": "approve", "reviewer_id": "user-1"},
        )
        assert r.status_code == 404


class TestGetPdfUrl:
    """GET /reviews/protocols/{protocol_id}/pdf-url."""

    def test_returns_signed_url(self, test_client, db_session) -> None:
        p = _add_protocol(db_session)
        with patch("api_service.reviews.generate_download_url") as m:
            m.return_value = "http://fake-pdf-url"
            r = test_client.get(f"/reviews/protocols/{p.id}/pdf-url")
        assert r.status_code == 200
        assert r.json()["url"] == "http://fake-pdf-url"
        assert r.json()["expires_in_minutes"] == 60

    def test_pdf_url_404(self, test_client) -> None:
        r = test_client.get("/reviews/protocols/unknown-id/pdf-url")
        assert r.status_code == 404


class TestAuditLog:
    """GET /reviews/audit-log."""

    def test_audit_log_pagination(self, test_client, db_session) -> None:
        r = test_client.get("/reviews/audit-log?page=1&page_size=50")
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert data["page"] == 1
        assert data["page_size"] == 50

    def test_audit_log_filter_by_target_type(self, test_client, db_session) -> None:
        r = test_client.get("/reviews/audit-log?target_type=criteria")
        assert r.status_code == 200

    def test_audit_log_empty(self, test_client) -> None:
        r = test_client.get("/reviews/audit-log")
        assert r.status_code == 200
        assert r.json()["items"] == [] or "items" in r.json()


class TestStructuredModify:
    """POST /reviews/criteria/{criteria_id}/action with structured fields."""

    def test_text_only_modify_still_works(self, test_client, db_session) -> None:
        """Backward compat: text-only modify without structured fields."""
        p = _add_protocol(db_session)
        b = _add_batch(db_session, p.id)
        c = _add_criterion(db_session, b.id, text="Original text")
        r = test_client.post(
            f"/reviews/criteria/{c.id}/action",
            json={
                "action": "modify",
                "reviewer_id": "user-1",
                "modified_text": "Updated text",
            },
        )
        assert r.status_code == 200
        assert r.json()["text"] == "Updated text"
        db_session.refresh(c)
        assert c.temporal_constraint is None
        assert c.numeric_thresholds is None
        assert c.conditions is None

    def test_structured_modify_temporal_constraint(
        self, test_client, db_session
    ) -> None:
        """Structured modify: temporal_constraint only."""
        p = _add_protocol(db_session)
        b = _add_batch(db_session, p.id)
        c = _add_criterion(db_session, b.id)
        temporal_data = {
            "duration": "6 months",
            "relation": "within",
            "reference_point": "screening",
        }
        r = test_client.post(
            f"/reviews/criteria/{c.id}/action",
            json={
                "action": "modify",
                "reviewer_id": "user-1",
                "modified_structured_fields": {"temporal_constraint": temporal_data},
            },
        )
        assert r.status_code == 200
        assert r.json()["temporal_constraint"] == temporal_data
        db_session.refresh(c)
        assert c.temporal_constraint == temporal_data

    def test_structured_modify_numeric_thresholds(
        self, test_client, db_session
    ) -> None:
        """Structured modify: numeric_thresholds only."""
        p = _add_protocol(db_session)
        b = _add_batch(db_session, p.id)
        c = _add_criterion(db_session, b.id)
        thresholds_data = {"value": 18.0, "unit": "years", "comparator": ">="}
        r = test_client.post(
            f"/reviews/criteria/{c.id}/action",
            json={
                "action": "modify",
                "reviewer_id": "user-1",
                "modified_structured_fields": {"numeric_thresholds": thresholds_data},
            },
        )
        assert r.status_code == 200
        assert r.json()["numeric_thresholds"] == thresholds_data
        db_session.refresh(c)
        assert c.numeric_thresholds == thresholds_data

    def test_structured_modify_conditions(self, test_client, db_session) -> None:
        """Structured modify: conditions only."""
        p = _add_protocol(db_session)
        b = _add_batch(db_session, p.id)
        c = _add_criterion(db_session, b.id)
        conditions_data = {"dependencies": ["if diabetic"]}
        r = test_client.post(
            f"/reviews/criteria/{c.id}/action",
            json={
                "action": "modify",
                "reviewer_id": "user-1",
                "modified_structured_fields": {"conditions": conditions_data},
            },
        )
        assert r.status_code == 200
        assert r.json()["conditions"] == conditions_data
        db_session.refresh(c)
        assert c.conditions == conditions_data

    def test_structured_modify_all_fields(self, test_client, db_session) -> None:
        """Structured modify: all three structured fields at once."""
        p = _add_protocol(db_session)
        b = _add_batch(db_session, p.id)
        c = _add_criterion(db_session, b.id)
        temporal_data = {"duration": "3 months", "relation": "after"}
        thresholds_data = {"value": 65.0, "unit": "years", "comparator": "<"}
        conditions_data = {"dependencies": ["if pregnant", "and not diabetic"]}
        r = test_client.post(
            f"/reviews/criteria/{c.id}/action",
            json={
                "action": "modify",
                "reviewer_id": "user-1",
                "modified_structured_fields": {
                    "temporal_constraint": temporal_data,
                    "numeric_thresholds": thresholds_data,
                    "conditions": conditions_data,
                },
            },
        )
        assert r.status_code == 200
        assert r.json()["temporal_constraint"] == temporal_data
        assert r.json()["numeric_thresholds"] == thresholds_data
        assert r.json()["conditions"] == conditions_data
        db_session.refresh(c)
        assert c.temporal_constraint == temporal_data
        assert c.numeric_thresholds == thresholds_data
        assert c.conditions == conditions_data

    def test_dual_write_text_and_structured(self, test_client, db_session) -> None:
        """Dual-write pattern: both text and structured fields in one request."""
        p = _add_protocol(db_session)
        b = _add_batch(db_session, p.id)
        c = _add_criterion(db_session, b.id, text="Original text")
        temporal_data = {"duration": "1 year", "relation": "within"}
        r = test_client.post(
            f"/reviews/criteria/{c.id}/action",
            json={
                "action": "modify",
                "reviewer_id": "user-1",
                "modified_text": "Updated text",
                "modified_structured_fields": {"temporal_constraint": temporal_data},
            },
        )
        assert r.status_code == 200
        assert r.json()["text"] == "Updated text"
        assert r.json()["temporal_constraint"] == temporal_data
        db_session.refresh(c)
        assert c.text == "Updated text"
        assert c.temporal_constraint == temporal_data

    def test_structured_modify_audit_log_schema_version(
        self, test_client, db_session
    ) -> None:
        """Audit log includes schema_version=structured_v1 for structured modify."""
        p = _add_protocol(db_session)
        b = _add_batch(db_session, p.id)
        c = _add_criterion(db_session, b.id)
        temporal_data = {"duration": "2 weeks", "relation": "before"}
        r = test_client.post(
            f"/reviews/criteria/{c.id}/action",
            json={
                "action": "modify",
                "reviewer_id": "user-1",
                "modified_structured_fields": {"temporal_constraint": temporal_data},
            },
        )
        assert r.status_code == 200
        audit_r = test_client.get(f"/reviews/audit-log?target_id={c.id}")
        assert audit_r.status_code == 200
        items = audit_r.json()["items"]
        assert len(items) >= 1
        log_entry = items[0]
        assert log_entry["details"]["schema_version"] == "structured_v1"

    def test_text_only_modify_audit_log_schema_version(
        self, test_client, db_session
    ) -> None:
        """Audit log includes schema_version=text_v1 for text-only modify."""
        p = _add_protocol(db_session)
        b = _add_batch(db_session, p.id)
        c = _add_criterion(db_session, b.id, text="Original")
        r = test_client.post(
            f"/reviews/criteria/{c.id}/action",
            json={
                "action": "modify",
                "reviewer_id": "user-1",
                "modified_text": "Updated",
            },
        )
        assert r.status_code == 200
        audit_r = test_client.get(f"/reviews/audit-log?target_id={c.id}")
        assert audit_r.status_code == 200
        items = audit_r.json()["items"]
        assert len(items) >= 1
        log_entry = items[0]
        assert log_entry["details"]["schema_version"] == "text_v1"

    def test_structured_modify_before_after_includes_structured(
        self, test_client, db_session
    ) -> None:
        """Audit log captures before/after values for structured fields."""
        p = _add_protocol(db_session)
        b = _add_batch(db_session, p.id)
        c = _add_criterion(db_session, b.id)
        # Set initial temporal_constraint
        c.temporal_constraint = {"duration": "old duration", "relation": "old"}
        db_session.add(c)
        db_session.commit()
        db_session.refresh(c)
        # Modify with new temporal_constraint
        new_temporal = {"duration": "new duration", "relation": "new"}
        r = test_client.post(
            f"/reviews/criteria/{c.id}/action",
            json={
                "action": "modify",
                "reviewer_id": "user-1",
                "modified_structured_fields": {"temporal_constraint": new_temporal},
            },
        )
        assert r.status_code == 200
        audit_r = test_client.get(f"/reviews/audit-log?target_id={c.id}")
        assert audit_r.status_code == 200
        items = audit_r.json()["items"]
        assert len(items) >= 1
        log_entry = items[0]
        before = log_entry["details"]["before_value"]
        after = log_entry["details"]["after_value"]
        assert before["temporal_constraint"] == {
            "duration": "old duration",
            "relation": "old",
        }
        assert after["temporal_constraint"] == new_temporal
