"""Document upload, list, detail, and delete endpoints."""

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.exceptions import NotFoundError
from app.db.models import Document
from app.schemas.document import DocumentOut
from app.services.document_service import delete_document, list_documents, upload_document

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