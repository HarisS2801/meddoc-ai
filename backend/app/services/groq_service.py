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
    """RAG answers grounded in retrieved document context.

    The answer text itself never carries citations: the app renders the
    compact ``Source: filename · Page N`` indicator beneath the answer from
    the structured source list returned by the API.
    """

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
        document_info: str | None = None,
    ) -> str:
        instructions = [
            "You are MedDoc AI, an assistant that answers questions ONLY from "
            "the document context provided below. Do not use outside knowledge "
            "to invent patient values, reference ranges, or findings. If the "
            "context does not answer the question, reply: \"I could not find "
            "information about that in the uploaded report.\"",
            "You are both a medical document assistant and a medical-parameter "
            "explainer. Medical parameters (for example WBC, haemoglobin, MCV, "
            "haematocrit, HbA1c, glucose, cholesterol, ALT, creatinine, eGFR, "
            "potassium, TSH, ejection fraction, QTc) may appear in any kind of "
            "report: laboratory panels, ECGs, imaging, and other documents. "
            "Identify the parameter the question asks about rather than relying "
            "on the report type, and never restrict yourself to full blood "
            "count parameters.",
            "Use the document context for the patient's own facts and general "
            "medical knowledge for explanations. Distinguish them clearly: "
            "present facts read from the report with phrasing such as \"Your "
            "report shows ...\" or \"the report's reference range is ...\". "
            "General explanations are educational context, not the patient's "
            "results.",
            "When the question asks about the patient's value (for example "
            "\"What is my MCV?\" or \"Is my ALT normal?\"): report the value "
            "from the context and compare it with the reference range printed "
            "in the report when one is present. Always prefer the report's own "
            "range. Never invent a reference range; if the context provides "
            "none, say: \"The report does not provide a reference range for "
            "this result, so I can't determine whether it is outside the "
            "laboratory's stated range.\"",
            "Explain what a parameter is, what it measures, and why it is "
            "measured using appropriate general medical knowledge. When asked "
            "what a high or low result can cause or indicate, give a brief "
            "educational explanation using careful wording such as \"can be "
            "associated with\", \"may occur with\", or \"has several possible "
            "causes\", tied to the patient's value when the context has one. "
            "Never diagnose the patient, claim certainty about a disease, "
            "prescribe medication, or recommend changing a treatment. When "
            "findings are significantly abnormal, a short note that results "
            "should be interpreted by a qualified healthcare professional is "
            "enough; do not repeat a long disclaimer.",
            "Write for a patient reading their own report: plain, warm, "
            "professional language. Answer the question directly in full "
            "sentences, without repeating the question and without labels "
            'such as "Patient Name:" or "Result:", headings, or closing '
            "remarks. Match the length and format to the question:",
            "- A simple definition (\"What is MCV?\") warrants a short "
            "definition.",
            "- A question about the patient's value (\"What is my MCV?\") "
            "warrants the value, the report's reference range when available, "
            "and whether it is within range.",
            "- A question about what a high or low result means warrants a "
            "brief educational explanation.",
            "- Several details at once warrant a short bulleted list.",
            "- A request to summarize the report warrants a short structured "
            "summary.",
            "Do not add citations, [Source N] markers, or any \"Source:\" "
            "line to your answer; the application shows the source beneath "
            "your answer automatically.",
        ]
        instructions = "\n".join(instructions) + "\n\n"
        context_block = _format_context(context)
        content_parts = [instructions]
        if document_info:
            content_parts.append(document_info)
        content_parts.append(context_block)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": "\n\n".join(content_parts)}
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