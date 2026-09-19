"""Groq AI service (the only AI provider in MedDoc AI).

Groq exposes an OpenAI-compatible chat-completions API. This module wraps
it behind a small interface used by chat, summarization, and extraction:

- :class:`GroqChatClient` talks to the Groq API (temperature 0, optional
  JSON-mode output, configurable timeout) and classifies every failure
  (quota, auth, timeout, network, server errors) into a
  :class:`GroqProviderError` carrying a stable ``kind`` so callers can log
  and respond safely.
- :class:`GroqChatCompleter` builds grounded RAG answers from retrieved
  document passages with citations.

Errors never leak the API key or the provider's raw error body. If Groq is
not configured or fails, callers surface one controlled
``GROQ_UNAVAILABLE`` error instead of inventing content.
"""

from dataclasses import dataclass

from openai import (
    APIConnectionError,
    APITimeoutError,
    APIStatusError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)

from app.core.config import get_settings
from app.core.exceptions import (
    GROQ_MISSING_KEY_MESSAGE,
    GROQ_UNAVAILABLE_MESSAGE,
    GroqUnavailableError,
)
from app.core.logging import get_logger

logger = get_logger("groq")

GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Token ceiling for long structured JSON (a real report's structured
# summary can exceed 4k tokens). Groq models spend part of the budget on
# reasoning before the final answer; give them generous headroom.
DEFAULT_MAX_TOKENS = 16384


class GroqProviderError(Exception):
    """A classified Groq failure. ``kind`` is one of:

    ``rate_limit``, ``authentication``, ``timeout``, ``network``,
    ``server``, ``api_error``, ``empty``, or ``unknown``.
    """

    def __init__(self, kind: str) -> None:
        self.kind = kind
        super().__init__(kind)


def classify_groq_error(exc: Exception) -> GroqProviderError:
    """Map an SDK/transport exception to a stable, safe error kind."""
    if isinstance(exc, RateLimitError):
        kind = "rate_limit"
    elif isinstance(exc, AuthenticationError):
        kind = "authentication"
    elif isinstance(exc, APITimeoutError):
        kind = "timeout"
    elif isinstance(exc, APIConnectionError):
        kind = "network"
    elif isinstance(exc, APIStatusError):
        kind = "server" if (exc.status_code or 0) >= 500 else "api_error"
    elif isinstance(exc, TimeoutError):
        kind = "timeout"
    else:
        kind = "unknown"
    status = getattr(exc, "status_code", None)
    # Never log the key, the patient data, or the provider's raw body.
    logger.warning("Groq request failed (kind=%s, http_status=%s).", kind, status)
    return GroqProviderError(kind)


@dataclass(frozen=True)
class SourceContext:
    """One retrieved passage handed to Groq for grounding."""

    document_id: int
    filename: str
    page_number: int | None
    text: str


class GroqChatClient:
    """Thin wrapper around Groq's OpenAI-compatible chat-completions API."""

    def __init__(
        self,
        api_key: str,
        model: str,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        base_url: str = GROQ_BASE_URL,
        timeout: int = 30,
    ) -> None:
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=0,
        )
        self._model = model
        self._max_tokens = max_tokens
        self.base_url = base_url
        self.timeout = timeout

    @property
    def model(self) -> str:
        return self._model

    def complete(self, messages: list[dict[str, str]], *, json_mode: bool = False) -> str:
        """Run one completion at temperature 0 and return the text.

        When ``json_mode`` is set, the response_format JSON schema hint is
        passed to Groq (supported by current Groq models). Raises
        :class:`GroqProviderError` on any failure.
        """
        kwargs: dict = {"temperature": 0.0, "max_tokens": self._max_tokens}
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                **kwargs,
            )
        except Exception as exc:
            raise classify_groq_error(exc) from None
        content = (response.choices[0].message.content or "").strip()
        if not content:
            raise GroqProviderError("empty")
        return content


def _format_context(context: list[SourceContext]) -> str:
    if not context:
        return "No context available."
    blocks = []
    for index, source in enumerate(context, start=1):
        page = source.page_number if source.page_number else "unknown"
        blocks.append(
            f"[Source {index}] ({source.filename}, page {page}):\n{source.text}"
        )
    return "\n\n".join(blocks)


class GroqChatCompleter:
    """RAG answers grounded in retrieved document context, cited per source."""

    provider = "groq"

    def __init__(self, client: GroqChatClient) -> None:
        self._client = client

    @property
    def model(self) -> str:
        return self._client.model

    def complete(
        self,
        *,
        query: str,
        context: list[SourceContext],
        history: list[dict[str, str]] | None = None,
    ) -> str:
        instructions = (
            "You are MedDoc AI, an assistant that answers questions ONLY from "
            "the document context provided below. Do not use outside knowledge. "
            "If the context does not answer the question, say so clearly. "
            "Cite sources using the [Source N] markers and include the page "
            "number when available.\n\n"
        )
        context_block = _format_context(context)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": instructions + context_block}
        ]
        messages.extend(history or [])
        messages.append({"role": "user", "content": query})
        return self._client.complete(messages)


def build_chat_completer(settings=get_settings()) -> GroqChatCompleter:
    """Create the Groq-backed chat completer.

    Raises a controlled :class:`GroqUnavailableError` when the Groq key is
    missing, so chat never falls back to a fake answer.
    """
    if not settings.groq_api_key:
        logger.error("Groq chat unavailable: %s", GROQ_MISSING_KEY_MESSAGE)
        raise GroqUnavailableError(GROQ_MISSING_KEY_MESSAGE)
    completer = GroqChatCompleter(
        GroqChatClient(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            base_url=GROQ_BASE_URL,
            timeout=settings.groq_timeout_seconds,
        )
    )
    logger.info("Using Groq chat completions (%s)", settings.groq_model)
    return completer


__all__ = [
    "GROQ_BASE_URL",
    "GROQ_UNAVAILABLE_MESSAGE",
    "GroqChatClient",
    "GroqChatCompleter",
    "GroqProviderError",
    "SourceContext",
    "build_chat_completer",
    "classify_groq_error",
]