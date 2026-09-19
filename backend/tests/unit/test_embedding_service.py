"""Tests for the local lexical embedding service (fully offline).

Groq offers no embedding API, so retrieval uses deterministic local
lexical vectors. These tests pin the provider's offline contract.
"""

import math

from app.core.config import Settings
from app.services.embedding_service import (
    EmbeddingService,
    LexicalEmbeddingProvider,
    build_embedding_service,
)

DIMENSIONS = 1536


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class TestLexicalEmbeddingProvider:
    def test_dimensions(self):
        assert LexicalEmbeddingProvider(DIMENSIONS).dimensions == DIMENSIONS

    def test_kind_is_lexical(self):
        assert LexicalEmbeddingProvider(DIMENSIONS).kind == "lexical"

    def test_deterministic_for_same_text(self):
        provider = LexicalEmbeddingProvider(DIMENSIONS)
        a = provider._embed_single("follow-up appointment")
        b = provider.embed_texts(["follow-up appointment"])[0]
        assert a == b

    def test_different_texts_give_different_vectors(self):
        provider = LexicalEmbeddingProvider(DIMENSIONS)
        a = provider.embed_texts(["metformin dose"])[0]
        b = provider.embed_texts(["the weather today"])[0]
        assert a != b

    def test_vector_values_within_unit_range(self):
        vector = LexicalEmbeddingProvider(DIMENSIONS)._embed_single("sample")
        assert len(vector) == DIMENSIONS
        assert all(-1.0 <= value <= 1.0 for value in vector)

    def test_related_text_is_closer_than_unrelated_text(self):
        provider = LexicalEmbeddingProvider(DIMENSIONS)
        chunk = "Metformin 500 mg twice daily with meals"
        related = "What dose of metformin is taken?"
        unrelated = "What is the weather forecast for Paris tomorrow?"
        chunk_v = provider._embed_single(chunk)
        assert _cosine(chunk_v, provider._embed_single(related)) > _cosine(
            chunk_v, provider._embed_single(unrelated)
        )

    def test_stopword_only_text_does_not_bias_similarity(self):
        provider = LexicalEmbeddingProvider(DIMENSIONS)
        chunk = "the target fasting glucose range"
        related = "fasting glucose target"
        different = "the weather forecast in the city"
        chunk_v = provider._embed_single(chunk)
        assert _cosine(chunk_v, provider._embed_single(related)) > _cosine(
            chunk_v, provider._embed_single(different)
        )

    def test_identical_text_has_zero_cosine_distance(self):
        provider = LexicalEmbeddingProvider(DIMENSIONS)
        a = provider._embed_single("Target fasting glucose: 80-130 mg/dL")
        b = provider._embed_single("Target fasting glucose: 80-130 mg/dL")
        assert _cosine(a, b) == 1.0


class TestEmbeddingService:
    def test_embed_texts_returns_same_length(self):
        service = EmbeddingService(provider=LexicalEmbeddingProvider(DIMENSIONS))
        vectors = service.embed_texts(["a", "bb", "ccc"])
        assert len(vectors) == 3
        assert all(len(v) == DIMENSIONS for v in vectors)

    def test_embed_text_is_singleton(self):
        service = EmbeddingService(provider=LexicalEmbeddingProvider(DIMENSIONS))
        assert service.embed_text("hello") == service.embed_texts(["hello"])[0]

    def test_lexical_service_reports_lexical(self):
        service = EmbeddingService(provider=LexicalEmbeddingProvider(DIMENSIONS))
        assert service.is_lexical is True
        assert service.kind == "lexical"


class TestBuildEmbeddingService:
    def test_always_returns_lexical_provider(self):
        service = build_embedding_service(settings=Settings(groq_api_key=""))
        assert isinstance(service._provider, LexicalEmbeddingProvider)
        assert service.kind == "lexical"
        assert service.is_lexical is True
        assert service.dimensions == Settings(groq_api_key="").embedding_dimensions

    def test_with_groq_key_still_returns_lexical_provider(self):
        service = build_embedding_service(settings=Settings(groq_api_key="test-key"))
        assert isinstance(service._provider, LexicalEmbeddingProvider)
        assert service.kind == "lexical"

    def test_respects_embedding_dimensions(self):
        service = build_embedding_service(settings=Settings(embedding_dimensions=768))
        assert service.dimensions == 768