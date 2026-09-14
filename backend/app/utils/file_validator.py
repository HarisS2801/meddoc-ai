"""Upload validation helpers.

Validation is extension- and content-based: allowed file types are
limited to PDF and plain text, sizes are capped, and PDFs are sniffed by
their magic header rather than trusting the filename or content-type
header alone.
"""

from pathlib import Path

from app.core.config import get_settings
from app.core.exceptions import InvalidFileError

ALLOWED_EXTENSIONS = {".pdf", ".txt"}

CONTENT_TYPE_PDF = "application/pdf"
CONTENT_TYPE_TEXT = "text/plain"

_PDF_HEADER = b"%PDF-"


def validate_upload(filename: str, size: int) -> str:
    """Validate a filename and byte size; return the effective content type.

    Returns ``application/pdf`` or ``text/plain`` based on the file
    extension. Raises :class:`InvalidFileError` for unsupported types or
    oversized files.
    """
    settings = get_settings()
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise InvalidFileError("Only .pdf and .txt files are supported.")
    if size > settings.max_upload_size_bytes:
        raise InvalidFileError(
            f"Files must not exceed {settings.max_upload_size_mb} MB."
        )
    return CONTENT_TYPE_PDF if ext == ".pdf" else CONTENT_TYPE_TEXT


def sniff_pdf(data: bytes) -> None:
    """Reject files that claim to be PDFs but lack the %PDF magic header."""
    if not data.startswith(_PDF_HEADER):
        raise InvalidFileError("The file is not a valid PDF (missing %PDF header).")