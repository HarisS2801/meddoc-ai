"""RAG chat endpoints: ask questions and browse conversations."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationDetailOut,
    ConversationOut,
)
from app.services.chat_service import (
    answer_question,
    delete_conversation,
    get_conversation,
    list_conversations,
)

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def ask(request: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    return answer_question(db, request)


@router.get("/conversations", response_model=list[ConversationOut])
def conversations(db: Session = Depends(get_db)) -> list[ConversationOut]:
    return list_conversations(db)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
def conversation_detail(
    conversation_id: int, db: Session = Depends(get_db)
) -> ConversationDetailOut:
    return get_conversation(db, conversation_id)


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation_route(
    conversation_id: int, db: Session = Depends(get_db)
) -> Response:
    delete_conversation(db, conversation_id)
    return Response(status_code=204)