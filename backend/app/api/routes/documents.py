"""Document upload, list, detail, delete, summarize, and extract endpoints."""

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.exceptions import ConflictError, NotFoundError
from app.db.models import Document
from app.schemas.document import DocumentOut
from app.schemas.extraction import ExtractionRequest, ExtractionResponse
from app.schemas.summarization import SummaryResponse
from app.services.document_service import delete_document, list_documents, upload_document
from app.services.extraction_service import extract_document
from app.services.summarization_service import summarize_document_bundle

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentOut, status_code=201)
def upload(file: UploadFile = File(...), db: Session = Depends(get_db)) -> Document:
    return upload_document(db, file)


@router.get("", response_model=list[DocumentOut])
def list_doc(db: Session = Depends(get_db)) -> list[Document]:
    return list_documents(db)


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(document_id: int, db: Session = Depends(get_db)) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise NotFoundError(f"Document {document_id} not found.")
    return document


@router.delete("/{document_id}", status_code=204)
def delete_document_route(
    document_id: int, db: Session = Depends(get_db)
) -> Response:
    delete_document(db, document_id)
    return Response(status_code=204)


@router.post("/{document_id}/summarize", response_model=SummaryResponse)
def summarize_document_route(
    document_id: int,
    force: bool = Query(False, description="Regenerate and overwrite the cached summary."),
    db: Session = Depends(get_db),
) -> SummaryResponse:
    bundle = summarize_document_bundle(db, document_id, force=force)
    return SummaryResponse(
        document_id=document_id,
        summary=bundle.summary,
        source_pages=bundle.source_pages,
        document_type=bundle.document_type,
        notice=bundle.notice,
        structured=bundle.structured,
        provider_used=bundle.provider,
        model_used=bundle.model,
        generation_status=bundle.generation_status,
        cached=bundle.cached,
    )


@router.post("/{document_id}/extract", response_model=ExtractionResponse)
def extract_document_route(
    document_id: int,
    request: ExtractionRequest,
    db: Session = Depends(get_db),
) -> ExtractionResponse:
    if request.document_id != document_id:
        raise ConflictError("The document id in the request body does not match the URL.")
    return extract_document(db, document_id, request.extraction_type)