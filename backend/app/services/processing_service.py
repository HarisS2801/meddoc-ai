"""Document processing pipeline: extract -> clean -> chunk -> persist.

Each uploaded document runs through this service synchronously. The
document moves ``uploading -> processing -> processed`` on success, or to
``failed`` with an error message that the review workflow can surface.
"""

from pathlib import Path

from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import DocumentStatus
from app.core.exceptions import InvalidFileError
from app.core.logging import get_logger
from app.db.models import Document, DocumentChunk
from app.utils.file_validator import CONTENT_TYPE_PDF, CONTENT_TYPE_TEXT
from app.utils.text_cleaner import chunk_text, clean_text, is_empty_text

logger = get_logger("processing")


def extract_pdf_pages(path: Path) -> list[tuple[int, str]]:
    """Extract ``(page_number, raw_text)`` pairs, 1-indexed."""
    try:
        reader = PdfReader(str(path))
    except Exception as exc:
        logger.warning("Failed to parse PDF '%s': %s", path, exc)
        raise InvalidFileError("The PDF file is corrupted or could not be parsed.") from exc

    pages: list[tuple[int, str]] = []
    for index, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        pages.append((index, text))
    return pages


def extract_text(path: Path, content_type: str) -> list[tuple[int, str]]:
    """Return ``(page_number, raw_text)`` pairs for a stored file."""
    if content_type == CONTENT_TYPE_PDF:
        return extract_pdf_pages(path)
    if content_type == CONTENT_TYPE_TEXT:
        raw = path.read_text(encoding="utf-8", errors="replace")
        return [(1, raw)]
    raise InvalidFileError("Unsupported document content type.")


def process_document(db: Session, document: Document, file_path: Path) -> Document:
    """Run the full processing pipeline and update the document in place."""
    settings = get_settings()

    document.status = DocumentStatus.PROCESSING.value
    document.error_message = None
    db.commit()

    try:
        pages = extract_text(file_path, document.content_type)
    except InvalidFileError as exc:
        document.status = DocumentStatus.FAILED.value
        document.error_message = str(exc)
        db.commit()
        raise

    chunks: list[DocumentChunk] = []
    index = 0
    total_length = 0
    for page_number, raw_text in pages:
        cleaned = clean_text(raw_text)
        if is_empty_text(cleaned):
            continue
        for piece in chunk_text(cleaned, settings.chunk_size, settings.chunk_overlap):
            chunks.append(
                DocumentChunk(
                    chunk_index=index,
                    content=piece,
                    page_number=page_number,
                )
            )
            index += 1
            total_length += len(piece)

    if not chunks:
        document.status = DocumentStatus.FAILED.value
        document.error_message = "The document contains no extractable text."
        db.commit()
        raise InvalidFileError(document.error_message)

    document.status = DocumentStatus.PROCESSED.value
    document.chunk_count = len(chunks)
    document.page_count = len({chunk.page_number for chunk in chunks})
    document.extracted_text_len = total_length
    document.chunks = chunks
    db.commit()
    db.refresh(document)

    logger.info(
        "Processed '%s': %d chunks across %d pages",
        document.filename,
        document.chunk_count,
        document.page_count,
    )
    return document