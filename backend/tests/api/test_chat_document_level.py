"""API tests for document-level chat questions (report type, abbreviation).

Document-level questions must be answered from the document's detected
metadata and must never be rejected by the RAG similarity threshold.
"""

import pytest

from app.core.config import get_settings

_FBC_REPORT = (
    "FULL BLOOD COUNT\n"
    "Patient: Test Patient\n"
    "White Blood Cell Count (WBC): 6.0 x 10^9/L\n"
    "Red Blood Cell Count (RBC): 4.8 x 10^12/L\n"
    "Haemoglobin (Hb): 142 g/L\n"
    "Platelets: 250 x 10^9/L\n"
)

_LIPID_REPORT = (
    "LIPID PROFILE\n"
    "Patient: Test Patient\n"
    "Total cholesterol: 5.2 mmol/L\n"
    "LDL Cholesterol: 3.1 mmol/L\n"
    "HDL Cholesterol: 1.4 mmol/L\n"
)

_GENERIC_NOTE = (
    "Follow-up appointments happen on the last Friday of each month. "
    "Patients should bring their referral letter and photo identification."
)


@pytest.fixture(autouse=True)
def isolated_uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(get_settings(), "upload_dir", tmp_path / "uploads")


def _upload(client, name: str, content: str):
    files = {"file": (name, content.encode("utf-8"), "text/plain")}
    resp = client.post("/api/documents/upload", files=files)
    assert resp.status_code == 201
    return resp.json()


def _upload_fbc(client):
    return _upload(client, "fbc_report.txt", _FBC_REPORT)


def _ask(client, question, document_id):
    resp = client.post(
        "/api/chat",
        json={"question": question, "document_ids": [document_id]},
    )
    assert resp.status_code == 200
    return resp.json()


class TestDocumentTypeQuery:
    def test_which_type_of_report_is_this(self, client):
        uploaded = _upload_fbc(client)
        body = _ask(client, "Which type of report is this?", uploaded["id"])

        assert body["answer"] == "This is a Full Blood Count (FBC) report."
        assert body["sources"] == []
        assert body["review_recommended"] is False
        assert body["intent"] == "document_type_query"
        assert body["provider_used"] == "metadata"

    def test_what_type_of_test_is_this(self, client):
        uploaded = _upload_fbc(client)
        body = _ask(client, "What type of test is this?", uploaded["id"])

        assert body["answer"] == "This is a Full Blood Count (FBC) test."
        assert body["intent"] == "document_type_query"

    def test_answer_comes_from_uploaded_document_not_hardcoded(self, client):
        uploaded = _upload(client, "lipid.txt", _LIPID_REPORT)
        body = _ask(client, "Which type of report is this?", uploaded["id"])

        assert body["answer"] == "This is a Lipid Profile report."

    def test_abbreviation_question_answered_from_metadata(self, client):
        uploaded = _upload_fbc(client)
        body = _ask(client, "What does FBC mean?", uploaded["id"])

        assert body["answer"] == "FBC stands for Full Blood Count."
        assert body["intent"] == "abbreviation_query"
        assert body["sources"] == []

    def test_unknown_report_type_is_not_invented(self, client):
        uploaded = _upload(client, "notes.txt", _GENERIC_NOTE)
        body = _ask(client, "Which type of report is this?", uploaded["id"])

        assert (
            body["answer"]
            == "The report type could not be determined from the uploaded document."
        )
        assert body["intent"] == "document_type_query"

    def test_report_type_exposed_on_document(self, client):
        uploaded = _upload_fbc(client)

        doc = client.get(f"/api/documents/{uploaded['id']}").json()
        assert doc["report_type"] == "Full Blood Count (FBC)"
        assert doc["report_header"] == "FULL BLOOD COUNT"


class TestRagStillWorks:
    def test_wbc_value_question_retrieves_chunks(self, client):
        uploaded = _upload_fbc(client)
        body = _ask(client, "What is my WBC?", uploaded["id"])

        assert body["intent"] == "medical_value_query"
        assert body["sources"], "expected a retrieved chunk for the WBC question"
        assert body["sources"][0]["document_id"] == uploaded["id"]
        assert "WBC" in body["sources"][0]["chunk_text"]
        assert body["review_recommended"] is False

    def test_value_not_in_document_returns_controlled_answer(self, client):
        uploaded = _upload_fbc(client)
        body = _ask(client, "What is my glucose level?", uploaded["id"])

        assert body["intent"] == "medical_value_query"
        assert body["sources"] == []
        assert "could not find information" in body["answer"]


class TestSummaryQuery:
    def test_summary_question_uses_full_document_context(self, client):
        uploaded = _upload_fbc(client)
        body = _ask(client, "Give me a summary of this report.", uploaded["id"])

        assert body["intent"] == "document_summary_query"
        assert body["sources"], "summary question must not be rejected by retrieval"
        assert "could not find information" not in body["answer"]

    def test_what_does_this_report_contain(self, client):
        uploaded = _upload_fbc(client)
        body = _ask(client, "What does this report contain?", uploaded["id"])

        assert body["intent"] == "document_summary_query"
        assert body["sources"]
        assert "could not find information" not in body["answer"]