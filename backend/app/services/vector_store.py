"""Vector store wrapper around ChromaDB.

The collection stores one embedding per document chunk, keyed by the
chunk's database row id, with metadata for filtering and citation
(page number, document id). The authoritative chunk text lives in
SQLite; the copy here is only for retrieval convenience.
"""

import os
from functools import lru_cache
from pathlib import Path

# ChromaDB reads telemetry settings at import time.
os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("CHROMA_TELEMETRY", "False")

import chromadb  # noqa: E402
from chromadb.api.models.Collection import Collection  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.logging import get_logger  # noqa: E402

logger = get_logger("vector_store")

_COLLECTION_NAME = "meddoc_chunks"


class VectorStore:
    """Persistence and retrieval of chunk embeddings in ChromaDB."""

    def __init__(self, chroma_dir: Path, collection: str = _COLLECTION_NAME) -> None:
        client = chromadb.PersistentClient(path=str(chroma_dir))
        self._collection: Collection = client.get_or_create_collection(
            name=collection,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert_chunks(self, entries: list[dict]) -> None:
        """Insert or update chunk embeddings.

        Each entry must contain: ``chunk_id`` (str), ``vector`` (list of
        float), ``document_id`` (int), ``page_number`` (int), and
        ``text`` (str).
        """
        if not entries:
            return
        self._collection.upsert(
            ids=[entry["chunk_id"] for entry in entries],
            embeddings=[entry["vector"] for entry in entries],
            documents=[entry["text"] for entry in entries],
            metadatas=[
                {
                    "document_id": entry["document_id"],
                    "page_number": entry["page_number"],
                }
                for entry in entries
            ],
        )
        logger.debug("Upserted %d chunk embeddings", len(entries))

    def delete_by_document(self, document_id: int) -> None:
        """Remove every embedding belonging to a document."""
        ids = self._collection.get(where={"document_id": document_id})["ids"]
        if ids:
            self._collection.delete(ids=ids)
            logger.debug("Deleted %d embeddings for document %d", len(ids), document_id)

    def search(
        self,
        query_embedding: list[float],
        document_ids: list[int] | None = None,
        top_k: int = 4,
    ) -> list[dict]:
        """Return the top-k nearest chunks, optionally restricted to docs.

        Distances are cosine distances (lower = more similar).
        """
        where = {"document_id": {"$in": document_ids}} if document_ids else None
        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        ids = results["ids"]
        if not ids or not ids[0]:
            return []

        hits: list[dict] = []
        for chunk_id, text, metadata, distance in zip(
            ids[0],
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            hits.append(
                {
                    "chunk_id": chunk_id,
                    "document_id": metadata["document_id"],
                    "page_number": metadata["page_number"],
                    "text": text,
                    "distance": distance,
                }
            )
        return hits

    def count(self) -> int:
        return self._collection.count()


@lru_cache
def get_vector_store() -> VectorStore:
    """Return a process-wide cached vector store for the default settings."""
    settings = get_settings()
    return VectorStore(chroma_dir=settings.chroma_dir)