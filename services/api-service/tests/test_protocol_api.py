"""Integration tests for protocol API endpoints (upload, confirm, list, detail)."""

import base64
from unittest.mock import patch

from shared.models import Protocol
from sqlmodel import select


def _make_pdf_bytes() -> bytes:
    """Minimal valid PDF bytes for tests."""
    return (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R>>endobj\n"
        b"xref\n0 4\n0000000000 65535 f\n0000000009 00000 n\n"
        b"0000000052 00000 n\n0000000101 00000 n\n"
        b"trailer<</Size 4/Root 1 0 R>>\nstartxref\n178\n%%EOF"
    )


class TestUploadProtocol:
    """POST /protocols/upload."""

    def test_upload_returns_url_and_protocol_id(self, test_client, db_session) -> None:
        with patch("api_service.protocols.generate_upload_url") as m:
            m.return_value = (
                "http://fake-upload-url",
                "gs://bucket/protocols/test.pdf",
            )
            with patch("api_service.protocols.set_blob_metadata"):
                r = test_client.post(
                    "/protocols/upload",
                    json={
                        "filename": "test.pdf",
                        "content_type": "application/pdf",
                        "file_size_bytes": 1024,
                    },
                )
        assert r.status_code == 200
        data = r.json()
        assert "protocol_id" in data
        assert data["upload_url"] == "http://fake-upload-url"
        assert data["gcs_path"] == "gs://bucket/protocols/test.pdf"
        # Protocol created in DB
        protocols = db_session.exec(select(Protocol)).all()
        assert len(protocols) == 1
        assert protocols[0].status == "uploaded"

    def test_upload_rejects_non_pdf(self, test_client) -> None:
        r = test_client.post(
            "/protocols/upload",
            json={
                "filename": "test.txt",
                "content_type": "text/plain",
                "file_size_bytes": 100,
            },
        )
        assert r.status_code == 400
        assert "PDF" in r.json().get("detail", "")

    def test_upload_rejects_over_50mb(self, test_client) -> None:
        r = test_client.post(
            "/protocols/upload",
            json={
                "filename": "huge.pdf",
                "content_type": "application/pdf",
                "file_size_bytes": 51 * 1024 * 1024,
            },
        )
        assert r.status_code == 400
        assert "50MB" in r.json().get("detail", "")


class TestConfirmUpload:
    """POST /protocols/{id}/confirm-upload."""

    def test_confirm_with_pdf_sets_quality(self, test_client, db_session) -> None:
        with patch("api_service.protocols.generate_upload_url") as m:
            m.return_value = ("http://fake", "gs://b/f.pdf")
            with patch("api_service.protocols.set_blob_metadata"):
                r = test_client.post(
                    "/protocols/upload",
                    json={
                        "filename": "test.pdf",
                        "content_type": "application/pdf",
                        "file_size_bytes": 1024,
                    },
                )
        assert r.status_code == 200
        pid = r.json()["protocol_id"]
        pdf_b64 = base64.b64encode(_make_pdf_bytes()).decode()
        with patch("api_service.protocols.set_blob_metadata"):
            r2 = test_client.post(
                f"/protocols/{pid}/confirm-upload",
                json={"pdf_bytes_base64": pdf_b64},
            )
        assert r2.status_code == 200
        data = r2.json()
        assert data.get("quality_score") is not None
        assert data.get("page_count") is not None

    def test_confirm_without_pdf_updates_status_only(
        self, test_client, db_session
    ) -> None:
        with patch("api_service.protocols.generate_upload_url") as m:
            m.return_value = ("http://fake", "gs://b/f.pdf")
            with patch("api_service.protocols.set_blob_metadata"):
                r = test_client.post(
                    "/protocols/upload",
                    json={
                        "filename": "test.pdf",
                        "content_type": "application/pdf",
                        "file_size_bytes": 1024,
                    },
                )
        pid = r.json()["protocol_id"]
        r2 = test_client.post(
            f"/protocols/{pid}/confirm-upload",
            json={"pdf_bytes_base64": None},
        )
        assert r2.status_code == 200
        # Quality may remain None if no pdf_bytes_base64
        assert r2.json().get("id") == pid

    def test_confirm_404_for_unknown_protocol(self, test_client) -> None:
        r = test_client.post(
            "/protocols/unknown-id/confirm-upload",
            json={"pdf_bytes_base64": None},
        )
        assert r.status_code == 404


class TestListProtocols:
    """GET /protocols."""

    def test_list_pagination(self, test_client, db_session) -> None:
        for i in range(3):
            p = Protocol(
                title=f"Protocol {i}",
                file_uri=f"gs://b/p{i}.pdf",
            )
            db_session.add(p)
        db_session.commit()
        r = test_client.get("/protocols?page=1&page_size=20")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert data["pages"] == 1

    def test_list_status_filter(self, test_client, db_session) -> None:
        p1 = Protocol(title="A", file_uri="gs://b/a.pdf", status="uploaded")
        p2 = Protocol(title="B", file_uri="gs://b/b.pdf", status="extracting")
        db_session.add_all([p1, p2])
        db_session.commit()
        r = test_client.get("/protocols?status=uploaded")
        assert r.status_code == 200
        assert r.json()["total"] == 1
        assert r.json()["items"][0]["status"] == "uploaded"

    def test_list_empty_returns_pages_one(self, test_client) -> None:
        r = test_client.get("/protocols")
        assert r.status_code == 200
        assert r.json()["items"] == []
        assert r.json()["pages"] == 1


class TestGetProtocol:
    """GET /protocols/{protocol_id}."""

    def test_get_existing_protocol(self, test_client, db_session) -> None:
        p = Protocol(title="Trial", file_uri="gs://b/f.pdf")
        db_session.add(p)
        db_session.commit()
        r = test_client.get(f"/protocols/{p.id}")
        assert r.status_code == 200
        data = r.json()
        assert data["id"] == p.id
        assert data["title"] == "Trial"
        assert data["file_uri"] == "gs://b/f.pdf"
        assert "created_at" in data
        assert "updated_at" in data

    def test_get_404_for_unknown(self, test_client) -> None:
        r = test_client.get("/protocols/unknown-id")
        assert r.status_code == 404
