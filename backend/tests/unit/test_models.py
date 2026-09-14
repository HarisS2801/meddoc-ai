"""ORM model round-trip and cascade-delete tests."""

import pytest
from sqlalchemy import select

from app.core.enums import (
    DocumentStatus,
    ReviewReason,
    ReviewStatus,
)
from app.db.base import Base
from app.db.models import (
    Conversation,
    Document,
    DocumentChunk,
    EvaluationResult,
    Message,
    ReviewItem,
)


class TestTablesRegistered:
    """Every model should be importable from the ``models`` package and
    registered on ``Base.metadata``."""

    def test_all_tables_exist(self):
        table_names = set(Base.metadata.tables)
        expected = {
            "documents",
            "document_chunks",
            "conversations",
            "messages",
            "review_items",
            "evaluation_results",
        }
        assert expected.issubset(table_names)


class TestDocumentAndChunks:
    def test_round_trip(self, db_session):
        doc = Document(
            filename="referral.pdf",
            title="Referral Letter",
            content_type="application/pdf",
            storage_path="/uploads/referral.pdf",
            status=DocumentStatus.PROCESSED.value,
            page_count=3,
            chunk_count=2,
            extracted_text_len=1200,
        )
        doc.chunks = [
            DocumentChunk(chunk_index=0, content="Follow-up on 15 Oct", page_number=1),
            DocumentChunk(chunk_index=1, content="Medication note", page_number=2),
        ]
        db_session.add(doc)
        db_session.commit()

        db_session.refresh(doc)
        assert doc.id is not None
        assert doc.status == "processed"
        assert doc.chunk_count == 2
        assert len(doc.chunks) == 2
        assert doc.chunks[0].page_number == 1

    def test_delete_document_cascades_chunks(self, db_session):
        doc = Document(
            filename="note.txt",
            content_type="text/plain",
            storage_path="/uploads/note.txt",
            status=DocumentStatus.PROCESSED.value,
            chunks=[
                DocumentChunk(chunk_index=0, content="alpha", page_number=1),
                DocumentChunk(chunk_index=1, content="beta", page_number=1),
            ],
        )
        db_session.add(doc)
        db_session.commit()

        doc_id = doc.id
        chunk_ids = [c.id for c in doc.chunks]
        db_session.delete(doc)
        db_session.commit()

        assert db_session.get(Document, doc_id) is None
        assert db_session.execute(
            select(DocumentChunk).where(DocumentChunk.id.in_(chunk_ids))
        ).all() == []

    def test_failed_document_records_error(self, db_session):
        doc = Document(
            filename="corrupt.pdf",
            content_type="application/pdf",
            storage_path="/uploads/corrupt.pdf",
            status=DocumentStatus.FAILED.value,
            error_message="Could not extract text: invalid PDF header",
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)
        assert doc.status == "failed"
        assert "invalid PDF header" in doc.error_message  # type: ignore[operator]


class TestConversationAndMessages:
    def test_round_trip(self, db_session):
        conv = Conversation(title="Follow-up questions")
        conv.messages = [
            Message(role="user", content="When is the appointment?"),
            Message(role="assistant", content="15 October."),
        ]
        db_session.add(conv)
        db_session.commit()

        db_session.refresh(conv)
        assert conv.id is not None
        assert len(conv.messages) == 2
        assert conv.messages[0].role == "user"

    def test_delete_conversation_cascades_messages(self, db_session):
        conv = Conversation(
            title="t",
            messages=[
                Message(role="user", content="q"),
                Message(role="assistant", content="a"),
            ],
        )
        db_session.add(conv)
        db_session.commit()

        conv_id = conv.id
        msg_ids = [m.id for m in conv.messages]
        db_session.delete(conv)
        db_session.commit()

        assert db_session.get(Conversation, conv_id) is None
        assert db_session.execute(
            select(Message).where(Message.id.in_(msg_ids))
        ).all() == []


class TestReviewItem:
    def test_link_to_message(self, db_session):
        conv = Conversation(title="x")
        msg = Message(role="user", content="Give me a diagnosis.")
        conv.messages = [msg]
        ri = ReviewItem(
            question="Give me a diagnosis.",
            answer="I could not find this information in the uploaded documents.",
            reason=ReviewReason.MEDICAL_ADVICE_ASKED.value,
            status=ReviewStatus.PENDING.value,
        )
        msg.review_item = ri
        db_session.add(conv)
        db_session.commit()

        db_session.refresh(ri)
        assert ri.id is not None
        assert ri.message_id == msg.id

    def test_delete_message_sets_review_message_id_null(self, db_session):
        conv = Conversation(title="y")
        msg = Message(role="user", content="q")
        ri = ReviewItem(
            question="q",
            answer="a",
            reason=ReviewReason.UNSUPPORTED_ANSWER.value,
            status=ReviewStatus.PENDING.value,
        )
        msg.review_item = ri
        conv.messages = [msg]
        db_session.add(conv)
        db_session.commit()

        msg_id = msg.id
        ri_id = ri.id
        db_session.delete(msg)
        db_session.commit()

        db_session.refresh(ri)
        assert ri.message_id is None


class TestEvaluationResult:
    def test_round_trip(self, db_session):
        result = EvaluationResult(
            run_id="run-001",
            scenario_id="sc-1",
            question="What is the dose?",
            answer="10 mg.",
            retrieval_precision=1.0,
            retrieval_recall=1.0,
            answer_correct=True,
            citation_correct=True,
            latency_ms=340,
            tokens_in=500,
            tokens_out=120,
        )
        db_session.add(result)
        db_session.commit()

        db_session.refresh(result)
        assert result.id is not None
        assert result.run_id == "run-001"
        assert result.latency_ms == 340