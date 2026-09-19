"""API tests for document summarization and structured extraction."""

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Document, DocumentChunk, ReviewItem

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

_WITH_DATE = (
    "The patient completed their intake with the care coordinator. "
    "The follow-up appointment is scheduled for 15 October."
)
_NO_DATE = "The patient completed their intake and no follow-up is planned."


@pytest.fixture(autouse=True)
def isolated_uploads(tmp_path, monkeypatch):
    """Route every upload to a throwaway directory so no real data leaks."""
    monkeypatch.setattr(get_settings(), "upload_dir", tmp_path / "uploads")


def _upload_doc(client, content: str, name: str = "notes.txt") -> int:
    files = {"file": (name, content.encode("utf-8"), "text/plain")}
    resp = client.post("/api/documents/upload", files=files)
    assert resp.status_code == 201
    return resp.json()["id"]


class TestSummarize:
    def test_summarize_processed_document(self, client):
        document_id = _upload_doc(client, _WITH_DATE)

        resp = client.post(f"/api/documents/{document_id}/summarize")

        assert resp.status_code == 200
        body = resp.json()
        assert body["document_id"] == document_id
        assert "intake" in body["summary"]
        assert body["source_pages"] == [1]

    def test_summarize_missing_document_returns_404(self, client):
        resp = client.post("/api/documents/999999/summarize")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"


class TestExtract:
    def test_extract_follow_up_date(self, client):
        document_id = _upload_doc(client, _WITH_DATE)

        resp = client.post(
            f"/api/documents/{document_id}/extract",
            json={"document_id": document_id, "schema": "follow_up"},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["document_id"] == document_id
        assert body["result"]["follow_up_date"] == "15 October"
        assert body["result"]["source_page"] == 1
        assert body["result"]["requires_review"] is False

    def test_extract_missing_date_flags_review(self, client, db_session):
        document_id = _upload_doc(client, _NO_DATE)

        resp = client.post(
            f"/api/documents/{document_id}/extract",
            json={"document_id": document_id, "schema": "follow_up"},
        )

        assert resp.status_code == 200
        assert resp.json()["result"]["requires_review"] is True
        review_item = db_session.scalars(select(ReviewItem)).first()
        assert review_item is not None
        assert review_item.reason == "incomplete_extraction"

    def test_extract_body_id_mismatch_returns_409(self, client):
        document_id = _upload_doc(client, _WITH_DATE)

        resp = client.post(
            f"/api/documents/{document_id}/extract",
            json={"document_id": 999999, "schema": "follow_up"},
        )

        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "conflict"

    def test_extract_missing_document_returns_404(self, client):
        resp = client.post(
            "/api/documents/999999/extract",
            json={"document_id": 999999, "schema": "follow_up"},
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"

    def test_extract_invalid_schema_rejected(self, client):
        resp = client.post(
            "/api/documents/1/extract",
            json={"document_id": 1, "schema": "bogus"},
        )
        assert resp.status_code == 422