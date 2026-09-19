"""Groq failure handling: controlled 503s, never a degraded preview.

The summarizer never fabricates or previews a medical summary when Groq
is unavailable. Each provider failure mode (missing key, quota, timeout,
unreadable output) surfaces as a controlled ``GROQ_UNAVAILABLE`` error,
and nothing is cached.
"""

import pytest

from app.core.enums import DocumentStatus
from app.core.exceptions import GROQ_UNAVAILABLE_MESSAGE, GroqUnavailableError
from app.db.models import Document, DocumentChunk, Summary
from app.services.groq_service import GroqProviderError
from app.services.summarization_service import (
    summarize_document_bundle,
    summarize_document_with_status,
)
from tests.conftest import REAL_BUILD_SUMMARIZER


class _RaisingSummarizer:
    provider = "groq"
    model = "test-rise"

    def __init__(self, exc) -> None:
        self._exc = exc

    def summarize_segment(self, text: str) -> str:  # noqa: ARG002
        raise self._exc

    def summarize_structured(self, text: str) -> str:  # noqa: ARG002
        raise self._exc


class _GarbageSummarizer:
    provider = "groq"
    model = "test-rise"

    def summarize_segment(self, text: str) -> str:
        return text

    def summarize_structured(self, text: str) -> str:  # noqa: ARG002
        return "totally not json"


def _make_document(db_session, content: str):
    document = Document(
        filename="report.txt",
        title="Report",
        content_type="text/plain",
        storage_path="/tmp/report.txt",
        status=DocumentStatus.PROCESSED.value,
        extracted_text_len=len(content),
        page_count=1,
        chunk_count=1,
    )
    document.chunks = [
        DocumentChunk(chunk_index=0, content=content, page_number=1),
    ]
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)
    return document


def test_no_key_raises_groq_unavailable(db_session, monkeypatch):
    import app.services.summarization_service as ss

    document = _make_document(db_session, "The clinic opens at nine.")
    monkeypatch.setattr(ss, "build_summarizer", REAL_BUILD_SUMMARIZER)

    with pytest.raises(GroqUnavailableError) as raised:
        summarize_document_with_status(db_session, document.id)
    assert raised.value.status_code == 503
    assert raised.value.code == "groq_unavailable"


def test_rate_limit_raises_groq_unavailable(db_session, monkeypatch):
    import app.services.summarization_service as ss

    document = _make_document(db_session, "The clinic opens at nine.")
    monkeypatch.setattr(
        ss,
        "build_summarizer",
        lambda: _RaisingSummarizer(GroqProviderError("rate_limit")),
    )

    with pytest.raises(GroqUnavailableError) as raised:
        summarize_document_bundle(db_session, document.id)
    assert raised.value.message == GROQ_UNAVAILABLE_MESSAGE


def test_timeout_raises_groq_unavailable(db_session, monkeypatch):
    import app.services.summarization_service as ss

    document = _make_document(db_session, "The clinic opens at nine.")
    monkeypatch.setattr(
        ss,
        "build_summarizer",
        lambda: _RaisingSummarizer(GroqProviderError("timeout")),
    )

    with pytest.raises(GroqUnavailableError):
        summarize_document_bundle(db_session, document.id)


def test_unreadable_output_raises_groq_unavailable(db_session, monkeypatch):
    import app.services.summarization_service as ss

    document = _make_document(db_session, "The clinic opens at nine.")
    monkeypatch.setattr(ss, "build_summarizer", lambda: _GarbageSummarizer())

    with pytest.raises(GroqUnavailableError):
        summarize_document_bundle(db_session, document.id)


def test_long_document_provider_failure_never_leaks_a_preview(
    db_session, monkeypatch
):
    import app.services.summarization_service as ss

    content = " ".join(f"Sentence number {i}." for i in range(4000))
    document = _make_document(db_session, content)
    monkeypatch.setattr(
        ss,
        "build_summarizer",
        lambda: _RaisingSummarizer(GroqProviderError("rate_limit")),
    )
    monkeypatch.setattr(ss, "_MAX_INPUT_CHARS", 500)

    with pytest.raises(GroqUnavailableError):
        summarize_document_bundle(db_session, document.id)


def test_failed_summaries_are_never_cached(db_session, monkeypatch):
    import app.services.summarization_service as ss
    from sqlalchemy import select

    document = _make_document(db_session, "The clinic opens at nine.")
    summarizer = _RaisingSummarizer(GroqProviderError("rate_limit"))
    monkeypatch.setattr(ss, "build_summarizer", lambda: summarizer)

    for _ in range(2):
        with pytest.raises(GroqUnavailableError):
            summarize_document_bundle(db_session, document.id)

    assert db_session.scalars(select(Summary)).all() == []