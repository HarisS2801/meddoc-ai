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
    provider_used: str = "groq"
    model_used: str = ""
    generation_status: str = "success"
    # Deterministic routing label that produced this answer; one of the
    # QuestionIntent values (e.g. document_type_query, medical_value_query).
    intent: str | None = None
    # Populated only when RETRIEVAL_DEBUG=true (structured retrieval
    # telemetry); always None otherwise so production responses stay lean.
    debug: dict | None = None


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