"""Text-cleaning and chunking utilities for extracted document content."""

import re

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MULTI_SPACE = re.compile(r"[ \t\u00a0]{2,}")
_MULTI_NEWLINE = re.compile(r"\n{3,}")


def clean_text(raw: str) -> str:
    """Normalise whitespace and strip control characters.

    - Converts CRLF/CR to plain LF
    - Removes non-printable control characters
    - Trims each line, collapses runs of spaces/tabs (incl. non-breaking)
    - Keeps paragraph breaks (blank lines) intact
    """
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_CHARS.sub("", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _MULTI_NEWLINE.sub("\n\n", text)
    text = _MULTI_SPACE.sub(" ", text)
    return text.strip()


def is_empty_text(text: str) -> bool:
    """True when a text blob carries no meaningful content."""
    return not text or not text.strip()


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split cleaned text into overlapping chunks.

    Chunks try to stay on paragraph boundaries (anchor at blank lines)
    so splits do not break meaning mid-sentence. Paragraphs longer than
    ``chunk_size`` are split on word boundaries. When ``overlap > 0``,
    each chunk repeats the tail of the previous chunk at its start, which
    preserves continuity for similarity search on questions spanning a
    boundary.
    """
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    if not paragraphs:
        return []

    chunks: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        if buffer:
            chunks.append(" ".join(buffer))
            buffer.clear()

    for paragraph in paragraphs:
        if len(paragraph) > chunk_size:
            flush()
            chunks.extend(_split_long_paragraph(paragraph, chunk_size))
            continue
        buffer_len = sum(len(p) + 1 for p in buffer)
        if buffer and buffer_len + len(paragraph) + 1 > chunk_size:
            flush()
        buffer.append(paragraph)
    flush()

    if overlap > 0 and len(chunks) > 1:
        chunks = _apply_overlap(chunks, overlap)
    return chunks


def _split_long_paragraph(text: str, chunk_size: int) -> list[str]:
    """Split a paragraph that exceeds chunk_size on word boundaries."""
    pieces: list[str] = []
    words: list[str] = []
    length = 0
    for word in text.split():
        if words and length + len(word) + 1 > chunk_size:
            pieces.append(" ".join(words))
            words = [word]
            length = len(word)
        else:
            words.append(word)
            length += len(word) + 1
    if words:
        pieces.append(" ".join(words))
    return pieces


def _apply_overlap(chunks: list[str], overlap: int) -> list[str]:
    """Prefix each chunk with the tail of its predecessor."""
    result = [chunks[0]]
    for chunk in chunks[1:]:
        tail = result[-1][-overlap:].strip()
        result.append(f"{tail} {chunk}".strip() if tail else chunk)
    return result