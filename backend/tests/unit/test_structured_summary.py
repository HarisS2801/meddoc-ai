"""Tests for the structured medical summary parsing and safety rules.

These exercise the parser, the sanitiser, and the offline mock without any
network access. They cover the required scenarios: diabetes reports,
cholesterol/blood pressure, missing patient information, no measurements,
multiple conditions, medications and follow-up, invalid JSON, and using the
complete document for long inputs.
"""

import json

from app.schemas.summarization import SAFETY_NOTICE, StructuredSummary
from app.services.summarization_service import (
    _parse_structured,
    _structured_input,
    summarize_document_bundle,
)

DIABETES = {
    "patient_information": {
        "name": "Jane Doe",
        "patient_id": "H-1024",
        "age": "58",
        "gender": "Female",
        "report_date": "2026-03-04",
        "doctor_or_hospital": "City Clinic",
    },
    "document_overview": {
        "document_type": "Diabetes Report",
        "purpose": "Routine follow-up for type 2 diabetes",
    },
    "main_condition": {
        "document_type": "Diabetes Report",
        "main_condition": "Type 2 Diabetes",
        "status": "Existing condition under follow-up",
        "symptoms_or_findings": ["increased thirst"],
        "purpose": "Monitoring blood glucose control",
    },
    "disease_severity": {
        "label": "Poorly controlled",
        "explanation": "HbA1c is above the target stated in the report.",
        "evidence": ["HbA1c 8.2% (target < 7.0%)"],
    },
    "measurements": [
        {
            "name": "Fasting blood glucose",
            "value": "162",
            "unit": "mg/dL",
            "reference_range": "70-110",
            "status": "High",
            "explanation": "Above the laboratory range.",
        },
        {
            "name": "HbA1c",
            "value": "8.2",
            "unit": "%",
            "reference_range": "< 7.0",
            "status": "High",
            "explanation": "Above the target stated in the report.",
        },
    ],
    "risk_overview": [
        {
            "characteristic": "Blood sugar",
            "level": "High concern",
            "evidence": "Fasting glucose 162 mg/dL (70-110)",
            "explanation": "This may indicate blood sugar is not well controlled.",
            "recommendation": "Discuss with a qualified healthcare professional.",
        }
    ],
    "key_findings": {
        "abnormal": [
            {
                "finding": "High HbA1c",
                "value": "8.2%",
                "why_it_matters": "Average blood sugar over recent months is high.",
            }
        ],
        "normal_or_reassuring": [
            {"finding": "Kidney function", "value": "Normal", "why_it_matters": "No kidney concern reported."}
        ],
    },
    "medications": [
        {
            "name": "Metformin",
            "dosage": "500 mg",
            "frequency": "twice daily",
            "duration": "ongoing",
            "reason": "blood sugar control",
            "changes": "No change",
            "follow_up": "Review in 3 months",
        }
    ],
    "follow_up": {
        "follow_up_plan": ["Review in 3 months"],
        "monitoring_plan": ["Check HbA1c"],
        "precautions": ["Seek care for very high blood sugar"],
    },
    "simple_explanation": "Your diabetes control needs attention.",
}


class TestParseStructured:
    def test_full_diabetes_report(self):
        result = _parse_structured(json.dumps(DIABETES))

        assert isinstance(result, StructuredSummary)
        assert result.patient_information.name == "Jane Doe"
        assert result.main_condition.main_condition == "Type 2 Diabetes"
        assert result.disease_severity.label == "Poorly controlled"

    def test_measurements_keep_value_unit_and_reference(self):
        result = _parse_structured(json.dumps(DIABETES))

        glucose = result.measurements[0]
        assert glucose.name == "Fasting blood glucose"
        assert glucose.value == "162"
        assert glucose.unit == "mg/dL"
        assert glucose.reference_range == "70-110"
        assert glucose.status == "High"

    def test_status_card_counts_are_recomputed(self):
        result = _parse_structured(json.dumps(DIABETES))

        card = result.status_card
        assert card.measurements_count == 2
        assert card.abnormal_findings_count == 3  # 2 high + 1 abnormal finding
        assert card.follow_up_required == "Yes"
        assert card.patient_name == "Jane Doe"

    def test_safety_notice_is_always_forced(self):
        payload = dict(DIABETES)
        payload["safety_notice"] = "ignored"
        result = _parse_structured(json.dumps(payload))
        assert result.safety_notice == SAFETY_NOTICE

    def test_missing_patient_information_is_not_invented(self):
        payload = {"main_condition": {"main_condition": "Hypertension"}}
        result = _parse_structured(json.dumps(payload))

        info = result.patient_information
        assert info.name == "Not mentioned in the report"
        assert info.age == "Not mentioned in the report"
        assert info.report_date == "Not mentioned in the report"
        assert result.status_card.patient_name == "Not mentioned in the report"

    def test_no_measurements_is_safe(self):
        payload = {"simple_explanation": "No lab values in this letter."}
        result = _parse_structured(json.dumps(payload))

        assert result.measurements == []
        assert result.status_card.measurements_count == 0
        assert result.status_card.abnormal_findings_count == 0

    def test_multiple_conditions_are_preserved(self):
        payload = {
            "main_condition": {"main_condition": "Type 2 Diabetes and Hypertension"},
            "risk_overview": [
                {"characteristic": "Blood sugar", "level": "High concern"},
                {"characteristic": "Blood pressure", "level": "Moderate concern"},
            ],
        }
        result = _parse_structured(json.dumps(payload))

        assert "Hypertension" in result.main_condition.main_condition
        assert len(result.risk_overview) == 2
        assert result.risk_overview[1].level == "Moderate concern"

    def test_medications_and_follow_up_are_preserved(self):
        result = _parse_structured(json.dumps(DIABETES))

        assert result.medications[0].name == "Metformin"
        assert result.medications[0].frequency == "twice daily"
        assert result.follow_up.follow_up_plan == ["Review in 3 months"]
        assert result.follow_up.monitoring_plan == ["Check HbA1c"]


class TestParseStructuredResilience:
    def test_invalid_json_returns_none(self):
        assert _parse_structured("this is not json") is None
        assert _parse_structured("") is None
        assert _parse_structured("{not valid json}") is None

    def test_non_object_json_returns_none(self):
        assert _parse_structured('["a", "b"]') is None
        assert _parse_structured("null") is None

    def test_wrong_types_return_none(self):
        assert _parse_structured('{"measurements": "oops"}') is None

    def test_fenced_json_is_parsed(self):
        raw = "```json\n" + json.dumps({"simple_explanation": "ok"}) + "\n```"
        result = _parse_structured(raw)
        assert result is not None
        assert result.simple_explanation == "ok"

    def test_json_with_surrounding_prose_is_parsed(self):
        raw = "Here is the summary:\n" + json.dumps(DIABETES) + "\nThanks."
        result = _parse_structured(raw)
        assert result is not None
        assert result.main_condition.main_condition == "Type 2 Diabetes"

    def test_empty_rows_are_dropped(self):
        payload = {
            "measurements": [
                {"name": "", "value": "10"},
                {"name": "Creatinine", "value": "1.1", "unit": "mg/dL"},
            ],
            "risk_overview": [{"characteristic": ""}],
            "medications": [{"name": ""}, {"name": "Aspirin"}],
            "key_findings": {"abnormal": [{"finding": ""}], "normal_or_reassuring": []},
        }
        result = _parse_structured(json.dumps(payload))

        assert [m.name for m in result.measurements] == ["Creatinine"]
        assert result.risk_overview == []
        assert [m.name for m in result.medications] == ["Aspirin"]
        assert result.key_findings.abnormal == []

    def test_unknown_labels_are_normalised(self):
        payload = {
            "measurements": [{"name": "X", "value": "1", "status": "very bad"}],
            "risk_overview": [{"characteristic": "Y", "level": "extremely risky"}],
            "disease_severity": {"label": "catastrophic", "evidence": ["x"]},
        }
        result = _parse_structured(json.dumps(payload))

        assert result.measurements[0].status == "Not available"
        assert result.risk_overview[0].level == "Not enough information"
        assert (
            result.disease_severity.label
            == "Unable to determine from the available information"
        )

    def test_severity_without_evidence_is_downgraded(self):
        payload = {"disease_severity": {"label": "Severe", "evidence": []}}
        result = _parse_structured(json.dumps(payload))
        assert (
            result.disease_severity.label
            == "Unable to determine from the available information"
        )

    def test_model_count_claim_is_ignored(self):
        payload = {
            "measurements": [{"name": "X", "value": "1", "status": "High"}],
            "status_card": {"abnormal_findings_count": 99, "measurements_count": 99},
        }
        result = _parse_structured(json.dumps(payload))
        assert result.status_card.abnormal_findings_count == 1
        assert result.status_card.measurements_count == 1


class _RecordingSummarizer:
    provider = "groq"
    model = "fake-model"

    def __init__(self, payload: str):
        self.payload = payload
        self.segment_inputs: list[str] = []
        self.structured_inputs: list[str] = []

    def summarize_segment(self, text: str) -> str:
        self.segment_inputs.append(text)
        return f"summary of segment {len(self.segment_inputs)}"

    def summarize_structured(self, text: str) -> str:
        self.structured_inputs.append(text)
        return self.payload


class TestCompleteDocumentIsUsed:
    def test_long_document_is_condensed_from_every_segment(self, monkeypatch):
        text = " ".join(f"Finding number {i}." for i in range(80))
        summarizer = _RecordingSummarizer(json.dumps({"simple_explanation": "ok"}))
        monkeypatch.setattr(
            "app.services.summarization_service._MAX_INPUT_CHARS", 200
        )

        condensed = _structured_input(summarizer, text)

        assert len(summarizer.segment_inputs) >= 2
        # every segment summary is represented in the structured input
        for index in range(1, len(summarizer.segment_inputs) + 1):
            assert f"summary of segment {index}" in condensed

    def test_bundle_uses_full_document_for_structured_call(self, db_session, monkeypatch):
        from app.core.enums import DocumentStatus
        from app.db.models import Document, DocumentChunk

        full_text = "First finding about glucose. Last finding about kidney."
        document = Document(
            filename="report.txt",
            title="Report",
            content_type="text/plain",
            storage_path="/tmp/report.txt",
            status=DocumentStatus.PROCESSED.value,
            extracted_text_len=len(full_text),
            page_count=1,
            chunk_count=1,
        )
        document.chunks = [
            DocumentChunk(chunk_index=0, content=full_text, page_number=1)
        ]
        db_session.add(document)
        db_session.commit()
        db_session.refresh(document)

        summarizer = _RecordingSummarizer(json.dumps(DIABETES))
        monkeypatch.setattr(
            "app.services.summarization_service.build_summarizer",
            lambda: summarizer,
        )

        bundle = summarize_document_bundle(db_session, document.id)

        assert bundle.structured is not None
        assert "glucose" in summarizer.structured_inputs[0]
        assert "kidney" in summarizer.structured_inputs[0]
        assert bundle.notice is None
