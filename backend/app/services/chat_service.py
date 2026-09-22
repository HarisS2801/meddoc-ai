"""RAG chat service: retrieval, answer generation, and review routing.

Given a question, the service retrieves document chunks with a hybrid
keyword + lexical-vector retriever (strictly scoped to the selected
documents), and generates an answer grounded in those chunks via Groq.
Every exchange is persisted as conversation messages, and risky or
low-confidence answers are routed to the human-review queue.

The backend decides whether retrieval succeeded. An empty retrieval never
reaches Groq: the user gets a controlled "not found in the uploaded
report" response instead of a model inventing a missing context.

If Groq is not configured or fails, a controlled ``GROQ_UNAVAILABLE`` error
is raised; the chat never fakes an answer.
"""

import json
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import DocumentStatus, MessageRole, ReviewReason, ReviewStatus
from app.core.exceptions import (
    GROQ_UNAVAILABLE_MESSAGE,
    AppError,
    ConflictError,
    GroqUnavailableError,
    NotFoundError,
)
from app.core.logging import get_logger
from app.db.models import Conversation, Document, DocumentChunk, Message, ReviewItem
from app.schemas.chat import ChatRequest, ChatResponse, SourceRef
from app.services.groq_service import SourceContext, build_chat_completer
from app.services.intent_classifier import (
    QuestionIntent,
    classify_intent,
    extract_abbreviation,
)
from app.services.retrieval import hybrid_retrieve
from app.utils.report_detector import abbreviation_meaning

logger = get_logger("chat")

_HISTORY_LIMIT = 6

# Controlled response when retrieval found nothing relevant in the selected
# report. Note: review routing and the offline test double expect the exact
# phrase "could not find information" so it stays in the message.
_NO_CONTEXT_ANSWER = (
    "I could not find information about that in the uploaded report. You can "
    "ask me about the patient's details, test results, or other information "
    "contained in the document."
)

# Deterministic answer when no selected document clearly names its type.
_REPORT_TYPE_UNKNOWN_ANSWER = (
    "The report type could not be determined from the uploaded document."
)

_MEDICAL_ADVICE_PATTERNS = (
    r"\bshould i\b",
    r"\bwhat should i\b",
    r"\bhow much\b",
    r"\bdos(?:e|age|ing)\b",
    r"prescri",
    r"\bdiagnos",
    r"\btreatment\b",
    r"\bmedication\b",
    r"\btherapy\b",
    r"is it (?:safe|ok)",
)


def looks_like_medical_advice(question: str) -> bool:
    """Best-effort heuristic for medically-sensitive requests."""
    lowered = question.lower()
    return any(re.search(pattern, lowered) for pattern in _MEDICAL_ADVICE_PATTERNS)


def review_decision(
    question: str,
    has_context: bool,
    best_distance: float | None,
    similarity_threshold: float,
) -> tuple[bool, str | None]:
    """Decide whether the answer needs human review.

    Returns ``(flagged, reason)``. ``reason`` is ``None`` when not flagged.
    """
    if looks_like_medical_advice(question):
        return True, ReviewReason.MEDICAL_ADVICE_ASKED.value
    if not has_context or best_distance is None or best_distance > similarity_threshold:
        return True, ReviewReason.LOW_CONFIDENCE.value
    return False, None


def list_conversations(db: Session) -> list[Conversation]:
    stmt = select(Conversation).order_by(Conversation.updated_at.desc())
    return list(db.scalars(stmt).all())


def get_conversation(db: Session, conversation_id: int) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise NotFoundError(f"Conversation {conversation_id} not found.")
    return conversation


def delete_conversation(db: Session, conversation_id: int) -> None:
    """Delete a chat workspace and its messages.

    Messages cascade away with the conversation; review items linked to
    those messages keep their history via ``SET NULL`` on ``message_id``.
    Uploaded documents are never touched.
    """
    conversation = get_conversation(db, conversation_id)
    db.delete(conversation)
    db.commit()


def _get_or_create_conversation(
    db: Session,
    conversation_id: int | None,
    question: str,
    document_ids: list[int],
) -> Conversation:
    if conversation_id is None:
        conversation = Conversation(
            title=question[:255],
            document_id=document_ids[0] if len(document_ids) == 1 else None,
        )
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        return conversation

    conversation = get_conversation(db, conversation_id)
    if conversation.document_id is not None:
        # Never reuse a workspace that was bound to a different document:
        # its history and cached context belong to that other report only.
        if set(document_ids) != {conversation.document_id}:
            raise ConflictError(
                "This chat workspace belongs to a different document. Start a "
                "new chat to ask about the selected document."
            )
    return conversation


def _resolve_documents(
    db: Session, document_ids: list[int] | None
) -> list[Document]:
    if not document_ids:
        raise ConflictError(
            "Please upload or select a document before asking a question."
        )

    documents: list[Document] = []
    for doc_id in document_ids:
        document = db.get(Document, doc_id)
        if document is None:
            raise NotFoundError(f"Document {doc_id} not found.")
        if document.status != DocumentStatus.PROCESSED.value:
            raise ConflictError(
                f"Document {doc_id} has not finished processing and cannot be searched."
            )
        documents.append(document)
    return documents


def _retrieve(
    db: Session, question: str, document_ids: list[int], settings
) -> list[dict]:
    """Return the relevant chunks for ``question``, scoped to the documents.

    Delegates to the hybrid retriever: keyword overlap (with medical-term
    expansion) over the authoritative SQLite chunk text is the relevance
    gate, and the lexical-vector cosine from ChromaDB only boosts ranking.
    """
    return hybrid_retrieve(
        db, question=question, document_ids=document_ids, settings=settings
    )


def _conversation_history(db: Session, conversation: Conversation) -> list[dict[str, str]]:
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.id.desc())
        .limit(_HISTORY_LIMIT)
    )
    recent = list(db.scalars(stmt).all())
    recent.reverse()
    return [{"role": message.role, "content": message.content} for message in recent]


# ---------------------------------------------------------------------------
# Document-level routing helpers.
#
# Document-level questions (report type, abbreviation meaning) are answered
# from the document's stored metadata — the type was detected during
# processing from the source text, never guessed by an LLM. They are routed
# deterministically and skip both vector retrieval and the similarity gate.
# ---------------------------------------------------------------------------


def _document_metadata_block(documents: list[Document]) -> str:
    """Small document information section passed to Groq with any context.

    Gives the model the report identity the document itself declared, so
    content questions are answered with the document in scope.
    """
    if not documents:
        return ""
    lines = ["DOCUMENT INFORMATION:", "-" * 21]
    for document in documents:
        report_type = document.report_type or "Not determined from the document"
        lines.append(f"Report Type: {report_type}")
        lines.append(f"Document: {document.filename}")
    lines.append("-" * 21)
    return "\n".join(lines)


def _document_noun(question: str) -> str:
    """Pick the noun the question used ("report", "test", "examination")."""
    lowered = question.lower()
    if re.search(r"\btest\b", lowered):
        return "test"
    if re.search(r"\bexam", lowered):
        return "examination"
    return "report"


def _report_type_abbreviation_matches(report_type: str | None, abbreviation: str) -> bool:
    if not report_type:
        return False
    return f"({abbreviation.lower()})" in report_type.lower()


def _metadata_answer(question: str, documents: list[Document], intent: str) -> str | None:
    """Answer a document-level question directly from stored metadata.

    Returns ``None`` when the question cannot be resolved from metadata so
    the caller falls back to the RAG path.
    """
    known = [document for document in documents if document.report_type]

    if intent == QuestionIntent.DOCUMENT_TYPE_QUERY:
        if not known:
            return _REPORT_TYPE_UNKNOWN_ANSWER
        noun = _document_noun(question)
        if len(known) == 1:
            return f"This is a {known[0].report_type} {noun}."
        parts = [f"{document.report_type} ({document.filename})" for document in known]
        return "The uploaded documents are: " + ", ".join(parts) + "."

    abbreviation = extract_abbreviation(question)
    if not abbreviation:
        return None
    for document in known:
        if _report_type_abbreviation_matches(document.report_type, abbreviation):
            meaning = abbreviation_meaning(abbreviation)
            if meaning:
                return f"{abbreviation.upper()} stands for {meaning}."
    return None


def _leading_chunks_for_summary(
    db: Session, document_ids: list[int], top_k: int
) -> list[dict]:
    """Fallback retrieval for summary questions: the document's leading chunks.

    Summary questions need the whole document, not a single high-scoring
    passage, so when keyword retrieval finds nothing we hand Groq the first
    chunks instead of rejecting the question.
    """
    chunks = list(
        db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id.in_(document_ids))
            .order_by(DocumentChunk.chunk_index)
        ).all()
    )
    hits = [
        {
            "chunk_id": str(chunk.id),
            "document_id": chunk.document_id,
            "page_number": chunk.page_number,
            "text": chunk.content,
            "matched_terms": [],
            "keyword_matches": 0,
            "vector_similarity": 0.0,
            "score": 0.0,
            "distance": None,
        }
        for chunk in chunks
    ]
    return hits[:top_k] if top_k else hits


def _persist_exchange(
    db: Session, conversation: Conversation, question: str, answer: str
) -> Message:
    """Persist one user+assistant exchange and return the assistant message."""
    user_message = Message(
        conversation=conversation,
        role=MessageRole.USER.value,
        content=question,
    )
    assistant_message = Message(
        conversation=conversation,
        role=MessageRole.ASSISTANT.value,
        content=answer,
    )
    db.add_all([user_message, assistant_message])
    db.commit()
    return assistant_message


def _log_routing_decision(
    *,
    conversation_id: int,
    question: str,
    documents: list[Document],
    intent: str,
    retrieval_required: bool,
    groq_called: bool,
    settings,
) -> None:
    """Emit the routing decision telemetry (never the full query in prod)."""
    decision = {
        "conversation_id": conversation_id,
        "query": question if settings.retrieval_debug else f"<len={len(question)}>",
        "intent": intent,
        "document_ids": [document.id for document in documents],
        "detected_report_type": {
            document.id: document.report_type for document in documents
        },
        "report_header": {
            document.id: document.report_header for document in documents
        },
        "retrieval_required": retrieval_required,
        "groq_called": groq_called,
    }
    logger.info("routing_decision=%s", json.dumps(decision))


def answer_question(db: Session, request: ChatRequest) -> ChatResponse:
    """Answer a chat question and persist the conversation exchange.

    Document-level questions (report type, abbreviation meaning) are
    answered deterministically from the stored document metadata and never
    hit the retrieval similarity gate. Content questions (medical values,
    general, summary) retrieve the relevant chunks and answer via Groq.
    """
    settings = get_settings()

    documents = _resolve_documents(db, request.document_ids)
    document_ids = [document.id for document in documents]
    filenames = {document.id: document.filename for document in documents}

    intent = classify_intent(request.question)

    conversation = _get_or_create_conversation(
        db, request.conversation_id, request.question, document_ids
    )

    # ----- Document-level questions answered directly from metadata -----
    if intent in {QuestionIntent.DOCUMENT_TYPE_QUERY, QuestionIntent.ABBREVIATION_QUERY}:
        metadata_answer = _metadata_answer(request.question, documents, intent)
        if metadata_answer is not None:
            _log_routing_decision(
                conversation_id=conversation.id,
                question=request.question,
                documents=documents,
                intent=intent,
                retrieval_required=False,
                groq_called=False,
                settings=settings,
            )
            _persist_exchange(db, conversation, request.question, metadata_answer)
            debug_payload = _routing_debug_payload(
                request,
                documents,
                intent=intent,
                retrieval_required=False,
                groq_called=False,
                hits=[],
                context_length=0,
                settings=settings,
            )
            if debug_payload is not None:
                logger.info("retrieval_debug=%s", json.dumps(debug_payload))
            db.refresh(conversation)
            return ChatResponse(
                conversation_id=conversation.id,
                answer=metadata_answer,
                sources=[],
                review_recommended=False,
                provider_used="metadata",
                model_used="document-metadata",
                generation_status="success",
                intent=intent,
                debug=debug_payload,
            )

    # ----- Content questions: RAG retrieval -> Groq -----
    try:
        hits = _retrieve(db, request.question, document_ids, settings)
    except AppError:
        # Controlled errors (e.g. Groq not configured) surface as-is.
        raise
    except Exception:
        logger.warning(
            "Retrieval failed in conversation %d; returning 503.",
            conversation.id,
            exc_info=True,
        )
        raise GroqUnavailableError(GROQ_UNAVAILABLE_MESSAGE) from None

    summary_fallback = False
    if not hits and intent == QuestionIntent.DOCUMENT_SUMMARY_QUERY:
        hits = _leading_chunks_for_summary(db, document_ids, settings.top_k)
        summary_fallback = bool(hits)

    context = [
        SourceContext(
            document_id=hit["document_id"],
            filename=filenames.get(hit["document_id"], "unknown"),
            page_number=hit["page_number"],
            text=hit["text"],
        )
        for hit in hits
    ]
    context_length = sum(len(source.text) for source in context)
    document_info = _document_metadata_block(documents)

    if hits:
        try:
            history = _conversation_history(db, conversation)
            completer = build_chat_completer()
            answer = completer.complete(
                query=request.question,
                context=context,
                history=history,
                document_info=document_info,
            )
        except AppError:
            # Controlled errors (e.g. Groq not configured) surface as-is.
            raise
        except Exception:
            logger.warning(
                "Groq failed to answer in conversation %d; returning 503.",
                conversation.id,
                exc_info=True,
            )
            raise GroqUnavailableError(GROQ_UNAVAILABLE_MESSAGE) from None
        provider_used = completer.provider
        model_used = completer.model
        groq_called = True
    else:
        # The backend decides retrieval success: an empty retrieval never
        # reaches Groq, so the model can never claim it has no context.
        answer = _NO_CONTEXT_ANSWER
        provider_used = "groq"
        model_used = settings.groq_model
        groq_called = False

    assistant_message = _persist_exchange(db, conversation, request.question, answer)

    sources = [
        SourceRef(
            document_id=hit["document_id"],
            filename=filenames.get(hit["document_id"], "unknown"),
            page_number=hit["page_number"],
            chunk_text=hit["text"],
        )
        for hit in hits
    ]

    best_distance = hits[0]["distance"] if hits else None
    confidence_threshold = settings.similarity_threshold
    if summary_fallback:
        # Summary questions intentionally hand the whole document to Groq;
        # the leading chunks are not a weak-context signal.
        flagged = False
    else:
        flagged, reason = review_decision(
            request.question,
            has_context=bool(hits),
            best_distance=best_distance,
            similarity_threshold=confidence_threshold,
        )
        if flagged:
            _create_review_item(
                db,
                assistant_message=assistant_message,
                question=request.question,
                document_ids=document_ids,
                sources=[source.model_dump() for source in sources],
                best_distance=best_distance,
                reason=reason,
            )

    _log_routing_decision(
        conversation_id=conversation.id,
        question=request.question,
        documents=documents,
        intent=intent,
        retrieval_required=True,
        groq_called=groq_called,
        settings=settings,
    )

    debug_payload = _retrieval_debug_payload(
        request,
        documents,
        hits,
        context_length,
        intent=intent,
        retrieval_required=True,
        groq_called=groq_called,
        settings=settings,
    )
    if debug_payload is not None:
        logger.info("retrieval_debug=%s", json.dumps(debug_payload))

    logger.info(
        "Answered question in conversation %d: documents=%s "
        "query=%r indexed_chunks=%d retrieved=%d context_length=%d",
        conversation.id,
        document_ids,
        len(request.question) if not settings.retrieval_debug else request.question,
        sum(document.chunk_count for document in documents),
        len(hits),
        context_length,
    )
    db.refresh(conversation)
    return ChatResponse(
        conversation_id=conversation.id,
        answer=answer,
        sources=sources,
        review_recommended=flagged,
        provider_used=provider_used,
        model_used=model_used,
        generation_status="success",
        intent=intent,
        debug=debug_payload,
    )


def _routing_debug_payload(
    request: ChatRequest,
    documents: list[Document],
    *,
    intent: str,
    retrieval_required: bool,
    groq_called: bool,
    hits: list[dict],
    context_length: int,
    settings,
) -> dict | None:
    """Structured routing telemetry, only when ``RETRIEVAL_DEBUG`` is on.

    Never enabled in production; never contains API keys. Chunk text is
    trimmed to a short preview so real medical documents are not dumped
    into logs.
    """
    if not settings.retrieval_debug:
        return None
    return {
        "intent": intent,
        "document_ids": [document.id for document in documents],
        "filenames": [document.filename for document in documents],
        "detected_report_type": {
            document.id: document.report_type for document in documents
        },
        "report_header": {
            document.id: document.report_header for document in documents
        },
        "retrieval_required": retrieval_required,
        "groq_called": groq_called,
        "extracted_text_length": sum(
            document.extracted_text_len for document in documents
        ),
        "num_chunks_indexed": sum(document.chunk_count for document in documents),
        "query": request.question,
        "num_retrieved_chunks": len(hits),
        "retrieved_chunks": [
            {
                "chunk_id": hit["chunk_id"],
                "document_id": hit["document_id"],
                "page_number": hit["page_number"],
                "score": hit["score"],
                "distance": hit["distance"],
                "matched_terms": hit.get("matched_terms", []),
                "text_preview": hit["text"][:200],
            }
            for hit in hits
        ],
        "context_length": context_length,
    }


def _retrieval_debug_payload(
    request: ChatRequest,
    documents: list[Document],
    hits: list[dict],
    context_length: int,
    *,
    intent: str,
    retrieval_required: bool,
    groq_called: bool,
    settings,
) -> dict | None:
    """Full retrieval telemetry for content questions (debug mode only).

    Thin wrapper over :func:`_routing_debug_payload` that keeps the same
    shape so one consumer parses both document-level and content answers.
    """
    return _routing_debug_payload(
        request,
        documents,
        intent=intent,
        retrieval_required=retrieval_required,
        groq_called=groq_called,
        hits=hits,
        context_length=context_length,
        settings=settings,
    )


def _create_review_item(
    db: Session,
    assistant_message: Message,
    *,
    question: str,
    document_ids: list[int],
    sources: list[dict],
    best_distance: float | None,
    reason: str | None,
) -> None:
    """Create a pending review item linked to the assistant message."""
    review = ReviewItem(
        question=question,
        answer=assistant_message.content,
        reason=reason or ReviewReason.UNSUPPORTED_ANSWER.value,
        status=ReviewStatus.PENDING.value,
        sources=sources,
        context={
            "document_ids": document_ids,
            "best_distance": best_distance,
        },
    )
    review.message = assistant_message
    db.add(review)
    db.commit()
    logger.info(
        "Routed answer to review queue (reason=%s) for message %d",
        review.reason,
        assistant_message.id,
    )