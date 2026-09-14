"""API tests for document upload, list, get, and delete."""

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Document, DocumentChunk
from tests.fixtures.pdf_gen import corrupt_pdf_bytes, sample_pdf_bytes

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture(autouse=True)
def isolated_uploads(tmp_path, monkeypatch):
    """Route every upload to a throwaway directory so no real data leaks."""
    monkeypatch.setattr(get_settings(), "upload_dir", tmp_path / "uploads")


def _upload(client, name: str, data: bytes, content_type: str):
    files = {"file": (name, data, content_type)}
    return client.post("/api/documents/upload", files=files)


class TestUpload:
    def test_upload_valid_pdf(self, client):
        resp = _upload(client, "plan.pdf", sample_pdf_bytes(), "application/pdf")

        assert resp.status_code == 201
        body = resp.json()
        assert body["filename"] == "plan.pdf"
        assert body["status"] == "processed"
        assert body["page_count"] == 3
        assert body["chunk_count"] == 3
        assert body["error_message"] is None

    def test_upload_valid_txt(self, client):
        content = (FIXTURES / "sample.txt").read_text(encoding="utf-8")
        resp = _upload(client, "sample.txt", content.encode("utf-8"), "text/plain")

        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "processed"
        assert body["chunk_count"] >= 2

    def test_upload_stores_page_numbers(self, client, db_session):
        resp = _upload(client, "pages.pdf", sample_pdf_bytes(), "application/pdf")
        document_id = resp.json()["id"]

        chunks = db_session.scalars(
            select(DocumentChunk).where(DocumentChunk.document_id == document_id)
        ).all()
        pages = {chunk.page_number for chunk in chunks}
        assert pages == {1, 2, 3}

    def test_upload_rejects_unsupported_extension(self, client):
        resp = _upload(client, "virus.exe", b"whatever", "application/octet-stream")
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "invalid_file"

    def test_upload_rejects_corrupt_pdf(self, client, db_session):
        resp = _upload(client, "broken.pdf", corrupt_pdf_bytes(), "application/pdf")

        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "invalid_file"

        row = db_session.scalars(
            select(Document).where(Document.filename == "broken.pdf")
        ).first()
        assert row is not None
        assert row.status == "failed"
        assert row.error_message

    def test_upload_rejects_fake_pdf_without_header(self, client):
        resp = _upload(client, "fake.pdf", b"definitely not a pdf", "application/pdf")
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "invalid_file"

    def test_upload_rejects_oversized_file(self, client, monkeypatch):
        monkeypatch.setattr(get_settings(), "max_upload_size_mb", 1)
        data = b"x" * (2 * 1024 * 1024)

        resp = _upload(client, "big.txt", data, "text/plain")
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "invalid_file"

    def test_upload_empty_txt_marks_failed(self, client, db_session):
        resp = _upload(client, "empty.txt", b"", "text/plain")

        assert resp.status_code == 422
        row = db_session.scalars(
            select(Document).where(Document.filename == "empty.txt")
        ).first()
        assert row is not None
        assert row.status == "failed"


class TestListGetDelete:
    def test_list_after_uploads(self, client):
        _upload(client, "a.pdf", sample_pdf_bytes(), "application/pdf")
        _upload(client, "b.txt", b"hello world", "text/plain")

        resp = client.get("/api/documents")
        assert resp.status_code == 200
        bodies = resp.json()
        assert len(bodies) == 2
        filenames = {b["filename"] for b in bodies}
        assert filenames == {"a.pdf", "b.txt"}
        assert bodies[0]["created_at"] >= bodies[1]["created_at"]

    def test_get_document(self, client):
        document_id = _upload(
            client, "a.pdf", sample_pdf_bytes(), "application/pdf"
        ).json()["id"]

        resp = client.get(f"/api/documents/{document_id}")
        assert resp.status_code == 200
        assert resp.json()["filename"] == "a.pdf"

    def test_get_missing_document_returns_404(self, client):
        resp = client.get("/api/documents/999999")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"

    def test_delete_removes_document_chunks_and_file(self, client, db_session):
        document_id = _upload(
            client, "del.pdf", sample_pdf_bytes(), "application/pdf"
        ).json()["id"]
        stored = db_session.get(Document, document_id).storage_path

        resp = client.delete(f"/api/documents/{document_id}")
        assert resp.status_code == 204

        assert client.get(f"/api/documents/{document_id}").status_code == 404
        assert db_session.get(Document, document_id) is None
        assert not Path(stored).exists()

    def test_delete_missing_document_returns_404(self, client):
        resp = client.delete("/api/documents/999999")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"