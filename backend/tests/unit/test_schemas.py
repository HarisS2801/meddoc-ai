"""Pydantic schema validation tests."""

import pytest
from pydantic import ValidationError

from app.core.enums import (
    DocumentStatus,
    ExtractionSchemaType,
    ReviewReason,
    ReviewStatus,
)
from app.db.models import Document
from app.schemas.chat import ChatRequest
from app.schemas.document import DocumentOut
from app.schemas.extraction import ExtractionRequest, ExtractionResult
from app.schemas.review import ReviewDecisionRequest, ReviewItemOut


class TestChatRequest:
    def test_valid_question(self):
        req = ChatRequest(question="What is the follow-up date?")
        assert req.question == "What is the follow-up date?"
        assert req.conversation_id is None
        assert req.document_ids is None

    def test_empty_question_rejected(self):
        with pytest.raises(ValidationError, match="at least 1 character"):
            ChatRequest(question="")

    def test_long_question_rejected(self):
        with pytest.raises(ValidationError, match="at most 2000"):
            ChatRequest(question="x" * 2001)

    def test_with_optional_fields(self):
        req = ChatRequest(
            question="Explain",
            conversation_id=7,
            document_ids=[1, 2, 3],
        )
        assert req.conversation_id == 7
        assert req.document_ids == [1, 2, 3]


class TestDocumentOut:
    def test_from_orm_document(self, db_session):
        doc = Document(
            filename="test.pdf",
            title="Test",
            content_type="application/pdf",
            storage_path="/test.pdf",
            status=DocumentStatus.PROCESSED.value,
        )
        db_session.add(doc)
        db_session.commit()
        db_session.refresh(doc)

        out = DocumentOut.model_validate(doc)
        assert out.id == doc.id
        assert out.status == DocumentStatus.PROCESSED
        assert out.filename == "test.pdf"


class TestExtractionRequest:
    def test_valid_follow_up_schema(self):
        req = ExtractionRequest.model_validate(
            {"document_id": 1, "schema": "follow_up"}
        )
        assert req.extraction_type == ExtractionSchemaType.FOLLOW_UP
        assert req.document_id == 1

    def test_invalid_schema_rejected(self):
        with pytest.raises(ValidationError, match="Input should be"):
            ExtractionRequest.model_validate(
                {"document_id": 1, "schema": "unknown_type"}
            )


class TestExtractionResult:
    def test_all_fields(self):
        result = ExtractionResult(
            follow_up_date="15 October",
            source_page=1,
            requires_review=True,
        )
        assert result.model_dump() == {
            "follow_up_date": "15 October",
            "source_page": 1,
            "requires_review": True,
        }

    def test_defaults(self):
        result = ExtractionResult()
        assert result.follow_up_date is None
        assert result.source_page is None
        assert result.requires_review is True


class TestReviewDecisionRequest:
    def test_empty_comment(self):
        req = ReviewDecisionRequest()
        assert req.comment is None

    def test_valid_comment(self):
        req = ReviewDecisionRequest(comment="Looks correct.")
        assert req.comment == "Looks correct."

    def test_long_comment_rejected(self):
        with pytest.raises(ValidationError, match="at most 2000"):
            ReviewDecisionRequest(comment="x" * 2001)


class TestReviewItemOut:
    def test_from_orm(self, db_session):
        from app.db.models import Message, Conversation

        conv = Conversation(title="test")
        msg = Message(role="user", content="q")
        conv.messages = [msg]
        from app.db.models import ReviewItem

        ri = ReviewItem(
            question="q",
            answer="a",
            reason=ReviewReason.UNSUPPORTED_ANSWER.value,
            status=ReviewStatus.PENDING.value,
            context=[{"chunk": "text"}],
            sources=[{"filename": "f.pdf", "page": 1}],
        )
        msg.review_item = ri
        db_session.add(conv)
        db_session.commit()
        db_session.refresh(ri)

        out = ReviewItemOut.model_validate(ri)
        assert out.reason == ReviewReason.UNSUPPORTED_ANSWER
        assert out.status == ReviewStatus.PENDING
        assert isinstance(out.context, list)
        assert len(out.sources) == 1