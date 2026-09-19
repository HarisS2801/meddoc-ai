"""Deterministic evaluation metrics.

All metrics are pure functions computing one value from explicit inputs so
they can be unit-tested without any infrastructure. The term-based answer
check is a cheap, offline proxy; an optional LLM judge (see :mod:`judge`)
can replace it for real runs.
"""

import re

_WORD = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> set[str]:
    """Lowercase alphanumeric word tokens from ``text``."""
    return set(_WORD.findall(text.lower()))


def retrieval_precision(expected_ids: set[int], retrieved_ids: list[int]) -> float:
    """Fraction of retrieved documents that were expected (0.0 if none)."""
    if not retrieved_ids:
        return 0.0
    expected = len(expected_ids.intersection(retrieved_ids))
    return expected / len(retrieved_ids)


def retrieval_recall(expected_ids: set[int], retrieved_ids: list[int]) -> float:
    """Fraction of expected documents that were retrieved (0.0 if none)."""
    if not expected_ids:
        return 0.0
    retrieved = set(retrieved_ids)
    return len(expected_ids.intersection(retrieved)) / len(expected_ids)


def term_coverage(answer: str, expected_terms: list[str]) -> float:
    """Fraction of expected terms present in the answer (1.0 if none)."""
    if not expected_terms:
        return 1.0
    tokens = tokenize(answer)
    present = sum(1 for term in expected_terms if tokenize(term).issubset(tokens))
    return present / len(expected_terms)


def answer_correct(answer: str, expected_terms: list[str], threshold: float = 0.5) -> bool:
    """True when enough expected terms appear in the answer to be grounded."""
    return term_coverage(answer, expected_terms) >= threshold


def citation_correct(
    answer: str,
    sources: list[dict],
    expected_terms: list[str],
    expect_sources: bool,
) -> bool:
    """Check that citations are present and carry the expected facts.

    - ``expect_sources`` False: correct only when no evidence was returned.
    - Otherwise: at least one source chunk must contain an expected term.
    """
    if not expect_sources:
        return not sources

    if not sources:
        return False

    chunk_texts = [str(source.get("chunk_text") or "") for source in sources]
    expected_tokens = [tokenize(term) for term in expected_terms]
    if not expected_tokens:
        return True

    has_marker = bool(re.search(r"\[Source\s+\d+\]", answer))
    any_term_in_chunks = any(
        tokens and tokens.issubset(tokenize(chunk)) for tokens in expected_tokens for chunk in chunk_texts
    )
    return has_marker or any_term_in_chunks


def routing_correct(expected_review: bool, review_recommended: bool) -> bool:
    """True when the review guard made the routing the scenario expects."""
    return expected_review == review_recommended