"""Tests for the extraction service (no network calls are made).

Groq handles extraction when configured; without a key a deterministic
regex extractor runs that only finds literal dates. When no value can be
confirmed the result is flagged ``requires_review`` and routed to the
human-review queue.
"""

import pytest
from sqlalchemy import select

import app.services.extraction_service as extraction_service
from app.core.config import Settings
from app.core.enums import DocumentStatus, ExtractionSchemaType, ReviewStatus
from app.core.exceptions import GroqUnavailableError, NotFoundError
from app.db.models import Document, DocumentChunk, ReviewItem
from app.services.extraction_service import (
    GroqExtractor,
    RegexDateExtractor,
    _parse_extraction_json,
    build_extractor,
    extract_document,
)
from app.services.groq_service import GroqProviderError
from tests.conftest import REAL_BUILD_EXTRACTOR


class TestRegexDateExtractor:
    def test_finds_day_month_date_and_page(self):
        chunks = [
            (1, "Patient intake summary."),
            (2, "The follow-up appointment is scheduled for 15 October."),
        ]
        data = RegexDateExtractor().extract(chunks)
        assert data.follow_up_date == "15 October"
        assert data.source_page == 2
        assert data.requires_review is False

    def test_finds_month_day_date(self):
        data = RegexDateExtractor().extract([(1, "Next review: February 10, 2026.")])
        assert data.follow_up_date == "February 10"
        assert data.source_page == 1

    def test_finds_iso_and_slash_dates(self):
        iso = RegexDateExtractor().extract([(1, "Due on 2026-08-20.")])
        assert iso.follow_up_date == "2026-08-20"
        slash = RegexDateExtractor().extract([(1, "Due on 15/10/2026.")])
        assert slash.follow_up_date == "15/10/2026"

    def test_no_date_flags_review(self):
        data = RegexDateExtractor().extract([(1, "No dates here at all.")])
        assert data.follow_up_date is None
        assert data.source_page is None
        assert data.requires_review is True


class TestParseExtractionJson:
    def test_valid_json(self):
        data = _parse_extraction_json(
            '{"follow_up_date": "2026-02-10", "source_page": 3}'
        )
        assert data.follow_up_date == "2026-02-10"
        assert data.source_page == 3
        assert data.requires_review is False

    def test_null_values_flag_review(self):
        data = _parse_extraction_json(
            '{"follow_up_date": null, "source_page": null}'
        )
        assert data.follow_up_date is None
        assert data.requires_review is True

    def test_garbage_output_flags_review(self):
        data = _parse_extraction_json("sorry, no json here")
        assert data.follow_up_date is None
        assert data.requires_review is True


class TestBuildExtractor:
    def test_no_api_key_returns_regex(self, monkeypatch):
        monkeypatch.setattr(extraction_service, "build_extractor", REAL_BUILD_EXTRACTOR)
        extractor = extraction_service.build_extractor(settings=Settings(groq_api_key=""))
        assert isinstance(extractor, RegexDateExtractor)

    def test_with_groq_api_key_returns_groq(self, monkeypatch):
        monkeypatch.setattr(extraction_service, "build_extractor", REAL_BUILD_EXTRACTOR)
        settings = Settings(groq_api_key="test-key")
        extractor = extraction_service.build_extractor(settings=settings)
        assert isinstance(extractor, GroqExtractor)
        assert extractor.provider == "groq"
        assert extractor.model == settings.groq_model


def _make_document(db_session, content: str, page: int = 1) -> Document:
    document = Document(
        filename="letter.txt",
        title="Letter",
        content_type="text/plain",
        storage_path="/tmp/letter.txt",
        status=DocumentStatus.PROCESSED.value,
        extracted_text_len=len(content),
        page_count=page,
        chunk_count=1,
    )
    document.chunks = [DocumentChunk(chunk_index=0, content=content, page_number=page)]
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)
    return document


class TestExtractDocument:
    def test_follow_up_date_found(self, db_session):
        document = _make_document(
            db_session, "The follow-up appointment is on 15 October."
        )

        response = extract_document(
            db_session, document.id, ExtractionSchemaType.FOLLOW_UP
        )

        assert response.document_id == document.id
        assert response.result.follow_up_date == "15 October"
        assert response.result.source_page == 1
        assert response.result.requires_review is False
        assert db_session.scalars(select(ReviewItem)).first() is None

    def test_missing_date_queues_review(self, db_session):
        document = _make_document(db_session, "No dates mentioned in this note.")

        response = extract_document(
            db_session, document.id, ExtractionSchemaType.FOLLOW_UP
        )

        assert response.result.follow_up_date is None
        assert response.result.requires_review is True
        review_item = db_session.scalars(select(ReviewItem)).first()
        assert review_item is not None
        assert review_item.reason == "incomplete_extraction"
        assert review_item.status == ReviewStatus.PENDING.value
        assert review_item.context["document_id"] == document.id

    def test_groq_failure_raises_groq_unavailable(self, db_session, monkeypatch):
        document = _make_document(db_session, "The appointment is on 15 October.")

        class _RaisingExtractor:
            def extract(self, chunks):  # noqa: ARG002
                raise GroqProviderError("rate_limit")

        monkeypatch.setattr(
            extraction_service, "build_extractor", lambda: _RaisingExtractor()
        )

        with pytest.raises(GroqUnavailableError):
            extract_document(db_session, document.id, ExtractionSchemaType.FOLLOW_UP)

    def test_unsupported_schema_rejected_at_schema_layer(self):
        from pydantic import ValidationError

        from app.schemas.extraction import ExtractionRequest

        with pytest.raises(ValidationError):
            ExtractionRequest.model_validate(
                {"document_id": 1, "schema": "not_a_real_schema"}
            )

    def test_missing_document_raises_not_found(self, db_session):
        try:
            extract_document(db_session, 999999, ExtractionSchemaType.FOLLOW_UP)
            raise AssertionError("expected NotFoundError")
        except NotFoundError:
            pass