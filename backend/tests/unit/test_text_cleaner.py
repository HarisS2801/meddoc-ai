"""Tests for the text-cleaning and chunking utilities."""

from app.utils.text_cleaner import chunk_text, clean_text, is_empty_text


class TestCleanText:
    def test_normalises_line_endings(self):
        assert clean_text("a\r\nb\r\n\r\nc") == "a\nb\n\nc"

    def test_strips_control_characters(self):
        assert clean_text("a\x00b\x1fc") == "abc"

    def test_collapses_runs_of_spaces(self):
        assert clean_text("a    b\t\t c") == "a b c"

    def test_strips_surrounding_whitespace(self):
        assert clean_text("  hello  \n\n") == "hello"

    def test_empty_input(self):
        assert clean_text("") == ""

    def test_is_empty_text(self):
        assert is_empty_text("")
        assert is_empty_text("   \n\t ")
        assert not is_empty_text("text")


class TestChunkText:
    def test_short_text_returns_single_chunk(self):
        chunks = chunk_text("The patient is doing well.", 800, 120)
        assert chunks == ["The patient is doing well."]

    def test_empty_text_returns_no_chunks(self):
        assert chunk_text("", 800, 120) == []

    def test_multiple_chunks_and_size_bounds(self):
        paragraph = " ".join(["word"] * 25)  # ~100 chars each time we repeat it
        big = "\n\n".join([paragraph] * 25)  # ~2500 chars
        chunks = chunk_text(big, 800, 120)

        assert len(chunks) >= 3
        for chunk in chunks:
            assert len(chunk) <= 800 + 120 + 5

    def test_overlap_connects_consecutive_chunks(self):
        chunk_size = 200
        overlap = 50
        big = "\n\n".join(["sentence %d here" % i for i in range(40)])
        chunks = chunk_text(big, chunk_size, overlap)

        assert len(chunks) >= 2
        for previous, current in zip(chunks, chunks[1:]):
            tail = previous[-overlap:].strip()
            assert tail in current

    def test_no_overlap_when_overlap_is_zero(self):
        big = "\n\n".join(["sentence %d here" % i for i in range(40)])
        chunks = chunk_text(big, 200, 0)
        assert len(chunks) >= 2

    def test_long_single_paragraph_is_split(self):
        huge = "absolutely " * 500
        chunks = chunk_text(huge, 800, 120)
        assert len(chunks) >= 5
        for chunk in chunks:
            assert len(chunk) <= 800 + 120 + 5