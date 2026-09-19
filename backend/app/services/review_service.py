"""Human review workflow: inspect and decide on flagged outputs.

Review items are created upstream (RAG chat, extraction, processing
failures). This service lists the queue, shows one item, and records a
human decision (approve / reject) with an optional comment.
"""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.enums import ReviewStatus
from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.db.models import ReviewItem

logger = get_logger("review")


def list_review_items(
    db: Session, status: ReviewStatus | None = None
) -> list[ReviewItem]:
    """Return the review queue, oldest first, optionally filtered by status."""
    stmt = select(ReviewItem).order_by(ReviewItem.created_at.asc())
    if status is not None:
        stmt = stmt.where(ReviewItem.status == status.value)
    return list(db.scalars(stmt).all())


def get_review_item(db: Session, review_id: int) -> ReviewItem:
    review = db.get(ReviewItem, review_id)
    if review is None:
        raise NotFoundError(f"Review item {review_id} not found.")
    return review


def decide_review_item(
    db: Session,
    review_id: int,
    decision: ReviewStatus,
    comment: str | None = None,
) -> ReviewItem:
    """Approve or reject a review item. Only pending items can be decided."""
    review = get_review_item(db, review_id)
    if review.status != ReviewStatus.PENDING.value:
        raise ConflictError(f"Review item {review_id} has already been decided.")

    review.status = decision.value
    review.reviewer_comment = comment
    review.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(review)

    logger.info("Review item %d %s", review_id, decision.value)
    return review


def review_stats(db: Session) -> dict[str, int]:
    """Return queue counts per status for the review dashboard."""
    rows = db.execute(
        select(ReviewItem.status, func.count(ReviewItem.id)).group_by(ReviewItem.status)
    ).all()
    counts = {status: count for status, count in rows}
    return {
        ReviewStatus.PENDING.value: counts.get(ReviewStatus.PENDING.value, 0),
        ReviewStatus.APPROVED.value: counts.get(ReviewStatus.APPROVED.value, 0),
        ReviewStatus.REJECTED.value: counts.get(ReviewStatus.REJECTED.value, 0),
    }