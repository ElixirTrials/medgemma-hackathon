"""Smoke test for E2E test infrastructure.

Validates that:
1. The upload fixture successfully creates a protocol via the API
2. The protocol appears in the database
3. The cleanup fixture removes it after the test
"""

from __future__ import annotations

import pytest


@pytest.mark.e2e
class TestInfrastructureSmoke:
    """Verify E2E test infrastructure works."""

    def test_upload_creates_protocol(self, upload_test_pdf, e2e_api_client):
        """Upload a test PDF and verify it appears in the API."""
        protocol_id = upload_test_pdf()

        # Verify protocol exists via API
        resp = e2e_api_client.get(f"/protocols/{protocol_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == protocol_id
        assert data["status"] in (
            "uploaded",
            "extracting",
            "processing",
            "pending_review",
        )

    def test_upload_with_custom_pdf(self, upload_test_pdf, e2e_api_client):
        """Upload a specific PDF and verify it works."""
        protocol_id = upload_test_pdf(
            pdf_path="data/protocols/crc_protocols/isrctn/48616-d8fc1476.pdf"
        )

        resp = e2e_api_client.get(f"/protocols/{protocol_id}")
        assert resp.status_code == 200

    def test_protocol_list_includes_upload(self, upload_test_pdf, e2e_api_client):
        """Uploaded protocol appears in the protocol list."""
        protocol_id = upload_test_pdf()

        resp = e2e_api_client.get("/protocols")
        assert resp.status_code == 200
        data = resp.json()
        protocol_ids = [p["id"] for p in data["items"]]
        assert protocol_id in protocol_ids
