"""Diagnostic tests for the upload -> index -> retrieve pipeline.

Pinpoint why ``POST /api/chat`` with ``document_ids=[3]`` reports
"No context or uploaded document was provided" even though
``GET /api/documents/3`` shows a fully processed document.

These tests exercise the *real* retrieval path (``VectorStore.search``
and ``chat_service._retrieve``) against an indexed document id 3 and
prove that the mechanism itself can return a relevant chunk.
"""

from sqlalchemy import select

from app.core.config import get_settings
from app.core.enums import DocumentStatus
from app.db.models import Document, DocumentChunk
from app.schemas.chat import ChatRequest
from app.services.chat_service import _retrieve, answer_question
from app.services.embedding_service import build_embedding_service
from app.services.vector_store import VectorStore

CONTENT = (
    "CARE PLAN GOALS\n"
    "- Target fasting glucose: 80-130 mg/dL\n"
    "- Target A1c: below 7.0%\n"
    "- Next appointment: 2026-08-20\n\n"
    "MEDICATIONS\n"
    "- Metformin 500 mg twice daily with meals.\n"
    "- Atorvastatin 20 mg once daily at bedtime.\n"
)


def _make_processed_document(db_session) -> tuple[Document, list[DocumentChunk]]:
    """Create a processed document with id 3 as the only seeded row."""
    document = Document(
        id=3,
        filename="sample.txt",
        title="Sample",
        content_type="text/plain",
        storage_path="/tmp/sample.txt",
        status=DocumentStatus.PROCESSED.value,
        extracted_text_len=len(CONTENT),
        page_count=1,
        chunk_count=2,
    )
    document.chunks = [
        DocumentChunk(chunk_index=0, content=CONTENT, page_number=1),
        DocumentChunk(chunk_index=1, content=CONTENT, page_number=1),
    ]
    db_session.add(document)
    db_session.commit()
    db_session.refresh(document)
    return document, list(document.chunks)


class TestDocumentThreeRetrievable:
    def test_stored_chunks_are_retrievable_for_document_three(
        self, db_session, vector_store: VectorStore
    ):
        _, chunks = _make_processed_document(db_session)
        assert chunks[0].document_id == 3

        service = build_embedding_service()
        vector_store.upsert_chunks(
            [
                {
                    "chunk_id": str(chunk.id),
                    "vector": service.embed_text(chunk.content),
                    "document_id": chunk.document_id,
                    "page_number": chunk.page_number,
                    "text": chunk.content,
                }
                for chunk in chunks
            ]
        )
        assert vector_store.count() == 2

        query = "What fasting glucose range does the care plan target?"
        hits = vector_store.search(
            query_embedding=service.embed_text(query),
            document_ids=[3],
            top_k=get_settings().top_k,
        )

        assert len(hits) >= 1
        assert all(hit["document_id"] == 3 for hit in hits)
        assert all(hit["page_number"] == 1 for hit in hits)

    def test_retrieve_gate_returns_a_chunk_for_document_three(
        self, db_session, vector_store: VectorStore
    ):
        _, chunks = _make_processed_document(db_session)
        service = build_embedding_service()
        vector_store.upsert_chunks(
            [
                {
                    "chunk_id": str(chunk.id),
                    "vector": service.embed_text(chunk.content),
                    "document_id": chunk.document_id,
                    "page_number": chunk.page_number,
                    "text": chunk.content,
                }
                for chunk in chunks
            ]
        )

        question = "Which medications are listed in the care plan?"
        hits = _retrieve(question, [3], get_settings())

        assert len(hits) >= 1
        assert hits[0]["document_id"] == 3

    def test_answer_question_grounds_on_document_three(
        self, db_session, vector_store: VectorStore
    ):
        _, chunks = _make_processed_document(db_session)
        service = build_embedding_service()
        vector_store.upsert_chunks(
            [
                {
                    "chunk_id": str(chunk.id),
                    "vector": service.embed_text(chunk.content),
                    "document_id": chunk.document_id,
                    "page_number": chunk.page_number,
                    "text": chunk.content,
                }
                for chunk in chunks
            ]
        )

        response = answer_question(
            db_session,
            ChatRequest(
                question="Which medications are listed in the care plan?",
                document_ids=[3],
            ),
        )

        assert response.sources, "expected at least one grounded source"
        assert all(source.document_id == 3 for source in response.sources)
        assert response.answer
        assert response.review_recommended is False

    def test_chromadb_metadata_roundtrips_document_id_as_int(self, vector_store):
        """Guard against the WHERE-filter doc-id type mismatch class of bugs."""
        service = build_embedding_service()
        vector_store.upsert_chunks(
            [
                {
                    "chunk_id": "c1",
                    "vector": service.embed_text("glucose target 130 mg/dL"),
                    "document_id": 3,
                    "page_number": 1,
                    "text": "glucose target 130 mg/dL",
                }
            ]
        )
        stored = vector_store.search(
            query_embedding=service.embed_text("glucose target"),
            document_ids=[3],
        )
        assert len(stored) == 1
        assert stored[0]["document_id"] == 3
        assert type(stored[0]["document_id"]) is int