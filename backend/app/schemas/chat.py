from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import MessageRole


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: int | None = None
    document_ids: list[int] | None = None


class SourceRef(BaseModel):
    document_id: int
    filename: str
    page_number: int | None = None
    chunk_text: str | None = None


class ChatResponse(BaseModel):
    conversation_id: int
    answer: str
    sources: list[SourceRef]
    review_recommended: bool


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: MessageRole
    content: str
    created_at: datetime


class ConversationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime
    updated_at: datetime


class ConversationDetailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[MessageOut]