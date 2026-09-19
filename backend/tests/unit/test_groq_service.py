"""Tests for the Groq service, the only AI provider in MedDoc AI.

No external network calls are made: the OpenAI-compatible client is
replaced with a fake, and provider exceptions are constructed locally.
"""

from types import SimpleNamespace

import pytest

from openai import (
    APIConnectionError,
    APITimeoutError,
    APIStatusError,
    AuthenticationError,
    RateLimitError,
)

from app.core.config import Settings
from app.core.exceptions import GroqUnavailableError
from app.services.groq_service import (
    GROQ_BASE_URL,
    GroqChatClient,
    GroqChatCompleter,
    GroqProviderError,
    SourceContext,
    build_chat_completer,
    classify_groq_error,
)


def _fake_openai(exc=None, content="hello"):
    """A minimal stand-in for the OpenAI client exposing
    ``chat.completions.create``."""
    state = {"calls": [], "exc": exc, "content": content}

    def create(model, messages, **kwargs):
        state["calls"].append((model, messages, kwargs))
        if state["exc"] is not None:
            raise state["exc"]
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=state["content"]))]
        )

    return (
        SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        ),
        state,
    )


def _http_error(cls, status_code: int):
    """Build an SDK exception of ``cls`` without hitting the network."""
    error = cls.__new__(cls)
    error.response = SimpleNamespace(status_code=status_code)
    error.body = {}
    error.status_code = status_code
    error.headers = None
    error.request = None
    return error


class TestClassifyGroqError:
    @pytest.mark.parametrize(
        "exc_type,status,expected",
        [
            (RateLimitError, 429, "rate_limit"),
            (AuthenticationError, 401, "authentication"),
            (APITimeoutError, 408, "timeout"),
            (APIConnectionError, 0, "network"),
            (APIStatusError, 500, "server"),
            (APIStatusError, 404, "api_error"),
        ],
    )
    def test_mapping(self, exc_type, status, expected):
        assert classify_groq_error(_http_error(exc_type, status)).kind == expected

    def test_builtin_timeout_is_timeout(self):
        assert classify_groq_error(TimeoutError()).kind == "timeout"

    def test_unknown_exception_is_unknown(self):
        assert classify_groq_error(RuntimeError("boom")).kind == "unknown"


class TestGroqChatClient:
    def test_complete_returns_content_and_passes_temperature(self):
        fake, state = _fake_openai(content="answer")
        client = GroqChatClient(api_key="k", model="model-1")
        client._client = fake

        result = client.complete([{"role": "user", "content": "hi"}])

        assert result == "answer"
        model, messages, kwargs = state["calls"][0]
        assert model == "model-1"
        assert messages == [{"role": "user", "content": "hi"}]
        assert kwargs["temperature"] == 0.0

    def test_complete_json_mode_sets_response_format(self):
        fake, state = _fake_openai(content="{}")
        client = GroqChatClient(api_key="k", model="model-1")
        client._client = fake

        client.complete([{"role": "user", "content": "json please"}], json_mode=True)

        assert state["calls"][0][2]["response_format"] == {"type": "json_object"}

    @pytest.mark.parametrize(
        "exc_type,status,expected",
        [
            (RateLimitError, 429, "rate_limit"),
            (AuthenticationError, 401, "authentication"),
            (APITimeoutError, 408, "timeout"),
            (APIConnectionError, 0, "network"),
            (APIStatusError, 503, "server"),
        ],
    )
    def test_complete_wraps_provider_failure(self, exc_type, status, expected):
        fake, _ = _fake_openai(exc=_http_error(exc_type, status))
        client = GroqChatClient(api_key="k", model="model-1")
        client._client = fake

        with pytest.raises(GroqProviderError) as raised:
            client.complete([{"role": "user", "content": "hi"}])
        assert raised.value.kind == expected

    def test_empty_content_raises_empty(self):
        fake, _ = _fake_openai(content="   ")
        client = GroqChatClient(api_key="k", model="model-1")
        client._client = fake

        with pytest.raises(GroqProviderError) as raised:
            client.complete([{"role": "user", "content": "hi"}])
        assert raised.value.kind == "empty"

    def test_base_url_defaults_to_groq(self):
        client = GroqChatClient(api_key="k", model="model-1")
        assert client.base_url == GROQ_BASE_URL
        assert client.model == "model-1"


class _FakeCompleterClient:
    model = "fake-model"

    def __init__(self) -> None:
        self.recorded: list[list[dict[str, str]]] = []

    def complete(self, messages, **kwargs):  # noqa: ARG002
        self.recorded.append(messages)
        return "answer"


class TestGroqChatCompleter:
    def _source(self, text="Bring a referral letter."):
        return SourceContext(
            document_id=7, filename="notes.txt", page_number=3, text=text
        )

    def test_complete_builds_grounded_messages(self):
        client = _FakeCompleterClient()
        completer = GroqChatCompleter(client)

        completer.complete(
            query="What should I bring?",
            context=[self._source()],
            history=[{"role": "user", "content": "previous question"}],
        )

        messages = client.recorded[0]
        assert messages[0]["role"] == "system"
        system = messages[0]["content"]
        assert "ONLY from" in system
        assert "[Source 1]" in system
        assert "notes.txt" in system
        assert "page 3" in system
        assert "Bring a referral letter." in system
        assert {"role": "user", "content": "previous question"} in messages
        assert messages[-1] == {
            "role": "user",
            "content": "What should I bring?",
        }

    def test_complete_empty_context_is_cited_as_no_context(self):
        client = _FakeCompleterClient()
        completer = GroqChatCompleter(client)

        completer.complete(query="Where is the lab?", context=[])

        system = client.recorded[0][0]["content"]
        assert "No context available." in system

    def test_provider_and_model_are_exposed(self):
        completer = GroqChatCompleter(_FakeCompleterClient())
        assert completer.provider == "groq"
        assert completer.model == "fake-model"


class TestBuildChatCompleter:
    def test_missing_key_raises_controlled_error(self):
        with pytest.raises(GroqUnavailableError):
            build_chat_completer(settings=Settings(groq_api_key=""))

    def test_with_key_returns_groq_completer(self):
        settings = Settings(groq_api_key="test-key", groq_model="llama-3.3-70b-versatile")
        completer = build_chat_completer(settings=settings)

        assert isinstance(completer, GroqChatCompleter)
        assert completer.provider == "groq"
        assert completer.model == settings.groq_model
        assert completer._client.base_url == GROQ_BASE_URL
        assert completer._client.timeout == settings.groq_timeout_seconds