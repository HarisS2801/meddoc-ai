"""Shared test fixtures.

The ``db_engine`` fixture creates a disposable SQLite database per test
in a ``tmp_path`` directory.  ``db_session`` yields an ORM session bound
to that database.  ``client`` provides a ``TestClient`` wired to a
session-backed ``get_db`` override so no real data is touched.

Every test runs fully offline: the Groq key is cleared and the app's AI
entry points are swapped for deterministic test doubles, so no external
API is ever called. Tests that want the *real* missing-key behaviour
(no key -> controlled ``GROQ_UNAVAILABLE`` 503) can restore the original
factories via the ``REAL_BUILD_*`` references below.
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_db
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import enable_sqlite_foreign_keys
from app.main import create_app
from app.services import chat_service, extraction_service, summarization_service
from app.services.extraction_service import RegexDateExtractor
from app.services.vector_store import VectorStore

# The original factories, captured before the autouse fixtures replace
# them, so tests can exercise the real "no key -> 503" paths.
REAL_BUILD_CHAT_COMPLETER = chat_service.build_chat_completer
REAL_BUILD_EXTRACTOR = extraction_service.build_extractor
REAL_BUILD_SUMMARIZER = summarization_service.build_summarizer


class TestChatDouble:
    """Deterministic stand-in for :class:`GroqChatCompleter`.

    Grounds the answer in the best retrieved passage (the chunk text, the
    filename, and the page number) or refuses politely when there is no
    context, so every offline chat test stays deterministic.
    """

    provider = "groq"
    model = "test-mock"

    @staticmethod
    def complete(*, query, context, history=None):  # noqa: ARG004
        if not context:
            return (
                "I could not find information about this in the uploaded "
                "document. Please ask a question the uploaded document can "
                "answer, or consult a qualified healthcare professional."
            )
        source = context[0]
        return (
            f"Based on the uploaded document, the most relevant passage "
            f"({source.filename}, page {source.page_number}) reads: "
            f'"{source.text}"'
        )


class _TestSummarizer:
    """Deterministic Groq-shaped summarizer used by tests that hit the
    real ``/summarize`` flow without stubbing it themselves.

    The plain summary is the document text itself, so assertions like
    ``"Nimal" in summary`` and ``"intake" in summary`` hold, and no
    medical value is ever invented.
    """

    provider = "groq"
    model = "test-mock"

    def __init__(self) -> None:
        self.structured_inputs: list[str] = []
        self.structured_calls = 0

    def summarize_segment(self, text: str) -> str:
        return text

    def summarize_structured(self, text: str) -> str:
        self.structured_calls += 1
        self.structured_inputs.append(text)
        return json.dumps({"simple_explanation": text})


@pytest.fixture()
def db_engine(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'test.db'}"
    test_engine = create_engine(database_url, connect_args={"check_same_thread": False})
    enable_sqlite_foreign_keys(test_engine)
    Base.metadata.create_all(test_engine)
    yield test_engine
    Base.metadata.drop_all(test_engine)
    test_engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    TestSession = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)  # noqa: N806
    session = TestSession()
    yield session
    session.close()


@pytest.fixture()
def client(db_engine):
    TestSession = sessionmaker(bind=db_engine, autoflush=False, expire_on_commit=False)  # noqa: N806

    def _override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app = create_app()
    app.dependency_overrides[get_db] = _override_get_db
    test_client = TestClient(app)
    yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def vector_store(tmp_path):
    """A VectorStore backed by a throwaway ChromaDB directory."""
    return VectorStore(chroma_dir=tmp_path / "chroma")


@pytest.fixture(autouse=True)
def isolated_vector_store(vector_store, monkeypatch):
    """Route every get_vector_store() call in the app to the test store."""
    monkeypatch.setattr(
        "app.services.vector_store.get_vector_store",
        lambda: vector_store,
    )


@pytest.fixture(autouse=True)
def offline_ai_providers(monkeypatch):
    """Clear the Groq key on the cached Settings for every test.

    A locally configured ``backend/.env`` can carry a real Groq key; tests
    must never call the paid API. With the key cleared, every ``build_*``
    factory is either a deterministic test double (see below) or, when
    restored to the real implementation, raises a controlled
    ``GROQ_UNAVAILABLE`` error.
    """
    settings = get_settings()
    monkeypatch.setattr(settings, "groq_api_key", "")
    return settings


@pytest.fixture(autouse=True)
def stop_groq_builders(monkeypatch):
    """Swap the app's Groq entry points for deterministic test doubles."""
    monkeypatch.setattr(chat_service, "build_chat_completer", lambda: TestChatDouble())
    monkeypatch.setattr(
        extraction_service, "build_extractor", lambda: RegexDateExtractor()
    )
    monkeypatch.setattr(
        summarization_service, "build_summarizer", lambda: _TestSummarizer()
    )