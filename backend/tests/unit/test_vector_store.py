"""Tests for the ChromaDB-backed vector store."""

from app.services.vector_store import VectorStore


def _make_store(tmp_path) -> VectorStore:
    return VectorStore(chroma_dir=tmp_path / "chroma")


def _entries(document_id: int, pairs: list[tuple[str, list[float]]]) -> list[dict]:
    return [
        {
            "chunk_id": chunk_id,
            "vector": vector,
            "document_id": document_id,
            "page_number": i + 1,
            "text": f"chunk text {chunk_id}",
        }
        for i, (chunk_id, vector) in enumerate(pairs)
    ]


class TestVectorStore:
    def test_count_and_upsert(self, tmp_path):
        store = _make_store(tmp_path)
        assert store.count() == 0

        store.upsert_chunks(
            _entries(1, [("c1", [1.0, 0.0, 0.0]), ("c2", [0.0, 1.0, 0.0])])
        )
        assert store.count() == 2

    def test_upsert_empty_is_noop(self, tmp_path):
        store = _make_store(tmp_path)
        store.upsert_chunks([])
        assert store.count() == 0

    def test_search_returns_nearest_first(self, tmp_path):
        store = _make_store(tmp_path)
        store.upsert_chunks(
            _entries(
                1,
                [
                    ("near", [0.99, 0.02, 0.01]),
                    ("far", [0.01, 0.97, 0.10]),
                ],
            )
        )
        hits = store.search(query_embedding=[1.0, 0.0, 0.0], top_k=2)
        assert [h["chunk_id"] for h in hits] == ["near", "far"]
        assert hits[0]["document_id"] == 1
        assert hits[0]["distance"] < hits[1]["distance"]

    def test_search_restricted_to_document_ids(self, tmp_path):
        store = _make_store(tmp_path)
        store.upsert_chunks(
            _entries(1, [("d1c1", [1.0, 0.0])])
            + _entries(2, [("d2c1", [0.99, 0.01])])
        )
        hits = store.search(query_embedding=[1.0, 0.0], document_ids=[2])
        assert len(hits) == 1
        assert hits[0]["chunk_id"] == "d2c1"

    def test_search_empty_store_returns_empty(self, tmp_path):
        store = _make_store(tmp_path)
        assert store.search(query_embedding=[1.0, 0.0]) == []

    def test_delete_by_document_removes_only_that_document(self, tmp_path):
        store = _make_store(tmp_path)
        store.upsert_chunks(
            _entries(1, [("d1c1", [1.0, 0.0]), ("d1c2", [0.5, 0.5])])
            + _entries(2, [("d2c1", [0.0, 1.0])])
        )

        store.delete_by_document(1)

        assert store.count() == 1
        remaining = store.search(query_embedding=[0.0, 1.0], top_k=5)
        assert [h["chunk_id"] for h in remaining] == ["d2c1"]

    def test_search_metadata_exposed_for_citations(self, tmp_path):
        store = _make_store(tmp_path)
        store.upsert_chunks(_entries(7, [("c9", [1.0, 0.0])]))
        hits = store.search(query_embedding=[1.0, 0.0])
        assert hits[0]["page_number"] == 1
        assert hits[0]["text"].startswith("chunk text")