"""Document-isolation and workspace-isolation API tests.

Proves that every chat request and summary is strictly scoped to the
selected document: chunks from other uploads are never retrieved, cited,
or sent to the AI provider, and clearing a workspace forgets the chat
memory without touching uploaded files.
"""

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import Conversation, Document, Message
from app.services.groq_service import GroqProviderError

DOC_A = (
    "Patient: Amal. Condition: Type 2 Diabetes. "
    "Blood glucose: 6.8 mmol/L."
)
DOC_B = (
    "Patient: Nimal. Condition: Cardiac disease. "
    "Blood pressure: 138/86 mmHg."
)


@pytest.fixture(autouse=True)
def isolated_uploads(tmp_path, monkeypatch):
    """Route every upload to a throwaway directory so no real data leaks."""
    monkeypatch.setattr(get_settings(), "upload_dir", tmp_path / "uploads")


def _upload(client, name: str, content: str) -> int:
    files = {"file": (name, content.encode("utf-8"), "text/plain")}
    resp = client.post("/api/documents/upload", files=files)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "processed", body
    return body["id"]


def _ask(client, question: str, document_id: int, conversation_id=None):
    payload = {"question": question, "document_ids": [document_id]}
    if conversation_id is not None:
        payload["conversation_id"] = conversation_id
    return client.post("/api/chat", json=payload)


class TestIsolation:
    def test_question_scoped_to_document_a_only(self, client):
        doc_a = _upload(client, "amal.txt", DOC_A)
        doc_b = _upload(client, "nimal.txt", DOC_B)

        resp = _ask(client, "What is the patient name?", doc_a)

        assert resp.status_code == 200
        body = resp.json()
        assert "Amal" in body["answer"]
        assert "Nimal" not in body["answer"]
        assert "Diabetes" in body["answer"]
        assert "Cardiac" not in body["answer"]
        assert body["sources"], "expected at least one source"
        assert all(source["document_id"] == doc_a for source in body["sources"])
        assert doc_b not in {source["document_id"] for source in body["sources"]}
        assert body["provider_used"] == "groq"
        assert body["model_used"] == "test-mock"
        assert body["generation_status"] == "success"

    def test_question_scoped_to_document_b_only(self, client):
        doc_a = _upload(client, "amal.txt", DOC_A)
        doc_b = _upload(client, "nimal.txt", DOC_B)

        resp = _ask(client, "What is the blood pressure?", doc_b)

        assert resp.status_code == 200
        body = resp.json()
        assert "Nimal" in body["answer"]
        assert "Amal" not in body["answer"]
        assert "138" in body["answer"]
        assert "Diabetes" not in body["answer"]
        assert body["sources"]
        assert all(source["document_id"] == doc_b for source in body["sources"])
        assert doc_a not in {source["document_id"] for source in body["sources"]}

    def test_switching_documents_starts_clean_scope(self, client):
        doc_a = _upload(client, "amal.txt", DOC_A)
        doc_b = _upload(client, "nimal.txt", DOC_B)

        first = _ask(client, "What is the patient name?", doc_a)
        assert first.status_code == 200
        assert "Amal" in first.json()["answer"]

        second = _ask(client, "What is the blood pressure?", doc_b)
        assert second.status_code == 200
        body = second.json()
        assert "Nimal" in body["answer"]
        assert "Amal" not in body["answer"]
        assert first.json()["conversation_id"] != body["conversation_id"]

    def test_reusing_other_document_workspace_is_rejected(self, client):
        doc_a = _upload(client, "amal.txt", DOC_A)
        doc_b = _upload(client, "nimal.txt", DOC_B)

        first = _ask(client, "What is the patient name?", doc_a)
        conversation_id = first.json()["conversation_id"]

        resp = _ask(client, "What is the blood pressure?", doc_b, conversation_id)

        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "conflict"

    def test_duplicate_filenames_are_isolated_by_id(self, client):
        first = _upload(client, "report.txt", DOC_A)
        second = _upload(client, "report.txt", DOC_B)

        assert first != second
        resp_a = _ask(client, "What is the patient name?", first)
        resp_b = _ask(client, "What is the blood pressure?", second)

        assert "Amal" in resp_a.json()["answer"]
        assert "Nimal" not in resp_a.json()["answer"]
        assert "Nimal" in resp_b.json()["answer"]
        assert "Amal" not in resp_b.json()["answer"]
        assert {s["document_id"] for s in resp_a.json()["sources"]} == {first}
        assert {s["document_id"] for s in resp_b.json()["sources"]} == {second}

    def test_zero_chunk_retrieval_returns_no_sources(self, client):
        doc = _upload(client, "clinic.txt", "Clinic hours are nine to five.")

        resp = _ask(client, "What is the weather forecast for Paris tomorrow?", doc)

        assert resp.status_code == 200
        body = resp.json()
        assert body["sources"] == []
        assert body["review_recommended"] is True
        assert "could not find information" in body["answer"]


class TestMissingAndInvalidDocuments:
    def test_missing_active_document_id_returns_clear_error(self, client):
        resp = client.post("/api/chat", json={"question": "Where is the clinic?"})

        assert resp.status_code == 409
        body = resp.json()
        assert body["error"]["code"] == "conflict"
        assert "upload or select a document" in body["error"]["message"]

    def test_invalid_document_id_returns_404(self, client):
        resp = _ask(client, "Where is the clinic?", 999999)

        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"


class TestWorkspaceClearing:
    def test_clear_workspace_forgets_chat_and_keeps_documents(self, client, db_session):
        doc_a = _upload(client, "amal.txt", DOC_A)
        doc_b = _upload(client, "nimal.txt", DOC_B)

        first = _ask(client, "What is the patient name?", doc_a)
        conversation_id = first.json()["conversation_id"]
        assert db_session.get(Conversation, conversation_id) is not None

        resp = client.delete(f"/api/chat/conversations/{conversation_id}")
        assert resp.status_code == 204

        assert db_session.get(Conversation, conversation_id) is None
        assert db_session.scalars(select(Message)).all() == []

        history = client.get("/api/documents")
        assert history.status_code == 200
        ids = {item["id"] for item in history.json()}
        assert doc_a in ids and doc_b in ids

    def test_empty_workspace_starts_fresh_conversation(self, client, db_session):
        doc = _upload(client, "amal.txt", DOC_A)

        first = _ask(client, "What is the patient name?", doc)
        conversation_id = first.json()["conversation_id"]
        client.delete(f"/api/chat/conversations/{conversation_id}")

        assert db_session.scalars(select(Conversation)).all() == []
        assert db_session.scalars(select(Message)).all() == []

        second = _ask(client, "What is the blood glucose?", doc)

        assert second.status_code == 200
        body = second.json()
        conversation = db_session.get(Conversation, body["conversation_id"])
        assert conversation.document_id == doc
        assert len(conversation.messages) == 2
        assert [m.role for m in conversation.messages] == ["user", "assistant"]

    def test_conversation_persisted_and_bound_to_document(self, client, db_session):
        doc_a = _upload(client, "amal.txt", DOC_A)
        doc_b = _upload(client, "nimal.txt", DOC_B)

        resp = _ask(client, "What is the patient name?", doc_a)
        conversation = db_session.get(Conversation, resp.json()["conversation_id"])

        assert conversation is not None
        assert conversation.document_id == doc_a
        assert len(conversation.messages) == 2

        other = db_session.get(Conversation, resp.json()["conversation_id"])
        assert other.document_id != doc_b


class TestSummaryIsolation:
    def test_summary_uses_only_the_selected_document(self, client):
        doc_a = _upload(client, "amal.txt", DOC_A)
        doc_b = _upload(client, "nimal.txt", DOC_B)

        resp = client.post(f"/api/documents/{doc_b}/summarize")

        assert resp.status_code == 200
        body = resp.json()
        assert body["document_id"] == doc_b
        assert "Nimal" in body["summary"]
        assert "Amal" not in body["summary"]
        assert "Diabetes" not in body["summary"]

    def test_failed_summary_returns_503_without_cross_document_leak(
        self, client, monkeypatch
    ):
        doc_a = _upload(client, "amal.txt", DOC_A)
        doc_b = _upload(client, "nimal.txt", DOC_B)

        class _RaisingSummarizer:
            provider = "groq"
            model = "fake-model"

            def summarize_segment(self, text: str) -> str:
                return text

            def summarize_structured(self, text: str) -> str:
                raise GroqProviderError("rate_limit")

        import app.services.summarization_service as summarization_service

        default_builder = summarization_service.build_summarizer
        monkeypatch.setattr(
            summarization_service, "build_summarizer", lambda: _RaisingSummarizer()
        )

        resp = client.post(f"/api/documents/{doc_a}/summarize")

        assert resp.status_code == 503
        error = resp.json()["error"]
        assert error["code"] == "groq_unavailable"
        assert error["provider"] == "groq"

        monkeypatch.setattr(summarization_service, "build_summarizer", default_builder)
        untouched = client.post(f"/api/documents/{doc_b}/summarize")
        assert untouched.status_code == 200
        assert "Nimal" in untouched.json()["summary"]
        assert "Amal" not in untouched.json()["summary"]