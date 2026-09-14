"""AI evaluation-result ORM model.

Stores one row per scenario evaluated, grouped by ``run_id``.
"""

from datetime import datetime, timezone

from sqlalchemy import Boolean, Float, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[str] = mapped_column(String(40), index=True)
    scenario_id: Mapped[str] = mapped_column(String(60))
    question: Mapped[str] = mapped_column(Text)
    retrieved_doc_ids: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    expected_doc_ids: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    answer: Mapped[str] = mapped_column(Text)
    retrieval_precision: Mapped[float] = mapped_column(Float, default=0.0)
    retrieval_recall: Mapped[float] = mapped_column(Float, default=0.0)
    answer_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    citation_correct: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<EvaluationResult run_id={self.run_id!r} scenario={self.scenario_id!r}>"