"""Tests for the summarization service (no network calls are made)."""

import json

import pytest
from sqlalchemy import select

from app.core.config import Settings
from app.core.enums import DocumentStatus
from app.core.exceptions import ConflictError, GroqUnavailableError, NotFoundError
from app.db.models import Document, DocumentChunk, Summary
from app.services.groq_service import GROQ_BASE_URL, GroqChatClient, GroqProviderError
from app.services.summarization_service import (
    GroqDocumentSummarizer,
    _content_fingerprint,
    build_summarizer,
    summarize_document,
    summarize_document_bundle,
)
from tests.conftest import REAL_BUILD_SUMMARIZER

import app.services.summarization_service as summarization_service

TEXT = "The clinic opens at nine. Appointments last an hour. Parking is free."

CACHED_PAYLOAD = {
    "document_overview": {"document_type": "Laboratory / Blood Test Report"},
    "main_condition": {
        "document_type": "Laboratory / Blood Test Report",
        "main_condition": "Type 2 Diabetes",
        "status": "Existing condition under follow-up",
    },
    "simple_explanation": "Your blood sugar is above the range in this report.",
}


class _CountingSummarizer:
    """Groq-shaped summarizer that counts real generation calls."""

    provider = "groq"
    model = "fake-model"

    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.structured_calls = 0

    def summarize_segment(self, text: str) -> str:
        return text

    def summarize_structured(self, text: str) -> str:
        self.structured_calls += 1
        return self.payload


class TestContentFingerprint:
    def test_stable_for_identical_input(self):
        first = _content_fingerprint(TEXT, "groq", "model-a")
        second = _content_fingerprint(TEXT, "groq", "model-a")
        assert first == second
        assert len(first) == 64

    def test_insensitive_to_whitespace_only_changes(self):
        first = _content_fingerprint("A B  C\n\nD", "groq", "model-a")
        second = _content_fingerprint("A B C D", "groq", "model-a")
        assert first == second

    def test_changes_when_content_changes(self):
        first = _content_fingerprint(TEXT, "groq", "model-a")
        second = _content_fingerprint(TEXT + " extra.", "groq", "model-a")
        assert first != second

    def test_changes_when_model_changes(self):
        first = _content_fingerprint(TEXT, "groq", "model-a")
        second = _content_fingerprint(TEXT, "groq", "model-b")
        assert first != second


class TestBuildSummarizer:
    def test_no_api_key_raises_controlled_error(self, monkeypatch):
        monkeypatch.setattr(
            summarization_service, "build_summarizer", REAL_BUILD_SUMMARIZER
        )
        with pytest.raises(GroqUnavailableError):
            summarization_service.build_summarizer(settings=Settings(groq_api_key=""))

    def test_with_groq_api_key_returns_groq_summarizer(self, monkeypatch):
        monkeypatch.setattr(
            summarization_service, "build_summarizer", REAL_BUILD_SUMMARIZER
        )
        settings = Settings(groq_api_key="test-key")
        summarizer = summarization_service.build_summarizer(settings=settings)
        assert isinstance(summarizer, GroqDocumentSummarizer)
        assert summarizer.provider == "groq"
        assert summarizer.model == settings.groq_model
        assert isinstance(summarizer._client, GroqChatClient)
        assert summarizer._client.base_url == GROQ_BASE_URL
        assert summarizer._client.timeout == settings.groq_timeout_seconds


def _make_document(db_session, content: str):
    document = Document(
        filename="report.txt",
        title="Report",
        content_type="text/plain",
        storage_path="/tmp/report.txt",
        status=DocumentStatus.PROCESSED.value,
        extracted_text_len=len(content),
        page_count=2,
        chunk_count=2,
    )
    document.chunks = [
        DocumentChunk(chunk_index=0, content=content, page_number=1),
        DocumentChunk(chunk_index=1, content="Second half.", page_number=2),
    ]
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)
    return document


class TestSummarizeDocument:
    def test_returns_summary_and_source_pages(self, db_session):
        _make_document(db_session, TEXT)

        summary, pages = summarize_document(db_session, 1)

        assert summary
        assert pages == [1, 2]
        assert "Appointments last an hour." in summary

    def test_missing_document_raises_not_found(self, db_session):
        try:
            summarize_document(db_session, 999999)
            raise AssertionError("expected NotFoundError")
        except NotFoundError:
            pass

    def test_document_without_chunks_raises_conflict(self, db_session):
        document = Document(
            filename="empty.txt",
            content_type="text/plain",
            storage_path="/tmp/empty.txt",
            status=DocumentStatus.PROCESSED.value,
        )
        db_session.add(document)
        db_session.commit()

        try:
            summarize_document(db_session, document.id)
            raise AssertionError("expected ConflictError")
        except ConflictError:
            pass


class TestSummaryCaching:
    def test_identical_calls_are_served_from_cache(self, db_session, monkeypatch):
        summarizer = _CountingSummarizer(json.dumps(CACHED_PAYLOAD))
        monkeypatch.setattr(
            "app.services.summarization_service.build_summarizer",
            lambda: summarizer,
        )
        document = _make_document(db_session, TEXT)

        first = summarize_document_bundle(db_session, document.id)
        second = summarize_document_bundle(db_session, document.id)

        assert summarizer.structured_calls == 1
        assert first.cached is False
        assert second.cached is True
        assert first.summary == second.summary
        assert second.document_type == "Laboratory / Blood Test Report"

    def test_content_change_invalidates_the_cache(self, db_session, monkeypatch):
        summarizer = _CountingSummarizer(json.dumps(CACHED_PAYLOAD))
        monkeypatch.setattr(
            "app.services.summarization_service.build_summarizer",
            lambda: summarizer,
        )
        document = _make_document(db_session, TEXT)

        summarize_document_bundle(db_session, document.id)
        assert summarizer.structured_calls == 1

        document.chunks[0].content = "Glucose 200 mg/dL (reference 70-110)."
        db_session.commit()

        summarize_document_bundle(db_session, document.id)
        assert summarizer.structured_calls == 2

    def test_force_regenerates_and_overwrites_cache(self, db_session, monkeypatch):
        summarizer = _CountingSummarizer(json.dumps(CACHED_PAYLOAD))
        monkeypatch.setattr(
            "app.services.summarization_service.build_summarizer",
            lambda: summarizer,
        )
        document = _make_document(db_session, TEXT)

        first = summarize_document_bundle(db_session, document.id)
        second = summarize_document_bundle(db_session, document.id, force=True)

        assert summarizer.structured_calls == 2
        assert first.cached is False
        assert second.cached is False
        rows = db_session.scalars(
            select(Summary).where(Summary.document_id == document.id)
        ).all()
        assert len(rows) == 1

    def test_bundle_exposes_groq_provider_and_model(self, db_session, monkeypatch):
        summarizer = _CountingSummarizer(json.dumps(CACHED_PAYLOAD))
        monkeypatch.setattr(
            "app.services.summarization_service.build_summarizer",
            lambda: summarizer,
        )
        document = _make_document(db_session, TEXT)

        bundle = summarize_document_bundle(db_session, document.id)

        assert bundle.provider == "groq"
        assert bundle.model == "fake-model"
        assert bundle.generation_status == "success"
        assert bundle.notice is None

    def test_provider_failure_is_not_cached(self, db_session, monkeypatch):
        class _BoomSummarizer(_CountingSummarizer):
            def summarize_structured(self, text: str) -> str:  # noqa: ARG002
                self.structured_calls += 1
                raise GroqProviderError("rate_limit")

        summarizer = _BoomSummarizer("{}")
        monkeypatch.setattr(
            "app.services.summarization_service.build_summarizer",
            lambda: summarizer,
        )
        document = _make_document(db_session, TEXT)

        with pytest.raises(GroqUnavailableError):
            summarize_document_bundle(db_session, document.id)
        with pytest.raises(GroqUnavailableError):
            summarize_document_bundle(db_session, document.id)

        assert summarizer.structured_calls == 2
        assert db_session.scalars(
            select(Summary).where(Summary.document_id == document.id)
        ).all() == []