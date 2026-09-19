"""Unit tests for the deterministic evaluation metrics."""

from evaluation.harness.scores import (
    answer_correct,
    citation_correct,
    retrieval_precision,
    retrieval_recall,
    routing_correct,
    term_coverage,
    tokenize,
)


class TestTokenize:
    def test_lowercases_and_strips_punctuation(self):
        assert tokenize("Fasting glucose: 80-130 mg/dL") == {
            "fasting",
            "glucose",
            "80",
            "130",
            "mg",
            "dl",
        }

    def test_empty_text(self):
        assert tokenize("") == set()


class TestRetrieval:
    def test_precision_overlap(self):
        assert retrieval_precision({1, 2}, [1, 3]) == 0.5

    def test_precision_empty_retrieval_is_zero(self):
        assert retrieval_precision({1, 2}, []) == 0.0

    def test_recall_overlap(self):
        assert retrieval_recall({1, 2}, [1, 3]) == 0.5

    def test_recall_empty_expected_is_zero(self):
        assert retrieval_recall(set(), [1]) == 0.0

    def test_perfect_match(self):
        assert retrieval_precision({1}, [1]) == 1.0
        assert retrieval_recall({1}, [1]) == 1.0


class TestAnswer:
    def test_term_coverage_full(self):
        assert term_coverage("Take 500 mg twice daily.", ["500", "twice"]) == 1.0

    def test_term_coverage_partial(self):
        assert term_coverage("Take 500 mg daily.", ["500", "twice"]) == 0.5

    def test_term_coverage_empty_terms(self):
        assert term_coverage("Anything.", []) == 1.0

    def test_answer_correct_at_threshold(self):
        assert answer_correct("Take 500 mg daily.", ["500", "twice"]) is True

    def test_answer_correct_below_threshold(self):
        assert (
            answer_correct("Take 500 mg daily.", ["500", "twice", "night", "dose"])
            is False
        )


class TestCitation:
    def test_correct_with_term_in_chunk(self):
        sources = [{"chunk_text": "Target fasting glucose 80-130 mg/dL."}]
        assert citation_correct("80 to 130 mg/dL", sources, ["80", "130"], True)

    def test_correct_with_source_marker_even_without_term(self):
        sources = [{"chunk_text": "Some unrelated text."}]
        assert citation_correct(
            "Answer [Source 1] says 95.", sources, ["80", "130"], True
        )

    def test_incorrect_when_source_missing_term_and_no_marker(self):
        sources = [{"chunk_text": "Some unrelated text."}]
        assert not citation_correct("The answer is 95.", sources, ["80", "130"], True)

    def test_no_sources_when_none_expected(self):
        assert citation_correct("I could not find that.", [], [], False)

    def test_sources_when_none_expected_is_wrong(self):
        assert not citation_correct("I could not find that.", [{"chunk_text": "x"}], [], False)


class TestRouting:
    def test_matches(self):
        assert routing_correct(True, True)
        assert routing_correct(False, False)

    def test_mismatch(self):
        assert not routing_correct(True, False)
        assert not routing_correct(False, True)