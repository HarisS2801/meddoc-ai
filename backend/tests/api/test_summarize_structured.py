"""API tests for the structured summary returned by the summarize endpoint.

They cover: a real provider returning valid JSON, invalid JSON, provider
failure, mock mode, and corrupted extracted text. No network is used.
"""

import json

from app.schemas.summarization import SAFETY_NOTICE
from app.services.groq_service import GroqProviderError

PROVIDER_PAYLOAD = {
    "patient_information": {"name": "Not mentioned in the report", "age": "Not mentioned in the report"},
    "document_overview": {"document_type": "Laboratory / Blood Test Report"},
    "main_condition": {
        "document_type": "Laboratory / Blood Test Report",
        "main_condition": "Type 2 Diabetes",
        "status": "Existing condition under follow-up",
    },
    "disease_severity": {
        "label": "Partially controlled",
        "explanation": "Glucose is above the stated range.",
        "evidence": ["Fasting glucose 140 mg/dL (70-110)"],
    },
    "measurements": [
        {
            "name": "Fasting glucose",
            "value": "140",
            "unit": "mg/dL",
            "reference_range": "70-110",
            "status": "High",
            "explanation": "Above the laboratory range.",
        }
    ],
    "key_findings": {"abnormal": [], "normal_or_reassuring": []},
    "medications": [],
    "follow_up": {"follow_up_plan": ["Repeat blood test in 3 months"]},
    "simple_explanation": "Your blood sugar is above the range in this report.",
}


class _FakeSummarizer:
    provider = "groq"
    model = "fake-model"

    def __init__(self, payload: str):
        self.payload = payload
        self.structured_inputs: list[str] = []

    def summarize_segment(self, text: str) -> str:
        return f"segment: {text}"

    def summarize_structured(self, text: str) -> str:
        self.structured_inputs.append(text)
        return self.payload


class _RaisingSummarizer(_FakeSummarizer):
    def summarize_structured(self, text: str) -> str:  # noqa: ARG002
        raise GroqProviderError("rate_limit")


class _CountingFakeSummarizer(_FakeSummarizer):
    def __init__(self, payload: str):
        super().__init__(payload)
        self.structured_calls = 0

    def summarize_structured(self, text: str) -> str:
        self.structured_calls += 1
        self.structured_inputs.append(text)
        return self.payload


def _upload_doc(client, content: str, name: str = "report.txt") -> int:
    files = {"file": (name, content.encode("utf-8"), "text/plain")}
    resp = client.post("/api/documents/upload", files=files)
    assert resp.status_code == 201
    return resp.json()["id"]


class TestStructuredSummaryApi:
    def test_valid_provider_json_is_returned(self, client, monkeypatch):
        summarizer = _FakeSummarizer(json.dumps(PROVIDER_PAYLOAD))
        monkeypatch.setattr(
            "app.services.summarization_service.build_summarizer",
            lambda: summarizer,
        )
        document_id = _upload_doc(
            client, "Fasting glucose 140 mg/dL (reference range 70-110)."
        )

        resp = client.post(f"/api/documents/{document_id}/summarize")

        assert resp.status_code == 200
        body = resp.json()
        assert body["notice"] is None
        assert body["summary"]
        assert body["provider_used"] == "groq"
        assert body["model_used"] == "fake-model"
        assert body["generation_status"] == "success"
        assert body["structured"]["main_condition"]["main_condition"] == "Type 2 Diabetes"
        measurement = body["structured"]["measurements"][0]
        assert measurement["value"] == "140"
        assert measurement["unit"] == "mg/dL"
        assert measurement["status"] == "High"
        assert body["structured"]["safety_notice"] == SAFETY_NOTICE

    def test_patient_information_is_never_invented(self, client, monkeypatch):
        summarizer = _FakeSummarizer(json.dumps(PROVIDER_PAYLOAD))
        monkeypatch.setattr(
            "app.services.summarization_service.build_summarizer",
            lambda: summarizer,
        )
        document_id = _upload_doc(client, "Repeat blood test in 3 months.")

        body = client.post(f"/api/documents/{document_id}/summarize").json()

        info = body["structured"]["patient_information"]
        assert info["name"] == "Not mentioned in the report"
        assert body["structured"]["status_card"]["patient_name"] == (
            "Not mentioned in the report"
        )

    def test_invalid_json_returns_503(self, client, monkeypatch):
        summarizer = _FakeSummarizer("totally not json")
        monkeypatch.setattr(
            "app.services.summarization_service.build_summarizer",
            lambda: summarizer,
        )
        document_id = _upload_doc(client, "Some report text for the preview.")

        resp = client.post(f"/api/documents/{document_id}/summarize")

        assert resp.status_code == 503
        error = resp.json()["error"]
        assert error["code"] == "groq_unavailable"
        assert error["provider"] == "groq"
        assert "preview" not in json.dumps(error)

    def test_provider_failure_returns_503(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.services.summarization_service.build_summarizer",
            lambda: _RaisingSummarizer("{}"),
        )
        document_id = _upload_doc(client, "The clinic opens at nine.")

        resp = client.post(f"/api/documents/{document_id}/summarize")

        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == "groq_unavailable"

    def test_mock_mode_returns_structured_without_invention(self, client):
        document_id = _upload_doc(
            client, "Clinic letter. The patient attended a routine review."
        )

        resp = client.post(f"/api/documents/{document_id}/summarize")

        assert resp.status_code == 200
        body = resp.json()
        assert body["structured"] is not None
        assert body["structured"]["measurements"] == []
        assert body["structured"]["medications"] == []
        assert body["structured"]["simple_explanation"]
        assert body["structured"]["safety_notice"] == SAFETY_NOTICE

    def test_corrupted_text_does_not_crash(self, client):
        corrupt = "###\x00\x01\x02 ??? \u2603\uffff\n\nrandom \u2028 bytes"
        document_id = _upload_doc(client, corrupt)

        resp = client.post(f"/api/documents/{document_id}/summarize")

        assert resp.status_code == 200
        body = resp.json()
        assert body["structured"] is not None
        assert "Not mentioned in the report" in json.dumps(body["structured"])

    def test_long_document_uses_all_segments(self, client, monkeypatch):
        summarizer = _FakeSummarizer(json.dumps(PROVIDER_PAYLOAD))
        monkeypatch.setattr(
            "app.services.summarization_service.build_summarizer",
            lambda: summarizer,
        )
        monkeypatch.setattr(
            "app.services.summarization_service._MAX_INPUT_CHARS", 200
        )
        long_text = "Start marker. " + " ".join(
            f"Sentence number {i}." for i in range(60)
        ) + " End marker."
        document_id = _upload_doc(client, long_text)

        resp = client.post(f"/api/documents/{document_id}/summarize")

        assert resp.status_code == 200
        assert resp.json()["structured"] is not None
        sent = summarizer.structured_inputs[0]
        assert "Start marker." in sent
        assert "End marker." in sent

    def test_summarize_is_cached_across_requests(self, client, monkeypatch):
        summarizer = _CountingFakeSummarizer(json.dumps(PROVIDER_PAYLOAD))
        monkeypatch.setattr(
            "app.services.summarization_service.build_summarizer",
            lambda: summarizer,
        )
        document_id = _upload_doc(
            client, "Fasting glucose 140 mg/dL (reference range 70-110)."
        )

        first = client.post(f"/api/documents/{document_id}/summarize")
        second = client.post(f"/api/documents/{document_id}/summarize")

        assert first.status_code == 200
        assert first.json()["cached"] is False
        assert second.json()["cached"] is True
        assert first.json()["summary"] == second.json()["summary"]
        assert first.json()["structured"] == second.json()["structured"]
        assert summarizer.structured_calls == 1