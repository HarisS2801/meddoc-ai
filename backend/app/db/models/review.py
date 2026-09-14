"""Human-review queue ORM model.

A review item is created whenever the pipeline determines that a human
should look at the output — low confidence, unsupported answer, medical
advice requested, etc.
"""

from datetime import datetime, timezone

from sqlalchemy import Integer, String, Text, ForeignKey
from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.core.enums import ReviewStatus


class ReviewItem(Base):
    __tablename__ = "review_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("messages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    sources: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reason: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(
        String(20), default=ReviewStatus.PENDING.value
    )
    reviewer_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    message: Mapped["Message | None"] = relationship(  # noqa: F821
        back_populates="review_item"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ReviewItem id={self.id} status={self.status!r}>"