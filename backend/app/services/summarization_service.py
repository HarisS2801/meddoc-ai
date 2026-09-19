"""Structured medical document summarization via Groq (the only AI provider).

Summaries are computed on demand from a document's chunks. The whole
document is always considered: content that fits in one pass is
summarised directly, and longer documents go through a map-reduce flow
(per-segment summaries combined into a condensed input) so no part of the
document is silently dropped.

The document type label is produced by Groq together with the structured
summary (never guessed by a keyword fallback).

Results are persisted keyed by a content fingerprint. Identical inputs
(same document, same provider, same model, same cache version) are served
from the cache, so a page refresh never triggers another Groq call. A
regeneration is only possible through an explicit ``force`` request.

If Groq is not configured or fails (quota, auth, timeout, network, or an
unreadable JSON response), the service raises a controlled
``GROQ_UNAVAILABLE`` error. It never fabricates or previews a medical
summary.
"""

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Protocol

from pydantic import ValidationError
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import (
    GROQ_MISSING_KEY_MESSAGE,
    GROQ_UNAVAILABLE_MESSAGE,
    ConflictError,
    GroqUnavailableError,
    NotFoundError,
)
from app.core.logging import get_logger
from app.db.models import Document, DocumentChunk, Summary
from app.schemas.summarization import SAFETY_NOTICE, StructuredSummary
from app.services.groq_service import (
    GROQ_BASE_URL,
    GroqChatClient,
    GroqProviderError,
)

logger = get_logger("summarization")

# Cache version marker. Bump it when the prompts, schema, or chunking change
# so previously stored summaries are regenerated exactly once instead of
# being served stale.
SUMMARY_CACHE_VERSION = "v1"

# Segment-map-reduce only kicks in for very large documents. For typical
# reports (a few thousand tokens) we pass the text straight to Groq.
_MAX_INPUT_CHARS = 40000

# Groq models spend part of the budget on reasoning before the final
# answer; give them generous headroom so the structured JSON is never
# truncated mid-object.
_SUMMARY_MAX_TOKENS = 16384

# Labels the UI knows how to colour. Anything else is normalised to the
# safest neutral value rather than trusting the model's wording blindly.
_MEASUREMENT_STATUSES = {
    "normal": "Normal",
    "high": "High",
    "low": "Low",
    "abnormal": "Abnormal",
    "not available": "Not available",
}
_RISK_LEVELS = {
    "low concern": "Low concern",
    "moderate concern": "Moderate concern",
    "high concern": "High concern",
    "not enough information": "Not enough information",
}
_SEVERITY_LABELS = {
    "normal / no abnormal finding reported": "Normal / No abnormal finding reported",
    "normal": "Normal / No abnormal finding reported",
    "no abnormal finding reported": "Normal / No abnormal finding reported",
    "mild": "Mild",
    "moderate": "Moderate",
    "severe": "Severe",
    "well controlled": "Well controlled",
    "partially controlled": "Partially controlled",
    "poorly controlled": "Poorly controlled",
    "unable to determine from the available information": (
        "Unable to determine from the available information"
    ),
}
_ABNORMAL_STATUSES = {"High", "Low", "Abnormal"}

_SEGMENT_INSTRUCTIONS = (
    "You are MedDoc AI, an assistant that explains uploaded healthcare "
    "documents to patients in plain language.\n\n"
    "This is an excerpt of a larger medical document. Summarize only the "
    "key facts in this excerpt in a few clear sentences: the kind of "
    "document it appears to be, main medical conditions, test results, "
    "medications, dates, follow-up instructions, and warnings. Be concise "
    "and factual. Do not invent information that is not in the excerpt.\n"
)

_NOT_MENTIONED = "Not mentioned in the report"

_STRUCTURED_INSTRUCTIONS = (
    "You are MedDoc AI, an assistant that explains an uploaded healthcare "
    "document to the patient who owns it, in plain language.\n\n"
    "Read the ENTIRE document text below and reply with a single JSON object "
    "and nothing else (no markdown, no commentary). Use exactly these keys:\n\n"
    "{\n"
    '  "patient_information": {"name": str, "patient_id": str, "age": str, '
    '"gender": str, "report_date": str, "doctor_or_hospital": str},\n'
    '  "document_overview": {"document_type": str, "purpose": str},\n'
    '  "main_condition": {"document_type": str, "main_condition": str, '
    '"status": str, "symptoms_or_findings": [str], "purpose": str},\n'
    '  "disease_severity": {"label": str, "explanation": str, '
    '"evidence": [str]},\n'
    '  "measurements": [{"name": str, "value": str, "unit": str, '
    '"reference_range": str, "status": str, "explanation": str}],\n'
    '  "risk_overview": [{"characteristic": str, "level": str, '
    '"evidence": str, "explanation": str, "recommendation": str}],\n'
    '  "key_findings": {"abnormal": [{"finding": str, "value": str, '
    '"why_it_matters": str}], "normal_or_reassuring": [{"finding": str, '
    '"value": str, "why_it_matters": str}]},\n'
    '  "medications": [{"name": str, "dosage": str, "frequency": str, '
    '"duration": str, "reason": str, "changes": str, "follow_up": str}],\n'
    '  "follow_up": {"follow_up_plan": [str], "monitoring_plan": [str], '
    '"precautions": [str]},\n'
    '  "simple_explanation": str\n'
    "}\n\n"
    "Rules:\n"
    f"- Use the exact string \"{_NOT_MENTIONED}\" for any field the document "
    "does not state. NEVER guess or invent names, ages, dates, doctors, "
    "measurements, values, units, reference ranges, diagnoses, medications, "
    "or instructions.\n"
    "- Only include a measurement in \"measurements\" when the document "
    "actually reports it. Keep the exact value and unit from the document, "
    "and copy the reference range only if the document provides it.\n"
    '- Measurement "status" must be one of: "Normal", "High", "Low", '
    '"Abnormal", "Not available". Judge it against the reference range in '
    "the document, not outside thresholds; if there is no reference range, "
    'use "Not available".\n'
    '- "disease_severity.label" must be one of: "Normal / No abnormal '
    'finding reported", "Mild", "Moderate", "Severe", "Well controlled", '
    '"Partially controlled", "Poorly controlled", "Unable to determine from '
    'the available information". Include the supporting values in '
    '"evidence". If the document does not provide enough evidence, use '
    '"Unable to determine from the available information" - never assign a '
    "severity you cannot support.\n"
    '- "risk_overview.level" must be one of: "Low concern", "Moderate '
    'concern", "High concern", "Not enough information". Include the value '
    'or finding and the reference range or evidence used. Never base a risk '
    "level on a single measurement alone.\n"
    "- Only list medications and follow-up instructions that the document "
    "states. Never recommend or change a medication.\n"
    "- \"simple_explanation\" is one or two short paragraphs a patient can "
    "understand: the main issue, whether it looks controlled or not, which "
    "values need attention, and what to discuss with the doctor.\n"
    "- Do not output a total cardiovascular or disease risk score.\n\n"
    "Document text:\n"
)


class DocumentSummarizer(Protocol):
    """Groq-backed summarizer interface (mirrored by test doubles)."""

    provider: str
    model: str

    def summarize_segment(self, text: str) -> str: ...

    def summarize_structured(self, text: str) -> str:
        """Return a raw JSON string for the structured summary schema."""
        ...


class GroqDocumentSummarizer:
    """Structured document summarization via the Groq API."""

    provider = "groq"

    def __init__(self, client: GroqChatClient) -> None:
        self._client = client

    @property
    def model(self) -> str:
        return self._client.model

    def _complete(self, system: str, text: str, *, json_mode: bool = False) -> str:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ]
        return self._client.complete(messages, json_mode=json_mode)

    def summarize_segment(self, text: str) -> str:
        return self._complete(_SEGMENT_INSTRUCTIONS, text)

    def summarize_structured(self, text: str) -> str:
        return self._complete(_STRUCTURED_INSTRUCTIONS, text, json_mode=True)


def build_summarizer(settings=get_settings()) -> DocumentSummarizer:
    """Create the Groq summarizer.

    Groq is the only provider: if the key is missing the call fails fast
    with a controlled :class:`GroqUnavailableError` instead of silently
    degrading to a mock or preview.
    """
    if not settings.groq_api_key:
        logger.error("Groq summarization unavailable: %s", GROQ_MISSING_KEY_MESSAGE)
        raise GroqUnavailableError(GROQ_MISSING_KEY_MESSAGE)
    summarizer = GroqDocumentSummarizer(
        GroqChatClient(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            max_tokens=_SUMMARY_MAX_TOKENS,
            base_url=GROQ_BASE_URL,
            timeout=settings.groq_timeout_seconds,
        )
    )
    logger.info("Using Groq summarizer (%s)", settings.groq_model)
    return summarizer


def _split_segments(text: str, limit: int) -> list[str]:
    """Split ``text`` into ordered segments no longer than ``limit``.

    Prefers paragraph boundaries so a segment is not cut mid-sentence when
    the document is readable as paragraphs.
    """
    text = text.strip()
    if not text:
        return []
    if len(text) <= limit:
        return [text]

    paragraphs = [para.strip() for para in re.split(r"\n{2,}", text) if para.strip()]
    segments: list[str] = []
    current = ""
    for para in paragraphs:
        if len(para) > limit:
            if current:
                segments.append(current)
                current = ""
            for start in range(0, len(para), limit):
                segments.append(para[start : start + limit])
            continue
        if current and len(current) + 1 + len(para) > limit:
            segments.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}".strip()
    if current:
        segments.append(current)
    return segments


def _load_document(
    db: Session, document_id: int
) -> tuple[Document, list[DocumentChunk]]:
    """Return the document row and its chunks, raising a clear error."""
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
        raise ConflictError(f"Document {document_id} has no text to summarize.")

    return document, chunks


def _dedupe_sentences(text: str) -> str:
    """Collapse consecutive duplicate sentences.

    Chunks are built with a small overlap, so joining them can repeat a
    sentence across a boundary. Removing exact adjacent duplicates keeps the
    summary input clean without losing content.
    """
    cleaned = " ".join(text.split())
    parts = re.split(r"(?<=\.)\s+", cleaned)
    out: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if out and part == out[-1]:
            continue
        out.append(part)
    return " ".join(out)


def _extract_json_object(raw: str) -> str | None:
    """Pull the first JSON object out of a model reply (tolerates fences)."""
    if not raw:
        return None
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    return text[start : end + 1]


def _normalise_label(value: str, allowed: dict[str, str], fallback: str) -> str:
    return allowed.get(value.strip().lower(), fallback)


def _sanitize_structured(structured: StructuredSummary) -> StructuredSummary:
    """Drop empty rows, normalise labels, and recompute derived counts.

    The model's own counts are never trusted: they are recalculated from the
    rows that actually survived. Disclaimers and "not mentioned" values are
    forced so the response can never present an invented interpretation.
    """
    measurements: list = []
    for item in structured.measurements:
        name = item.name.strip()
        if not name:
            continue
        item.name = name
        item.value = item.value.strip() or _NOT_MENTIONED
        item.unit = item.unit.strip()
        item.reference_range = (
            item.reference_range.strip() or _NOT_MENTIONED
        )
        item.status = _normalise_label(
            item.status, _MEASUREMENT_STATUSES, "Not available"
        )
        item.explanation = item.explanation.strip()
        measurements.append(item)
    structured.measurements = measurements

    structured.risk_overview = [
        item for item in structured.risk_overview if item.characteristic.strip()
    ]
    for item in structured.risk_overview:
        item.characteristic = item.characteristic.strip()
        item.level = _normalise_label(
            item.level, _RISK_LEVELS, "Not enough information"
        )
        item.evidence = item.evidence.strip() or _NOT_MENTIONED
        item.explanation = item.explanation.strip()
        item.recommendation = item.recommendation.strip()

    for group in (
        structured.key_findings.abnormal,
        structured.key_findings.normal_or_reassuring,
    ):
        group[:] = [finding for finding in group if finding.finding.strip()]

    structured.medications = [
        medication for medication in structured.medications if medication.name.strip()
    ]

    structured.disease_severity.label = _normalise_label(
        structured.disease_severity.label,
        _SEVERITY_LABELS,
        "Unable to determine from the available information",
    )
    # A severity/control claim without supporting values is downgraded.
    if (
        structured.disease_severity.label
        not in {
            "Unable to determine from the available information",
            "Normal / No abnormal finding reported",
        }
        and not structured.disease_severity.evidence
    ):
        structured.disease_severity.label = (
            "Unable to determine from the available information"
        )
        structured.disease_severity.explanation = (
            "The report does not provide enough evidence to determine the "
            "disease severity or control level."
        )

    abnormal_measurements = sum(
        1 for item in structured.measurements if item.status in _ABNORMAL_STATUSES
    )
    abnormal_count = abnormal_measurements + len(structured.key_findings.abnormal)

    card = structured.status_card
    information = structured.patient_information
    if card.patient_name.strip().lower() in {"", _NOT_MENTIONED.lower()}:
        card.patient_name = information.name.strip() or _NOT_MENTIONED
    if card.main_condition.strip().lower() in {"", _NOT_MENTIONED.lower()}:
        card.main_condition = (
            structured.main_condition.main_condition.strip() or _NOT_MENTIONED
        )
    if not card.report_type.strip():
        card.report_type = structured.document_overview.document_type
    if card.report_date.strip().lower() in {"", _NOT_MENTIONED.lower()}:
        card.report_date = information.report_date.strip() or _NOT_MENTIONED
    card.measurements_count = len(structured.measurements)
    card.abnormal_findings_count = abnormal_count
    if card.follow_up_required.strip().lower() not in {"yes", "no"}:
        has_follow_up = bool(
            structured.follow_up.follow_up_plan
            or structured.follow_up.monitoring_plan
            or structured.follow_up.precautions
        )
        card.follow_up_required = "Yes" if has_follow_up else "Not mentioned"
    if card.overall_status.strip().lower() in {
        "",
        "unable to determine from the report",
    }:
        if abnormal_count > 0 or card.follow_up_required == "Yes":
            card.overall_status = "Needs attention"
        elif structured.measurements:
            card.overall_status = "Results reported — review with your doctor"
        else:
            card.overall_status = "Unable to determine from the report"

    structured.safety_notice = SAFETY_NOTICE
    if not structured.simple_explanation.strip():
        structured.simple_explanation = (
            f"{structured.document_overview.document_type} reviewed. See the "
            "sections above for the details found in this report."
        )
    return structured


def _parse_structured(raw: str) -> StructuredSummary | None:
    """Parse a Groq reply into a validated, sanitised ``StructuredSummary``.

    Returns ``None`` for anything that is not a JSON object the schema can
    validate, so callers can raise a controlled error instead of presenting
    a half-broken interpretation.
    """
    candidate = _extract_json_object(raw)
    if candidate is None:
        return None
    try:
        data = json.loads(candidate)
    except (ValueError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        structured = StructuredSummary.model_validate(data)
    except ValidationError:
        return None
    return _sanitize_structured(structured)


def _structured_input(summarizer: DocumentSummarizer, text: str) -> str:
    """Feed the whole document to the structured prompt, condensed if needed."""
    text = _dedupe_sentences(text)
    if len(text) <= _MAX_INPUT_CHARS:
        return text
    segments = _split_segments(text, _MAX_INPUT_CHARS)
    segment_summaries = [summarizer.summarize_segment(segment) for segment in segments]
    return "\n\n".join(segment_summaries)


def _plain_summary(structured: StructuredSummary) -> str:
    """The plain-text ``summary`` for the API response."""
    if structured.simple_explanation.strip():
        return structured.simple_explanation.strip()
    return (
        f"{structured.document_overview.document_type}: "
        f"{structured.main_condition.main_condition}."
    )


@dataclass(frozen=True)
class SummaryBundle:
    """Everything the summarize endpoint needs for one document."""

    summary: str
    source_pages: list[int]
    notice: str | None
    structured: StructuredSummary | None
    document_type: str = "Medical Report"
    provider: str = "groq"
    model: str = ""
    generation_status: str = "success"
    cached: bool = False


def _content_fingerprint(text: str, provider: str, model: str) -> str:
    """Deterministic identifier for one summarization task.

    The chunk text is normalised (whitespace collapsed) before hashing so
    meaningless layout differences never change the fingerprint, while any
    real content change does. The cache version and provider identity are
    folded in so changing either invalidates stored summaries.
    """
    normalized = " ".join(text.split())
    payload = "\n".join((SUMMARY_CACHE_VERSION, provider, model, normalized))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_cached_summary(
    db: Session, document_id: int, fingerprint: str
) -> Summary | None:
    return db.scalars(
        select(Summary)
        .where(
            Summary.document_id == document_id,
            Summary.fingerprint == fingerprint,
        )
        .order_by(Summary.id.desc())
        .limit(1)
    ).first()


def _store_summary(
    db: Session,
    document_id: int,
    fingerprint: str,
    bundle: SummaryBundle,
    *,
    force: bool = False,
) -> None:
    """Persist the bundle so future identical requests skip the AI call.

    With ``force=True`` (an explicit retry), any previously stored rows for
    the same fingerprint are replaced so regenerations are saved.
    """
    if force:
        db.execute(
            delete(Summary).where(
                Summary.document_id == document_id,
                Summary.fingerprint == fingerprint,
            )
        )
        db.flush()

    row = Summary(
        document_id=document_id,
        fingerprint=fingerprint,
        summary=bundle.summary,
        source_pages=json.dumps(bundle.source_pages),
        document_type=bundle.document_type,
        notice=bundle.notice,
        structured=(
            bundle.structured.model_dump_json() if bundle.structured else None
        ),
        provider=bundle.provider,
        model=bundle.model,
        version=SUMMARY_CACHE_VERSION,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        # A concurrent request won the race and inserted the same row.
        db.rollback()
        cached = _load_cached_summary(db, document_id, fingerprint)
        if cached is not None:
            logger.info(
                "Summary for document %d already cached; skipping duplicate.",
                document_id,
            )
            return
        raise
    db.refresh(row)


def _bundle_from_row(row: Summary, *, cached: bool = True) -> SummaryBundle:
    """Rebuild a SummaryBundle from a stored row, tolerating corruption."""
    structured = None
    if row.structured:
        try:
            structured = StructuredSummary.model_validate_json(row.structured)
        except (ValidationError, ValueError):
            structured = None
    source_pages = json.loads(row.source_pages or "[]")
    return SummaryBundle(
        summary=row.summary,
        source_pages=source_pages if isinstance(source_pages, list) else [],
        notice=row.notice,
        structured=structured,
        document_type=row.document_type,
        provider=row.provider,
        model=row.model,
        generation_status="success",
        cached=cached,
    )


def _generate_bundle(
    summarizer: DocumentSummarizer,
    text: str,
    source_pages: list[int],
    document_id: int,
) -> SummaryBundle:
    """Run Groq once and assemble the full bundle, or fail controlled."""
    try:
        raw = summarizer.summarize_structured(_structured_input(summarizer, text))
        structured = _parse_structured(raw)
    except GroqProviderError as exc:
        logger.warning(
            "Groq structured summarization failed for document %d (kind=%s).",
            document_id,
            exc.kind,
        )
        raise GroqUnavailableError(GROQ_UNAVAILABLE_MESSAGE) from None

    if structured is None:
        logger.warning(
            "Document %d: Groq returned an unreadable structured response; "
            "no summary can be produced.",
            document_id,
        )
        raise GroqUnavailableError(GROQ_UNAVAILABLE_MESSAGE) from None

    logger.info("Structured summary generated for document %d", document_id)
    return SummaryBundle(
        _plain_summary(structured),
        source_pages,
        None,
        structured,
        structured.document_overview.document_type,
        provider=summarizer.provider,
        model=summarizer.model,
        generation_status="success",
        cached=False,
    )


def summarize_document_bundle(
    db: Session, document_id: int, *, force: bool = False
) -> SummaryBundle:
    """Return the structured summary for a document.

    Groq is called exactly once per distinct fingerprint: identical
    requests (including a page refresh) are served from the cache with
    ``cached=True`` and produce no Groq call. Regenerating requires an
    explicit ``force=True`` (the "Retry AI Analysis" action).

    On any Groq failure (missing key, quota, auth, timeout, network, or an
    unreadable response) a controlled :class:`GroqUnavailableError` is
    raised; no preview or mock summary is ever produced.
    """
    _, chunks = _load_document(db, document_id)
    text = "\n".join(chunk.content for chunk in chunks)
    source_pages = sorted({chunk.page_number for chunk in chunks})
    summarizer = build_summarizer()
    provider = summarizer.provider
    model = summarizer.model
    fingerprint = _content_fingerprint(text, provider, model)

    if not force:
        cached = _load_cached_summary(db, document_id, fingerprint)
        if cached is not None:
            logger.info(
                "Serving cached summary for document %d (%s %s).",
                document_id,
                provider,
                model,
            )
            return _bundle_from_row(cached, cached=True)

    bundle = _generate_bundle(summarizer, text, source_pages, document_id)
    _store_summary(db, document_id, fingerprint, bundle, force=force)
    return bundle


def summarize_document(db: Session, document_id: int) -> tuple[str, list[int]]:
    """Return ``(summary, source_pages)`` covering the whole document.

    The full concatenated chunk text is summarized. Long documents are
    condensed in order through Groq segment calls so no part is skipped.
    """
    bundle = summarize_document_bundle(db, document_id)
    return bundle.summary, bundle.source_pages


def summarize_document_with_status(
    db: Session, document_id: int
) -> tuple[str, list[int], str | None]:
    """Return ``(summary, source_pages, notice)``.

    ``notice`` is always ``None``: the app never degrades to a preview.
    Groq failures raise a controlled ``GROQ_UNAVAILABLE`` error instead.
    """
    bundle = summarize_document_bundle(db, document_id)
    return bundle.summary, bundle.source_pages, bundle.notice