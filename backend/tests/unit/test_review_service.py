"""Tests for the human review workflow services."""

from app.core.enums import ReviewReason, ReviewStatus
from app.core.exceptions import ConflictError, NotFoundError
from app.db.models import ReviewItem
from app.services.review_service import (
    decide_review_item,
    get_review_item,
    list_review_items,
    review_stats,
)


def _make_item(db_session, question="Q", answer="A", status=ReviewStatus.PENDING.value):
    item = ReviewItem(
        question=question,
        answer=answer,
        reason=ReviewReason.MEDICAL_ADVICE_ASKED.value,
        status=status,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


class TestList:
    def test_empty_queue(self, db_session):
        assert list_review_items(db_session) == []

    def test_returns_all_oldest_first(self, db_session):
        first = _make_item(db_session, status=ReviewStatus.APPROVED.value)
        second = _make_item(db_session)

        items = list_review_items(db_session)
        assert [item.id for item in items] == [first.id, second.id]

    def test_filter_by_status(self, db_session):
        _make_item(db_session, status=ReviewStatus.PENDING.value)
        _make_item(db_session, status=ReviewStatus.APPROVED.value)

        pending = list_review_items(db_session, ReviewStatus.PENDING)
        assert len(pending) == 1
        assert pending[0].status == ReviewStatus.PENDING.value


class TestGet:
    def test_missing_raises_not_found(self, db_session):
        try:
            get_review_item(db_session, 999999)
            raise AssertionError("expected NotFoundError")
        except NotFoundError:
            pass


class TestDecide:
    def test_approve_updates_status_and_comment(self, db_session):
        item = _make_item(db_session)

        decided = decide_review_item(
            db_session, item.id, ReviewStatus.APPROVED, comment="Looks correct."
        )

        assert decided.status == ReviewStatus.APPROVED.value
        assert decided.reviewer_comment == "Looks correct."
        assert decided.reviewed_at is not None

    def test_reject_updates_status(self, db_session):
        item = _make_item(db_session)

        decided = decide_review_item(db_session, item.id, ReviewStatus.REJECTED)

        assert decided.status == ReviewStatus.REJECTED.value
        assert decided.reviewed_at is not None

    def test_already_decided_raises_conflict(self, db_session):
        item = _make_item(db_session, status=ReviewStatus.APPROVED.value)

        try:
            decide_review_item(db_session, item.id, ReviewStatus.REJECTED)
            raise AssertionError("expected ConflictError")
        except ConflictError:
            pass

    def test_missing_raises_not_found(self, db_session):
        try:
            decide_review_item(db_session, 999999, ReviewStatus.APPROVED)
            raise AssertionError("expected NotFoundError")
        except NotFoundError:
            pass


class TestStats:
    def test_counts_per_status(self, db_session):
        _make_item(db_session, status=ReviewStatus.PENDING.value)
        _make_item(db_session, status=ReviewStatus.PENDING.value)
        _make_item(db_session, status=ReviewStatus.APPROVED.value)

        stats = review_stats(db_session)
        assert stats == {"pending": 2, "approved": 1, "rejected": 0}

    def test_empty_queue_zero_counts(self, db_session):
        assert review_stats(db_session) == {"pending": 0, "approved": 0, "rejected": 0}