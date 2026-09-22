"""Tests for deterministic report-type detection and abbreviations."""

from app.utils.report_detector import (
    ReportTypeMeta,
    abbreviation_meaning,
    detect_report_type,
)


class TestDetectReportType:
    def test_full_blood_count(self):
        meta = detect_report_type("PATIENT NAME: A\nFULL BLOOD COUNT\nPatient: Sam")
        assert meta == ReportTypeMeta(
            report_type="Full Blood Count (FBC)", header="FULL BLOOD COUNT"
        )

    def test_full_blood_count_keeps_original_terminology(self):
        # The document says "FULL BLOOD COUNT" -- must not become CBC.
        meta = detect_report_type("FULL BLOOD COUNT\nWBC: 6.0")
        assert meta.report_type == "Full Blood Count (FBC)"

    def test_complete_blood_count(self):
        meta = detect_report_type("COMPLETE BLOOD COUNT")
        assert meta.report_type == "Complete Blood Count (CBC)"

    def test_lipid_profile(self):
        meta = detect_report_type("LIPID PROFILE\nTotal cholesterol: 5.2")
        assert meta.report_type == "Lipid Profile"
        assert meta.header == "LIPID PROFILE"

    def test_lipid_panel(self):
        meta = detect_report_type("Lipid Panel")
        assert meta.report_type == "Lipid Profile"

    def test_liver_function_test(self):
        meta = detect_report_type("LIVER FUNCTION TEST\nALT: 22")
        assert meta.report_type == "Liver Function Test (LFT)"

    def test_kidney_function_test(self):
        meta = detect_report_type("KIDNEY FUNCTION TEST\nCreatinine: 90")
        assert meta.report_type == "Kidney Function Test / Renal Function Test"

    def test_renal_function_test_synonym(self):
        meta = detect_report_type("RENAL FUNCTION TEST")
        assert meta.report_type == "Kidney Function Test / Renal Function Test"

    def test_header_split_across_pdf_lines(self):
        meta = detect_report_type("PATIENT:\nFULL\nBLOOD\nCOUNT\nWBC 6.0")
        assert meta.report_type == "Full Blood Count (FBC)"

    def test_unknown_document_returns_none(self):
        assert detect_report_type("Follow-up appointment on 15 October.") is None
        assert detect_report_type("") is None
        assert detect_report_type(None) is None
        assert detect_report_type("   ") is None

    def test_no_false_positive_on_generic_text(self):
        assert detect_report_type("The patient reported a cough and fever.") is None


class TestAbbreviationMeaning:
    def test_known_abbreviations(self):
        assert abbreviation_meaning("FBC") == "Full Blood Count"
        assert abbreviation_meaning("fbc") == "Full Blood Count"
        assert abbreviation_meaning("CBC") == "Complete Blood Count"
        assert abbreviation_meaning("LFT") == "Liver Function Test"

    def test_unknown_abbreviation(self):
        assert abbreviation_meaning("ESR") is None
        assert abbreviation_meaning("") is None