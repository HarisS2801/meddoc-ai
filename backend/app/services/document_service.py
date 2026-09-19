"""Document lifecycle operations: upload, retrieve, list, delete."""

import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.enums import DocumentStatus
from app.core.exceptions import AppError, InvalidFileError, NotFoundError
from app.core.logging import get_logger
from app.db.models import Document
from app.services import vector_store as vector_store_module
from app.services.processing_service import embed_document_chunks, process_document
from app.utils.file_validator import CONTENT_TYPE_PDF, sniff_pdf, validate_upload

logger = get_logger("documents")


def upload_document(db: Session, file: UploadFile) -> Document:
    """Validate, persist, and process an uploaded file into a document."""
    settings = get_settings()
    filename = file.filename or "unnamed"
    content = file.file.read()

    content_type = validate_upload(filename, len(content))
    if content_type == CONTENT_TYPE_PDF:
        sniff_pdf(content)

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{Path(filename).suffix.lower() or ''}"
    dest = settings.upload_dir / stored_name
    dest.write_bytes(content)

    document = Document(
        filename=filename,
        title=Path(filename).stem,
        content_type=content_type,
        storage_path=str(dest),
        status=DocumentStatus.UPLOADING.value,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    try:
        processed = process_document(db, document, dest)
    except InvalidFileError:
        raise
    except Exception as exc:
        document.status = DocumentStatus.FAILED.value
        document.error_message = "An unexpected processing error occurred."
        try:
            db.commit()
        except Exception:
            db.rollback()
        logger.exception("Unexpected error while processing '%s'", filename)
        raise AppError(
            "The document could not be processed.",
            status_code=500,
            code="processing_failed",
        ) from exc

    _embed_document(db, processed)
    return processed


def _embed_document(db: Session, document: Document) -> None:
    """Best-effort vector indexing; never fails the upload."""
    try:
        embed_document_chunks(db, document)
    except Exception:
        logger.exception(
            "Embedding failed for '%s'; document kept as processed without vectors.",
            document.filename,
        )


def list_documents(db: Session) -> list[Document]:
    stmt = select(Document).order_by(Document.created_at.desc())
    return list(db.scalars(stmt).all())


def get_document(db: Session, document_id: int) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise NotFoundError(f"Document {document_id} not found.")
    return document


def delete_document(db: Session, document_id: int) -> None:
    """Delete a document, its chunks (cascade), vectors, and stored file."""
    document = get_document(db, document_id)
    stored = Path(document.storage_path)
    if stored.exists():
        stored.unlink()
    try:
        vector_store_module.get_vector_store().delete_by_document(document_id)
    except Exception:
        logger.exception("Failed to clean up vectors for document %d", document_id)
    db.delete(document)
    db.commit()