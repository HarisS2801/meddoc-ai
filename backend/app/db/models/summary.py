"""Cached summary ORM model.

Each processed document stores the generated summary keyed by a content
fingerprint. Identical inputs hit the same row, so repeated summarize
requests return byte-for-byte the same answer without re-running the AI
provider on every page refresh.
"""

from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Summary(Base):
    __tablename__ = "summaries"
    __table_args__ = (
        UniqueConstraint(
            "document_id",
            "fingerprint",
            name="uq_summaries_document_fingerprint",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    fingerprint: Mapped[str] = mapped_column(String(64))
    summary: Mapped[str] = mapped_column(Text)
    source_pages: Mapped[str] = mapped_column(Text)
    document_type: Mapped[str] = mapped_column(String(120))
    notice: Mapped[str | None] = mapped_column(Text, nullable=True)
    structured: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(120))
    version: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )

    document: Mapped["Document"] = relationship(back_populates="summaries")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Summary id={self.id} document_id={self.document_id}>"