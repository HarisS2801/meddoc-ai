"""API tests for RAG chat: ask, conversations list/detail, review routing."""

from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Document, DocumentChunk, Message, ReviewItem

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"

_CONTENT = (
    "Follow-up appointments happen on the last Friday of each month. "
    "Patients should bring their referral letter and photo identification."
)


@pytest.fixture(autouse=True)
def isolated_uploads(tmp_path, monkeypatch):
    """Route every upload to a throwaway directory so no real data leaks."""
    monkeypatch.setattr(get_settings(), "upload_dir", tmp_path / "uploads")


def _upload(client, name: str, data: bytes, content_type: str):
    files = {"file": (name, data, content_type)}
    return client.post("/api/documents/upload", files=files)


def _upload_chat_doc(client):
    resp = _upload(client, "notes.txt", _CONTENT.encode("utf-8"), "text/plain")
    assert resp.status_code == 201
    return resp.json()


def _first_chunk_text(client, db_session) -> str:
    document_id = db_session.scalars(
        select(DocumentChunk)
    ).first().document_id
    chunks = db_session.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    ).all()
    assert chunks, "expected at least one chunk to exist"
    return chunks[0].content


class TestAsk:
    def test_answer_grounded_with_sources(self, client, db_session):
        uploaded = _upload_chat_doc(client)
        question = _first_chunk_text(client, db_session)

        resp = client.post(
            "/api/chat",
            json={"question": question, "document_ids": [uploaded["id"]]},
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["conversation_id"] > 0
        assert body["answer"]
        assert body["review_recommended"] is False
        assert len(body["sources"]) >= 1
        source = body["sources"][0]
        assert source["document_id"] == uploaded["id"]
        assert source["filename"] == "notes.txt"
        assert source["page_number"] == 1
        assert source["chunk_text"]

    def test_medical_question_routed_to_review(self, client):
        uploaded = _upload_chat_doc(client)

        resp = client.post(
            "/api/chat",
            json={
                "question": "Should I take a higher dose?",
                "document_ids": [uploaded["id"]],
            },
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["review_recommended"] is True

    def test_missing_document_id_returns_clear_error(self, client):
        resp = client.post("/api/chat", json={"question": "Where is the clinic?"})

        assert resp.status_code == 409
        body = resp.json()
        assert body["error"]["code"] == "conflict"
        assert "upload or select a document" in body["error"]["message"]

    def test_missing_document_id_returns_404(self, client):
        resp = client.post(
            "/api/chat", json={"question": "hi", "document_ids": [999999]}
        )
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"

    def test_review_item_persisted_for_medical_question(self, client, db_session):
        uploaded = _upload_chat_doc(client)
        client.post(
            "/api/chat",
            json={
                "question": "Should I take a higher dose?",
                "document_ids": [uploaded["id"]],
            },
        )

        review_item = db_session.scalars(select(ReviewItem)).first()
        assert review_item is not None
        assert review_item.reason == "medical_advice_asked"
        assert review_item.sources == []


class TestConversation:
    def test_list_and_detail(self, client):
        uploaded = _upload_chat_doc(client)
        first = client.post(
            "/api/chat",
            json={"question": "Where is the clinic?", "document_ids": [uploaded["id"]]},
        ).json()
        second = client.post(
            "/api/chat",
            json={
                "question": "Where is the lab?",
                "conversation_id": first["conversation_id"],
                "document_ids": [uploaded["id"]],
            },
        ).json()

        conversations = client.get("/api/chat/conversations")
        assert conversations.status_code == 200
        bodies = conversations.json()
        assert len(bodies) == 1
        assert bodies[0]["id"] == first["conversation_id"]
        assert bodies[0]["title"] == "Where is the clinic?"

        detail = client.get(f"/api/chat/conversations/{first['conversation_id']}")
        assert detail.status_code == 200
        messages = detail.json()["messages"]
        assert len(messages) == 4
        roles = [m["role"] for m in messages]
        assert roles == ["user", "assistant", "user", "assistant"]
        assert second["conversation_id"] == first["conversation_id"]

    def test_delete_conversation_clears_workspace(self, client, db_session):
        uploaded = _upload_chat_doc(client)
        first = client.post(
            "/api/chat",
            json={"question": "Where is the clinic?", "document_ids": [uploaded["id"]]},
        ).json()

        resp = client.delete(f"/api/chat/conversations/{first['conversation_id']}")
        assert resp.status_code == 204

        from app.db.models import Message

        assert client.get(f"/api/chat/conversations/{first['conversation_id']}").status_code == 404
        assert db_session.scalars(select(Message)).first() is None
        assert db_session.get(Document, uploaded["id"]) is not None

    def test_missing_conversation_returns_404(self, client):
        resp = client.get("/api/chat/conversations/999999")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"

    def test_question_below_min_length_rejected(self, client):
        resp = client.post("/api/chat", json={"question": ""})
        assert resp.status_code == 422