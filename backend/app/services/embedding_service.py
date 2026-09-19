"""Embedding service.

Groq — the only AI provider in MedDoc AI — offers no embedding API, so
retrieval uses deterministic local lexical vectors. Vectors encode term
presence (stopword-filtered, sub-linear TF, L2-normalised) so that texts
sharing content words are cosine-similar.

This is a lexical approximation of retrieval only -- it cannot capture
same-meaning synonyms or paraphrase -- but it is fully private, runs fully
offline, costs nothing, and is a faithful stand-in for protecting the RAG
pipeline. No external embedding API is ever called.
"""

import hashlib
import math
import re
from collections import Counter

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger("embedding")

_LEXICAL_SALT = "meddoc-lexical"

# Content words only; dropping closed-class tokens keeps lexical
# similarity driven by subject matter instead of filler words.
_STOPWORDS = frozenset(
    (
        "a", "an", "and", "are", "as", "at", "be", "been", "being", "but",
        "by", "can", "could", "did", "do", "does", "for", "from", "had",
        "has", "have", "he", "her", "his", "how", "i", "if", "in", "into",
        "is", "it", "its", "of", "on", "or", "she", "should", "so", "than",
        "that", "the", "their", "them", "then", "there", "these", "they",
        "this", "to", "was", "we", "were", "what", "when", "where", "which",
        "who", "will", "with", "would", "you", "your",
        "doe", "dont", "doesnt", "didnt", "hadn", "hasn", "havent", "isnt",
        "arent", "wasnt", "werent", "wouldn", "shouldn", "couldnt", "not",
    )
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")


class LexicalEmbeddingProvider:
    """Deterministic, dependency-free local lexical embeddings.

    Vectors are built from the text's content words: stopwords are
    removed, each remaining token gets a sub-linear TF weight
    (``1 + log(count)``) mapped to a stable hashed dimension, and the
    result is L2-normalised so cosine similarity measures shared
    vocabulary. Identical text always yields the identical vector; related
    text is closer than unrelated text. No network, no provider.
    """

    def __init__(self, dimensions: int = 1536) -> None:
        self._dimensions = dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    @property
    def kind(self) -> str:
        return "lexical"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_single(text) for text in texts]

    def embed_text(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def _tokens(self, text: str) -> list[str]:
        lowered = text.lower()
        return [tok for tok in _TOKEN_RE.findall(lowered) if tok not in _STOPWORDS]

    def _index(self, token: str) -> int:
        digest = hashlib.sha256(f"{_LEXICAL_SALT}:{token}".encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big") % self._dimensions

    def _embed_single(self, text: str) -> list[float]:
        counts = Counter(self._tokens(text))
        if not counts:
            vector = self._fallback_vector(text)
            norm = math.sqrt(sum(x * x for x in vector)) or 1.0
            return [x / norm for x in vector]

        vector = [0.0] * self._dimensions
        for token, count in counts.items():
            vector[self._index(token)] += 1.0 + math.log(count)

        norm = math.sqrt(sum(x * x for x in vector))
        if norm > 0:
            vector = [x / norm for x in vector]
        return vector

    def _fallback_vector(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        vector: list[float] = []
        while len(vector) < self._dimensions:
            for byte in digest:
                if len(vector) == self._dimensions:
                    break
                vector.append((byte - 128) / 128.0)
        return vector


class EmbeddingService:
    """Facade over the local lexical embedding provider."""

    def __init__(self, provider: LexicalEmbeddingProvider) -> None:
        self._provider = provider

    @property
    def dimensions(self) -> int:
        return self._provider.dimensions

    @property
    def kind(self) -> str:
        return self._provider.kind

    @property
    def is_lexical(self) -> bool:
        return self._provider.kind == "lexical"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return self._provider.embed_texts(texts)

    def embed_text(self, text: str) -> list[float]:
        return self._provider.embed_text(text)


def build_embedding_service(settings=get_settings()) -> EmbeddingService:
    """Build the local lexical embedding service (the only embedding path).

    Groq has no embedding API and no other AI provider is configured, so
    embeddings are always computed locally and deterministically.
    """
    provider = LexicalEmbeddingProvider(settings.embedding_dimensions)
    logger.info(
        "Using local lexical embeddings (%d dims) - fully offline, no AI provider.",
        settings.embedding_dimensions,
    )
    return EmbeddingService(provider=provider)