"""Tests for the RAG chat service heuristics and answer flow."""

from sqlalchemy import select

from app.core.enums import DocumentStatus, MessageRole, ReviewStatus
from app.core.exceptions import ConflictError, NotFoundError
from app.db.models import Conversation, Document, DocumentChunk, Message, ReviewItem
from app.schemas.chat import ChatRequest
from app.services.chat_service import (
    answer_question,
    list_conversations,
    looks_like_medical_advice,
    review_decision,
)
from app.services.embedding_service import build_embedding_service


class TestMedicalAdviceHeuristic:
    def test_flags_medical_requests(self):
        assert looks_like_medical_advice("Should I take a higher dose?")
        assert looks_like_medical_advice("What is the treatment for flu?")
        assert looks_like_medical_advice("Is it safe to double the dosage?")

    def test_does_not_flag_administrative_requests(self):
        assert not looks_like_medical_advice("Where is the appointment scheduled?")
        assert not looks_like_medical_advice("Which page mentions the address?")


class TestReviewDecision:
    def test_medical_advice_takes_priority(self):
        flagged, reason = review_decision(
            "Should I take paracetamol?", has_context=True, best_distance=0.0, similarity_threshold=0.30
        )
        assert flagged is True
        assert reason == "medical_advice_asked"

    def test_weak_context_flags_low_confidence(self):
        flagged, reason = review_decision(
            "Where is the clinic?", has_context=True, best_distance=0.9, similarity_threshold=0.30
        )
        assert flagged is True
        assert reason == "low_confidence"

    def test_missing_context_flags_low_confidence(self):
        flagged, reason = review_decision(
            "Anything relevant?", has_context=False, best_distance=None, similarity_threshold=0.30
        )
        assert flagged is True
        assert reason == "low_confidence"

    def test_clear_answer_not_flagged(self):
        flagged, reason = review_decision(
            "Where is the clinic?", has_context=True, best_distance=0.05, similarity_threshold=0.30
        )
        assert flagged is False
        assert reason is None


def _make_processed_document(db_session, content: str) -> tuple[Document, DocumentChunk]:
    document = Document(
        filename="notes.txt",
        title="Notes",
        content_type="text/plain",
        storage_path="/tmp/notes.txt",
        status=DocumentStatus.PROCESSED.value,
        extracted_text_len=len(content),
        page_count=1,
        chunk_count=1,
    )
    chunk = DocumentChunk(chunk_index=0, content=content, page_number=1)
    document.chunks = [chunk]
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)
    db_session.refresh(chunk)
    return document, chunk


class TestAnswerQuestion:
    def test_answer_grounded_in_indexed_chunk(self, db_session, vector_store):
        content = "Follow-up appointments happen on the last Friday of each month."
        _, chunk = _make_processed_document(db_session, content)
        service = build_embedding_service()
        vector_store.upsert_chunks(
            [
                {
                    "chunk_id": str(chunk.id),
                    "vector": service.embed_text(content),
                    "document_id": chunk.document_id,
                    "page_number": 1,
                    "text": content,
                }
            ]
        )

        response = answer_question(
            db_session,
            ChatRequest(question=content, document_ids=[chunk.document_id]),
        )

        assert response.conversation_id is not None
        assert response.answer
        assert len(response.sources) == 1
        assert response.sources[0].filename == "notes.txt"
        assert response.sources[0].document_id == chunk.document_id
        assert response.sources[0].page_number == 1
        assert response.review_recommended is False

        conversation = db_session.get(Conversation, response.conversation_id)
        assert len(conversation.messages) == 2
        assert conversation.messages[0].role == MessageRole.USER.value
        assert conversation.messages[1].role == MessageRole.ASSISTANT.value

    def test_medical_question_creates_review_item(self, db_session, vector_store):
        content = "Follow-up appointments happen on the last Friday of each month."
        _, chunk = _make_processed_document(db_session, content)
        service = build_embedding_service()
        vector_store.upsert_chunks(
            [
                {
                    "chunk_id": str(chunk.id),
                    "vector": service.embed_text(content),
                    "document_id": chunk.document_id,
                    "page_number": 1,
                    "text": content,
                }
            ]
        )

        response = answer_question(
            db_session,
            ChatRequest(
                question="Should I take a higher dose?",
                document_ids=[chunk.document_id],
            ),
        )

        assert response.review_recommended is True
        review_item = db_session.scalars(select(ReviewItem)).first()
        assert review_item is not None
        assert review_item.status == ReviewStatus.PENDING.value
        assert review_item.reason == "medical_advice_asked"

    def test_missing_document_id_raises_conflict(self, db_session):
        try:
            answer_question(db_session, ChatRequest(question="Where is the clinic?"))
            raise AssertionError("expected ConflictError")
        except ConflictError:
            pass

    def test_missing_document_id_raises_not_found(self, db_session):
        try:
            answer_question(
                db_session, ChatRequest(question="hi", document_ids=[999999])
            )
            raise AssertionError("expected NotFoundError")
        except NotFoundError:
            pass

    def test_conversation_continuation_keeps_history(self, db_session, vector_store):
        content = "Follow-up appointments happen on the last Friday of each month."
        _, chunk = _make_processed_document(db_session, content)
        service = build_embedding_service()
        vector_store.upsert_chunks(
            [
                {
                    "chunk_id": str(chunk.id),
                    "vector": service.embed_text(content),
                    "document_id": chunk.document_id,
                    "page_number": 1,
                    "text": content,
                }
            ]
        )

        first = answer_question(
            db_session, ChatRequest(question=content, document_ids=[chunk.document_id])
        )
        second = answer_question(
            db_session,
            ChatRequest(
                question=content,
                conversation_id=first.conversation_id,
                document_ids=[chunk.document_id],
            ),
        )

        assert second.conversation_id == first.conversation_id
        conversation = db_session.get(Conversation, first.conversation_id)
        assert len(conversation.messages) == 4

    def test_conversation_bound_to_other_document_is_rejected(self, db_session, vector_store):
        content_a = "Follow-up appointments happen on the last Friday of each month."
        content_b = "Blood pressure target is below 130/80 mmHg."
        _, chunk_a = _make_processed_document(db_session, content_a)
        doc_b = Document(
            filename="b.txt",
            title="B",
            content_type="text/plain",
            storage_path="/tmp/b.txt",
            status=DocumentStatus.PROCESSED.value,
            extracted_text_len=len(content_b),
            page_count=1,
            chunk_count=1,
        )
        chunk_b = DocumentChunk(chunk_index=0, content=content_b, page_number=1)
        doc_b.chunks = [chunk_b]
        db_session.add(doc_b)
        db_session.commit()
        db_session.refresh(doc_b)
        db_session.refresh(chunk_b)
        service = build_embedding_service()
        for chunk in (chunk_a, chunk_b):
            vector_store.upsert_chunks(
                [
                    {
                        "chunk_id": str(chunk.id),
                        "vector": service.embed_text(chunk.content),
                        "document_id": chunk.document_id,
                        "page_number": 1,
                        "text": chunk.content,
                    }
                ]
            )

        first = answer_question(
            db_session, ChatRequest(question=content_a, document_ids=[chunk_a.document_id])
        )
        try:
            answer_question(
                db_session,
                ChatRequest(
                    question=content_b,
                    conversation_id=first.conversation_id,
                    document_ids=[chunk_b.document_id],
                ),
            )
            raise AssertionError("expected ConflictError")
        except ConflictError:
            pass

    def test_list_conversations_sorted_by_activity(self, db_session):
        doc_a = Document(
            filename="a.txt",
            title="A",
            content_type="text/plain",
            storage_path="/tmp/a.txt",
            status=DocumentStatus.PROCESSED.value,
            extracted_text_len=1,
            page_count=1,
            chunk_count=1,
        )
        doc_b = Document(
            filename="b.txt",
            title="B",
            content_type="text/plain",
            storage_path="/tmp/b.txt",
            status=DocumentStatus.PROCESSED.value,
            extracted_text_len=1,
            page_count=1,
            chunk_count=1,
        )
        db_session.add_all([doc_a, doc_b])
        db_session.commit()
        db_session.refresh(doc_a)
        db_session.refresh(doc_b)
        answer_question(db_session, ChatRequest(question="Where is the clinic?", document_ids=[doc_a.id]))
        answer_question(db_session, ChatRequest(question="Where is the lab?", document_ids=[doc_b.id]))

        conversations = list_conversations(db_session)
        assert len(conversations) == 2
        assert conversations[0].title != conversations[1].title
        assert conversations[0].updated_at >= conversations[1].updated_at

    def test_delete_conversation_clears_workspace_and_keeps_document(
        self, db_session, vector_store
    ):
        from app.services.chat_service import delete_conversation

        content = "Follow-up appointments happen on the last Friday of each month."
        _, chunk = _make_processed_document(db_session, content)
        service = build_embedding_service()
        vector_store.upsert_chunks(
            [
                {
                    "chunk_id": str(chunk.id),
                    "vector": service.embed_text(content),
                    "document_id": chunk.document_id,
                    "page_number": 1,
                    "text": content,
                }
            ]
        )

        first = answer_question(
            db_session, ChatRequest(question=content, document_ids=[chunk.document_id])
        )
        assert db_session.get(Conversation, first.conversation_id) is not None
        assert db_session.get(Document, chunk.document_id) is not None

        delete_conversation(db_session, first.conversation_id)

        assert db_session.get(Conversation, first.conversation_id) is None
        assert db_session.get(Document, chunk.document_id) is not None


class TestLexicalRetrievalGating:
    """Regression tests for the mock-mode retrieval gate and grounding."""

    _CONTENT = (
        "CARE PLAN GOALS\n"
        "- Target fasting glucose: 80-130 mg/dL\n"
        "- Target A1c: below 7.0%\n"
        "- Next appointment: 2026-08-20"
    )

    def _index(self, db_session, vector_store, content):
        _, chunk = _make_processed_document(db_session, content)
        service = build_embedding_service()
        vector_store.upsert_chunks(
            [
                {
                    "chunk_id": str(chunk.id),
                    "vector": service.embed_text(content),
                    "document_id": chunk.document_id,
                    "page_number": 1,
                    "text": content,
                }
            ]
        )
        return chunk

    def test_in_scope_question_retrieves_grounded_sources(self, db_session, vector_store):
        chunk = self._index(db_session, vector_store, self._CONTENT)
        response = answer_question(
            db_session,
            ChatRequest(
                question="What range is listed as the target fasting glucose in the care plan?",
                document_ids=[chunk.document_id],
            ),
        )
        assert len(response.sources) == 1
        assert response.sources[0].document_id == chunk.document_id
        assert response.sources[0].chunk_text == self._CONTENT
        assert response.review_recommended is False

    def test_out_of_scope_question_retrieves_nothing(self, db_session, vector_store):
        chunk = self._index(db_session, vector_store, self._CONTENT)
        response = answer_question(
            db_session,
            ChatRequest(
                question="What is the weather forecast for Paris tomorrow?",
                document_ids=[chunk.document_id],
            ),
        )
        assert response.sources == []