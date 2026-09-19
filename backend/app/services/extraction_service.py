"""Structured extraction from documents.

Supports the ``follow_up`` schema: pick a follow-up appointment date out of
the document text and the page it appears on.

Groq (the only AI provider) handles extraction when configured. Without a
key, a deterministic regex extractor runs — it only finds literal dates
written in common formats, never inventing one — so the flow stays
testable offline. When no value can be confirmed, the result is flagged
``requires_review`` and routed to the human-review queue.
"""

import json
import re
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import (
    ExtractionSchemaType,
    ReviewReason,
    ReviewStatus,
)
from app.core.exceptions import (
    GROQ_MISSING_KEY_MESSAGE,
    GROQ_UNAVAILABLE_MESSAGE,
    ConflictError,
    GroqUnavailableError,
    NotFoundError,
)
from app.core.logging import get_logger
from app.db.models import Document, DocumentChunk, ReviewItem
from app.schemas.extraction import ExtractionResponse, ExtractionResult
from app.services.groq_service import (
    GROQ_BASE_URL,
    GroqChatClient,
    GroqProviderError,
)

logger = get_logger("extraction")

_DAY_MONTH = (
    r"(?:\d{1,2})(?:st|nd|rd|th)?\s+"
    r"(?:jan\w*|feb\w*|mar\w*|apr\w*|may|jun\w*|jul\w*|aug\w*|sep\w*|oct\w*|nov\w*|dec\w*)"
)
_MONTH_DAY = (
    r"(?:jan\w*|feb\w*|mar\w*|apr\w*|may|jun\w*|jul\w*|aug\w*|sep\w*|oct\w*|nov\w*|dec\w*)"
    r"\s+\d{1,2}(?:st|nd|rd|th)?"
)
_ISO = r"\d{4}-\d{1,2}-\d{1,2}"
_SLASH = r"\d{1,2}/\d{1,2}/\d{2,4}"

_DATE_PATTERN = re.compile(
    rf"(?:{_DAY_MONTH}|{_MONTH_DAY}|{_ISO}|{_SLASH})",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ExtractionData:
    follow_up_date: str | None
    source_page: int | None
    requires_review: bool


class Extractor(Protocol):
    """Minimal interface implemented by the Groq and regex extractors."""

    def extract(self, chunks: list[tuple[int, str]]) -> ExtractionData: ...


class GroqExtractor:
    """Real extraction via the Groq chat API with strict JSON output."""

    provider = "groq"

    def __init__(self, client: GroqChatClient) -> None:
        self._client = client

    @property
    def model(self) -> str:
        return self._client.model

    def extract(self, chunks: list[tuple[int, str]]) -> ExtractionData:
        pages = "\n\n".join(f"[Page {page}]\n{text}" for page, text in chunks)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are MedDoc AI. Identify the follow-up appointment date in "
                    "the document below. Reply with STRICT JSON only, using the shape "
                    '{"follow_up_date": "YYYY-MM-DD" or null, "source_page": <int> or '
                    "null}. If no follow-up date is present, return null values. "
                    "Never invent a date that is not in the document."
                ),
            },
            {"role": "user", "content": pages},
        ]
        raw = self._client.complete(messages, json_mode=True)
        return _parse_extraction_json(raw)


def _parse_extraction_json(raw: str) -> ExtractionData:
    try:
        payload = json.loads(_extract_json(raw))
    except (ValueError, json.JSONDecodeError):
        return ExtractionData(None, None, requires_review=True)
    date = payload.get("follow_up_date")
    page = payload.get("source_page")
    found = bool(date)
    return ExtractionData(
        follow_up_date=date if found else None,
        source_page=page if found else None,
        requires_review=not found,
    )


def _extract_json(raw: str) -> str:
    start = raw.find("{")
    end = raw.rfind("}") + 1
    if start == -1 or end == 0:
        raise ValueError("No JSON object found in model output.")
    return raw[start:end]


class RegexDateExtractor:
    """Deterministic regex extractor that finds the first literal date.

    Returns the raw matched date text and the page it appears on. Only
    dates written in common formats are recognised; when no date is found
    the result is flagged for human review. This path never invents data.
    """

    def extract(self, chunks: list[tuple[int, str]]) -> ExtractionData:
        for page_number, text in chunks:
            match = _DATE_PATTERN.search(text)
            if match:
                return ExtractionData(
                    follow_up_date=match.group(0),
                    source_page=page_number,
                    requires_review=False,
                )
        return ExtractionData(None, None, requires_review=True)


def build_extractor(settings=get_settings()) -> Extractor:
    """Create the extractor: Groq when configured, otherwise regex.

    Without a key the deterministic regex extractor runs so the flow stays
    testable offline. It only reports literal dates; extraction is never
    faked.
    """
    if settings.groq_api_key:
        logger.info("Using Groq extractor (%s)", settings.groq_model)
        return GroqExtractor(
            GroqChatClient(
                api_key=settings.groq_api_key,
                model=settings.groq_model,
                base_url=GROQ_BASE_URL,
                timeout=settings.groq_timeout_seconds,
            )
        )
    logger.warning(
        "No GROQ_API_KEY set - using regex date extractor "
        "for offline development (%s).",
        GROQ_MISSING_KEY_MESSAGE,
    )
    return RegexDateExtractor()


def extract_document(
    db: Session, document_id: int, extraction_type: ExtractionSchemaType
) -> ExtractionResponse:
    """Extract a structured field from a document using the given schema."""
    if extraction_type != ExtractionSchemaType.FOLLOW_UP:
        raise ConflictError(
            f"Extraction schema '{extraction_type.value}' is not yet supported."
        )

    document = db.get(Document, document_id)
    if document is None:
        raise NotFoundError(f"Document {document_id} not found.")

    chunks = list(
        db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        ).all()
    )
    if not chunks:
        raise ConflictError(f"Document {document_id} has no text to extract from.")

    extractor = build_extractor()
    try:
        data = extractor.extract(
            [(chunk.page_number, chunk.content) for chunk in chunks]
        )
    except GroqProviderError as exc:
        logger.warning(
            "Groq extraction failed for document %d (kind=%s).",
            document_id,
            exc.kind,
        )
        raise GroqUnavailableError(GROQ_UNAVAILABLE_MESSAGE) from None

    if data.requires_review:
        _queue_review(db, document, data.follow_up_date)

    logger.info(
        "Extraction for document %d: date=%r page=%r",
        document_id,
        data.follow_up_date,
        data.source_page,
    )
    return ExtractionResponse(
        document_id=document_id,
        result=ExtractionResult(
            follow_up_date=data.follow_up_date,
            source_page=data.source_page,
            requires_review=data.requires_review,
        ),
    )


def _queue_review(db: Session, document: Document, date: str | None) -> None:
    """Create a pending review item when extraction is incomplete."""
    review = ReviewItem(
        question=(
            f"Extract the follow-up date from document {document.id} "
            f"({document.filename})."
        ),
        answer=(
            "No follow-up date could be confirmed from the document."
            if date is None
            else f"Candidate follow-up date: {date}."
        ),
        reason=ReviewReason.INCOMPLETE_EXTRACTION.value,
        status=ReviewStatus.PENDING.value,
        sources=None,
        context={
            "document_id": document.id,
            "extraction_type": ExtractionSchemaType.FOLLOW_UP.value,
        },
    )
    db.add(review)
    db.commit()
    logger.info(
        "Routed extraction to review queue for document %d (reason=%s)",
        document.id,
        review.reason,
    )