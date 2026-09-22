from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.core.enums import DocumentStatus


class DocumentBase(BaseModel):
    filename: str
    title: str | None = None
    content_type: str


class DocumentOut(DocumentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: DocumentStatus
    report_type: str | None = None
    report_header: str | None = None
    extracted_text_len: int
    page_count: int
    chunk_count: int
    error_message: str | None = None
    created_at: datetime