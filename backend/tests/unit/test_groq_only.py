"""Migration gate: the app is 100% Groq offline, with no mock fallbacks.

These tests pin the Groq-only contract:

- Every AI endpoint surfaces a controlled ``503 groq_unavailable`` when
  Groq is not configured or fails (missing key, rate limit, timeout,
  unreadable output) - never a fabricated medical answer or preview.
- Structured summaries are sanitised so unknown labels are normalised and
  patient information is never invented.
- Successful calls persist everything to the cache; failures cache nothing,
  and a retry after a failure serves a fresh result, not stale data.
"""

import json

import pytest

from app.db.models import Message, ReviewItem, Summary
from app.services.groq_service import GroqProviderError
from tests.conftest import (
    REAL_BUILD_CHAT_COMPLETER,
    REAL_BUILD_EXTRACTOR,
    REAL_BUILD_SUMMARIZER,
)

TEXT = "The clinic opens at nine. Appointments last an hour. Parking is free."


def _upload(client, content: str = TEXT) -> int:
    files = {"file": ("notes.txt", content.encode("utf-8"), "text/plain")}
    resp = client.post("/api/documents/upload", files=files)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _ask(client, question, document_id: int, **extra):
    payload = {"question": question, "document_ids": [document_id]}
    payload.update(extra)
    return client.post("/api/chat", json=payload)


class _RaisingSummarizer:
    provider = "groq"
    model = "test-rise"

    def __init__(self, exc) -> None:
        self._exc = exc

    def summarize_segment(self, text: str) -> str:  # noqa: ARG002
        raise self._exc

    def summarize_structured(self, text: str) -> str:  # noqa: ARG002
        raise self._exc


class _CountingSummarizer:
    provider = "groq"
    model = "fake-model"

    def __init__(self, payload: str) -> None:
        self.payload = payload
        self.structured_calls = 0

    def summarize_segment(self, text: str) -> str:
        return text

    def summarize_structured(self, text: str) -> str:
        self.structured_calls += 1
        return self.payload


class _RaisingCompleter:
    provider = "groq"
    model = "test-rise"

    def __init__(self, exc) -> None:
        self._exc = exc

    def complete(self, **kwargs):  # noqa: ARG002
        raise self._exc


class _RaisingExtractor:
    def __init__(self, exc) -> None:
        self._exc = exc

    def extract(self, chunks):  # noqa: ARG002
        raise self._exc


def _error(resp):
    return resp.json()["error"]


class TestSummarizeOfflineContract:
    def test_summarize_without_key_returns_503_groq_unavailable(
        self, client, monkeypatch
    ):
        import app.services.summarization_service as ss

        monkeypatch.setattr(ss, "build_summarizer", REAL_BUILD_SUMMARIZER)
        document_id = _upload(client)

        resp = client.post(f"/api/documents/{document_id}/summarize")

        assert resp.status_code == 503
        assert _error(resp)["code"] == "groq_unavailable"

    def test_summarize_rate_limit_returns_503_groq_unavailable(
        self, client, monkeypatch
    ):
        import app.services.summarization_service as ss

        monkeypatch.setattr(
            ss,
            "build_summarizer",
            lambda: _RaisingSummarizer(GroqProviderError("rate_limit")),
        )
        document_id = _upload(client)

        resp = client.post(f"/api/documents/{document_id}/summarize")

        assert resp.status_code == 503
        assert _error(resp)["code"] == "groq_unavailable"

    def test_summarize_timeout_returns_503_groq_unavailable(
        self, client, monkeypatch
    ):
        import app.services.summarization_service as ss

        monkeypatch.setattr(
            ss,
            "build_summarizer",
            lambda: _RaisingSummarizer(GroqProviderError("timeout")),
        )
        document_id = _upload(client)

        resp = client.post(f"/api/documents/{document_id}/summarize")

        assert resp.status_code == 503
        assert _error(resp)["code"] == "groq_unavailable"

    def test_summarize_success_caches_and_is_not_recalled(self, client, monkeypatch):
        import app.services.summarization_service as ss

        summarizer = _CountingSummarizer(json.dumps({"simple_explanation": "ok"}))
        monkeypatch.setattr(ss, "build_summarizer", lambda: summarizer)
        document_id = _upload(client)

        first = client.post(f"/api/documents/{document_id}/summarize")
        second = client.post(f"/api/documents/{document_id}/summarize")

        assert first.status_code == 200
        assert second.status_code == 200
        assert summarizer.structured_calls == 1
        assert first.json()["cached"] is False
        assert second.json()["cached"] is True
        assert second.json()["provider_used"] == "groq"
        assert second.json()["model_used"] == "fake-model"
        assert second.json()["generation_status"] == "success"
        assert first.json()["structured"] == second.json()["structured"]

    def test_summarize_force_regenerates_and_overwrites(self, client, monkeypatch):
        import app.services.summarization_service as ss

        summarizer = _CountingSummarizer(json.dumps({"simple_explanation": "ok"}))
        monkeypatch.setattr(ss, "build_summarizer", lambda: summarizer)
        document_id = _upload(client)

        first = client.post(f"/api/documents/{document_id}/summarize")
        second = client.post(
            f"/api/documents/{document_id}/summarize", params={"force": "true"}
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert summarizer.structured_calls == 2
        assert second.json()["cached"] is False
        assert first.json()["structured"] == second.json()["structured"]

    def test_structured_unreadable_output_returns_503(self, client, monkeypatch):
        import app.services.summarization_service as ss

        monkeypatch.setattr(
            ss, "build_summarizer", lambda: _CountingSummarizer("totally not json")
        )
        document_id = _upload(client)

        resp = client.post(f"/api/documents/{document_id}/summarize")

        assert resp.status_code == 503
        assert _error(resp)["code"] == "groq_unavailable"

    def test_structured_payload_normalised_never_invents(self, client, monkeypatch):
        import app.services.summarization_service as ss

        payload = {
            "patient_information": {"name": "Not mentioned in the report"},
            "measurements": [{"name": "X", "value": "1", "status": "very bad"}],
            "risk_overview": [{"characteristic": "Y", "level": "extremely risky"}],
            "disease_severity": {"label": "catastrophic", "evidence": []},
            "status_card": {"abnormal_findings_count": 99},
            "simple_explanation": "ok",
        }
        monkeypatch.setattr(
            ss, "build_summarizer", lambda: _CountingSummarizer(json.dumps(payload))
        )
        document_id = _upload(client, "Some report text.")

        resp = client.post(f"/api/documents/{document_id}/summarize")

        assert resp.status_code == 200
        body = resp.json()
        structured = body["structured"]
        assert structured["measurements"][0]["status"] == "Not available"
        assert structured["risk_overview"][0]["level"] == "Not enough information"
        assert (
            structured["disease_severity"]["label"]
            == "Unable to determine from the available information"
        )
        assert (
            structured["patient_information"]["name"]
            == "Not mentioned in the report"
        )
        assert structured["status_card"]["abnormal_findings_count"] == 0


class TestChatOfflineContract:
    def test_chat_without_key_returns_503_groq_unavailable(self, client, monkeypatch):
        import app.services.chat_service as cs

        monkeypatch.setattr(cs, "build_chat_completer", REAL_BUILD_CHAT_COMPLETER)
        document_id = _upload(client)

        resp = _ask(client, "Where is the clinic?", document_id)

        assert resp.status_code == 503
        assert _error(resp)["code"] == "groq_unavailable"

    def test_chat_rate_limit_returns_503_groq_unavailable(self, client, monkeypatch):
        import app.services.chat_service as cs

        monkeypatch.setattr(
            cs,
            "build_chat_completer",
            lambda: _RaisingCompleter(GroqProviderError("rate_limit")),
        )
        document_id = _upload(client)

        resp = _ask(client, "Where is the clinic?", document_id)

        assert resp.status_code == 503
        assert _error(resp)["code"] == "groq_unavailable"

    def test_chat_timeout_returns_503_groq_unavailable(self, client, monkeypatch):
        import app.services.chat_service as cs

        monkeypatch.setattr(
            cs,
            "build_chat_completer",
            lambda: _RaisingCompleter(GroqProviderError("timeout")),
        )
        document_id = _upload(client)

        resp = _ask(client, "Where is the clinic?", document_id)

        assert resp.status_code == 503
        assert _error(resp)["code"] == "groq_unavailable"

    def test_chat_success_returns_grounded_answer_with_metadata(self, client):
        document_id = _upload(client, "The target fasting glucose is 80-130 mg/dL.")

        resp = _ask(client, "What is the target fasting glucose?", document_id)

        assert resp.status_code == 200
        body = resp.json()
        assert body["provider_used"] == "groq"
        assert body["model_used"] == "test-mock"
        assert body["generation_status"] == "success"
        assert body["answer"]
        assert body["sources"]


class TestExtractOfflineContract:
    def test_extract_without_key_uses_regex_and_invents_nothing(
        self, client, monkeypatch
    ):
        import app.services.extraction_service as es

        monkeypatch.setattr(es, "build_extractor", REAL_BUILD_EXTRACTOR)
        document_id = _upload(client, "The follow-up appointment is on 15 October.")

        resp = client.post(
            f"/api/documents/{document_id}/extract",
            json={"document_id": document_id, "schema": "follow_up"},
        )

        assert resp.status_code == 200
        result = resp.json()["result"]
        assert result["follow_up_date"] == "15 October"
        assert result["source_page"] == 1
        assert result["requires_review"] is False

    def test_extract_missing_follow_up_queues_review(self, client, db_session):
        from sqlalchemy import select

        from app.db.models import ReviewItem

        document_id = _upload(client, "No dates are mentioned in this note.")

        resp = client.post(
            f"/api/documents/{document_id}/extract",
            json={"document_id": document_id, "schema": "follow_up"},
        )

        assert resp.status_code == 200
        result = resp.json()["result"]
        assert result["follow_up_date"] is None
        assert result["requires_review"] is True
        review_item = db_session.scalars(select(ReviewItem)).first()
        assert review_item.reason == "incomplete_extraction"

    def test_extract_groq_failure_returns_503(self, client, monkeypatch):
        import app.services.extraction_service as es

        monkeypatch.setattr(
            es,
            "build_extractor",
            lambda: _RaisingExtractor(GroqProviderError("rate_limit")),
        )
        document_id = _upload(client, "The appointment is on 15 October.")

        resp = client.post(
            f"/api/documents/{document_id}/extract",
            json={"document_id": document_id, "schema": "follow_up"},
        )

        assert resp.status_code == 503
        assert _error(resp)["code"] == "groq_unavailable"


class TestFailureSafety:
    def test_retry_after_unavailable_does_not_serve_stale(
        self, client, monkeypatch
    ):
        import app.services.summarization_service as ss

        document_id = _upload(client, "Glucose 200 mg/dL (reference 70-110).")

        monkeypatch.setattr(
            ss,
            "build_summarizer",
            lambda: _RaisingSummarizer(GroqProviderError("rate_limit")),
        )
        failed = client.post(f"/api/documents/{document_id}/summarize")
        assert failed.status_code == 503

        summarizer = _CountingSummarizer(json.dumps({"simple_explanation": "fresh"}))
        monkeypatch.setattr(ss, "build_summarizer", lambda: summarizer)
        retried = client.post(f"/api/documents/{document_id}/summarize")

        assert retried.status_code == 200
        body = retried.json()
        assert body["cached"] is False
        assert body["summary"] == "fresh"
        assert summarizer.structured_calls == 1

    def test_error_envelope_carries_groq_metadata(self, client, monkeypatch):
        import app.services.summarization_service as ss

        monkeypatch.setattr(
            ss,
            "build_summarizer",
            lambda: _RaisingSummarizer(GroqProviderError("rate_limit")),
        )
        document_id = _upload(client)

        resp = client.post(f"/api/documents/{document_id}/summarize")

        body = resp.json()
        error = body["error"]
        assert error["code"] == "groq_unavailable"
        assert error["success"] is False
        assert error["provider"] == "groq"
        assert error["generation_status"] == "unavailable"
        assert error["error_code"] == "GROQ_UNAVAILABLE"
        assert error["message"]
        # The error envelope is the ONLY shape: no success keys may leak.
        assert set(body) == {"error"}
        assert "summary" not in body
        assert "structured" not in body
        assert "cached" not in body

    def test_failure_never_fabricates_or_persists_medical_content(
        self, client, db_session, monkeypatch
    ):
        from sqlalchemy import select

        import app.services.chat_service as cs
        import app.services.summarization_service as ss

        document_id = _upload(client, "Patient: Amal. Diabetes follows up in March.")

        monkeypatch.setattr(cs, "build_chat_completer", REAL_BUILD_CHAT_COMPLETER)
        chat_resp = _ask(client, "What is the patient name?", document_id)
        assert chat_resp.status_code == 503

        monkeypatch.setattr(ss, "build_summarizer", REAL_BUILD_SUMMARIZER)
        summary_resp = client.post(f"/api/documents/{document_id}/summarize")
        assert summary_resp.status_code == 503

        assert db_session.scalars(select(Message)).all() == []
        assert db_session.scalars(select(Summary)).all() == []
        assert db_session.scalars(select(ReviewItem)).all() == []
        for body in (chat_resp.json(), summary_resp.json()):
            assert "Amal" not in json.dumps(body)
            assert "Diabetes" not in json.dumps(body)