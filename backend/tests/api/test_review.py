"""API tests for the human review workflow."""

from app.core.enums import ReviewReason, ReviewStatus
from app.db.models import ReviewItem


def _seed_item(db_session, *, status=ReviewStatus.PENDING.value, comment=None):
    item = ReviewItem(
        question="Should I take a higher dose?",
        answer="Based on the documents, the most relevant passage is...",
        reason=ReviewReason.MEDICAL_ADVICE_ASKED.value,
        status=status,
        reviewer_comment=comment,
        sources=[{"document_id": 1, "filename": "notes.txt", "page_number": 1}],
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


class TestQueue:
    def test_list_empty(self, client):
        resp = client.get("/api/review")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_and_filter_by_status(self, client, db_session):
        _seed_item(db_session, status=ReviewStatus.PENDING.value)
        _seed_item(db_session, status=ReviewStatus.APPROVED.value)

        all_items = client.get("/api/review")
        assert len(all_items.json()) == 2

        pending = client.get("/api/review", params={"status": "pending"})
        assert len(pending.json()) == 1
        assert pending.json()[0]["status"] == "pending"

    def test_stats(self, client, db_session):
        _seed_item(db_session, status=ReviewStatus.PENDING.value)
        _seed_item(db_session, status=ReviewStatus.REJECTED.value)

        stats = client.get("/api/review/stats")
        assert stats.status_code == 200
        assert stats.json() == {"pending": 1, "approved": 0, "rejected": 1}

    def test_get_detail(self, client, db_session):
        item = _seed_item(db_session)

        resp = client.get(f"/api/review/{item.id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == item.id
        assert body["reason"] == "medical_advice_asked"
        assert body["status"] == "pending"
        assert body["message_id"] is None
        assert body["sources"][0]["filename"] == "notes.txt"

    def test_get_missing_returns_404(self, client):
        resp = client.get("/api/review/999999")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"


class TestDecide:
    def test_approve(self, client, db_session):
        item = _seed_item(db_session)

        resp = client.post(
            f"/api/review/{item.id}/approve", json={"comment": "Looks correct."}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "approved"
        assert body["reviewer_comment"] == "Looks correct."
        assert body["reviewed_at"] is not None

    def test_reject(self, client, db_session):
        item = _seed_item(db_session)

        resp = client.post(f"/api/review/{item.id}/reject", json={})
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    def test_decide_twice_returns_409(self, client, db_session):
        item = _seed_item(db_session, status=ReviewStatus.APPROVED.value)

        resp = client.post(f"/api/review/{item.id}/reject", json={})
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "conflict"

    def test_decide_missing_returns_404(self, client):
        resp = client.post("/api/review/999999/approve", json={})
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "not_found"