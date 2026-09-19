"""Human review workflow endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.enums import ReviewStatus
from app.schemas.review import ReviewDecisionRequest, ReviewItemOut
from app.services.review_service import (
    decide_review_item,
    get_review_item,
    list_review_items,
    review_stats,
)

router = APIRouter(prefix="/review", tags=["review"])


@router.get("", response_model=list[ReviewItemOut])
def list_reviews(
    status: ReviewStatus | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[ReviewItemOut]:
    return list_review_items(db, status)


@router.get("/stats", response_model=dict[str, int])
def stats(db: Session = Depends(get_db)) -> dict[str, int]:
    return review_stats(db)


@router.get("/{review_id}", response_model=ReviewItemOut)
def get_review(review_id: int, db: Session = Depends(get_db)) -> ReviewItemOut:
    return get_review_item(db, review_id)


@router.post("/{review_id}/approve", response_model=ReviewItemOut)
def approve(
    review_id: int,
    payload: ReviewDecisionRequest,
    db: Session = Depends(get_db),
) -> ReviewItemOut:
    return decide_review_item(db, review_id, ReviewStatus.APPROVED, payload.comment)


@router.post("/{review_id}/reject", response_model=ReviewItemOut)
def reject(
    review_id: int,
    payload: ReviewDecisionRequest,
    db: Session = Depends(get_db),
) -> ReviewItemOut:
    return decide_review_item(db, review_id, ReviewStatus.REJECTED, payload.comment)