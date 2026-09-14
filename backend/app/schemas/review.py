from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import ReviewReason, ReviewStatus


class ReviewItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    message_id: int | None = None
    question: str
    answer: str
    context: list[dict] | dict | None = None
    sources: list[dict] | None = None
    reason: ReviewReason
    status: ReviewStatus
    reviewer_comment: str | None = None
    created_at: datetime
    reviewed_at: datetime | None = None


class ReviewDecisionRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)