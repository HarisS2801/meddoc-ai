"""RAG chat service: retrieval, answer generation, and review routing.

Given a question, the service embeds it locally (lexical vectors), searches
the vector store for the most relevant chunks (optionally restricted to a
set of documents), and generates an answer grounded in those chunks via
Groq. Every exchange is persisted as conversation messages, and risky or
low-confidence answers are routed to the human-review queue.

If Groq is not configured or fails, a controlled ``GROQ_UNAVAILABLE`` error
is raised; the chat never fakes an answer.
"""

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
from app.db.models import Conversation, Document, Message, ReviewItem
from app.schemas.chat import ChatRequest, ChatResponse, SourceRef
from app.services import vector_store as vector_store_module
from app.services.embedding_service import build_embedding_service
from app.services.groq_service import SourceContext, build_chat_completer

logger = get_logger("chat")

_HISTORY_LIMIT = 6

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
    question: str, document_ids: list[int], settings
) -> list[dict]:
    """Return the relevant chunks, gated by the lexical relevance threshold.

    Embeddings are always the local lexical provider, so a single lexical
    gate applies and only the single best passage is used for grounding.
    """
    if not document_ids:
        return []

    service = build_embedding_service()
    query_embedding = service.embed_text(question)
    hits = vector_store_module.get_vector_store().search(
        query_embedding=query_embedding,
        document_ids=document_ids,
        top_k=settings.top_k,
    )
    relevant = [hit for hit in hits if hit["distance"] <= settings.similarity_threshold]
    return relevant[:1]


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


def answer_question(db: Session, request: ChatRequest) -> ChatResponse:
    """Answer a RAG question and persist the conversation exchange."""
    settings = get_settings()

    documents = _resolve_documents(db, request.document_ids)
    document_ids = [document.id for document in documents]
    filenames = {document.id: document.filename for document in documents}

    conversation = _get_or_create_conversation(
        db, request.conversation_id, request.question, document_ids
    )

    try:
        hits = _retrieve(request.question, document_ids, settings)
        context = [
            SourceContext(
                document_id=hit["document_id"],
                filename=filenames.get(hit["document_id"], "unknown"),
                page_number=hit["page_number"],
                text=hit["text"],
            )
            for hit in hits
        ]

        history = _conversation_history(db, conversation)
        completer = build_chat_completer()
        answer = completer.complete(
            query=request.question,
            context=context,
            history=history,
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

    user_message = Message(
        conversation=conversation,
        role=MessageRole.USER.value,
        content=request.question,
    )
    assistant_message = Message(
        conversation=conversation,
        role=MessageRole.ASSISTANT.value,
        content=answer,
    )
    db.add_all([user_message, assistant_message])
    db.commit()

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

    db.refresh(conversation)
    logger.info(
        "Answered question in conversation %d using %d source(s)",
        conversation.id,
        len(sources),
    )
    return ChatResponse(
        conversation_id=conversation.id,
        answer=answer,
        sources=sources,
        review_recommended=flagged,
        provider_used=completer.provider,
        model_used=completer.model,
        generation_status="success",
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