"""Dev-only RAG retrieval debug endpoint.

Lets an engineer (or a test) prove, without calling Groq, which chunks are
retrieved for a real question and whether the medical value actually survived
in the stored chunk text. Independent of the prompt: it proves the chunk
store, not the model, is the source of truth.

This endpoint is **never registered in production**. The router is only
mounted when ``RETRIEVAL_DEBUG=true`` (see ``app/main.py``), and the handler
also re-checks the flag defensively. It returns chunk text (patient data), so
it must stay behind that flag; it is the explicit, deliberate dev escape
hatch of the spec.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import get_settings
from app.db.models import Document, DocumentChunk

router = APIRouter(prefix="/retrieval/debug", tags=["retrieval-debug"])


@router.get("/inspect")
def inspect_retrieval_debug(
    document_id: int = Query(...),
    question: str = Query(..., min_length=1, max_length=300),
    db: Session = Depends(get_db),
) -> dict:
    """Return retrieval telemetry for ``question`` scoped to ``document_id``.

    Response mirrors the ``debug`` payload the chat endpoint would log, but
    without requiring a Greeting/Groq round trip, so it can be diffed against
    whether the value actually reached the model.
    """
    settings = get_settings()
    if not settings.retrieval_debug:
        raise HTTPException(status_code=404, detail="Retrieval debug is not enabled.")

    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail=f"Document {document_id} not found.")

    chunk_count = db.scalar(
        select(func.count())
        .select_from(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
    )

    from app.services import retrieval as retrieval_module

    hits = retrieval_module.hybrid_retrieve(
        db, question=question, document_ids=[document_id], settings=settings
    )

    return {
        "document_id": document_id,
        "filename": document.filename,
        "extracted_text_length": document.extracted_text_len,
        "chunk_count": chunk_count,
        "query": question,
        "num_retrieved_chunks": len(hits),
        "retrieved_chunks": [
            {
                "chunk_id": hit["chunk_id"],
                "document_id": hit["document_id"],
                "page_number": hit["page_number"],
                "score": hit["score"],
                "distance": hit["distance"],
                "matched_terms": hit.get("matched_terms", []),
                "text": hit["text"],
            }
            for hit in hits
        ],
        "context_length": sum(len(hit["text"]) for hit in hits),
    }
