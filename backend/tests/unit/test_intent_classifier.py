"""Tests for the deterministic chat question-intent classifier."""

from app.services.intent_classifier import (
    QuestionIntent,
    classify_intent,
    extract_abbreviation,
)


class TestDocumentTypeQuery:
    def test_type_questions(self):
        for question in (
            "Which type of report is this?",
            "What type of report is this?",
            "What kind of report is this?",
            "Which type of report is this",
            "What type of test is this?",
            "What kind of test is this?",
            "What medical test is this?",
            "What blood test is this?",
            "What test is this?",
            "What examination was performed?",
            "What exam was done?",
            "Which test was performed?",
            "Identify the report type.",
        ):
            assert classify_intent(question) == QuestionIntent.DOCUMENT_TYPE_QUERY, question


class TestAbbreviationQuery:
    def test_abbreviation_questions(self):
        for question in (
            "What does FBC mean?",
            "What does FBC stand for?",
            "What does the abbreviation FBC stand for?",
            "What is CBC short for?",
            "What is the full form of LFT?",
        ):
            assert classify_intent(question) == QuestionIntent.ABBREVIATION_QUERY, question

    def test_extract_abbreviation(self):
        assert extract_abbreviation("What does FBC mean?") == "fbc"
        assert extract_abbreviation("What does the abbreviation CBC stand for?") == "cbc"
        assert extract_abbreviation("What is LFT short for?") == "lft"
        assert extract_abbreviation("Which type of report is this?") is None


class TestSummaryQuery:
    def test_summary_questions(self):
        for question in (
            "Give me a summary of this report.",
            "Summarize this report.",
            "Can you summarise the document?",
            "What does this report contain?",
            "What is this report about?",
            "Overview of this report.",
        ):
            assert classify_intent(question) == QuestionIntent.DOCUMENT_SUMMARY_QUERY, question


class TestMedicalValueQuery:
    def test_value_questions(self):
        for question in (
            "What is my WBC?",
            "What is my haemoglobin?",
            "What is my glucose level?",
            "What was my platelet count?",
            "How much is my LDL cholesterol?",
        ):
            assert classify_intent(question) == QuestionIntent.MEDICAL_VALUE_QUERY, question


class TestGeneralQuery:
    def test_generic_fallback(self):
        for question in (
            "What is the weather forecast tomorrow?",
            "Where is the clinic?",
            "Should I take a higher dose?",
        ):
            assert classify_intent(question) == QuestionIntent.GENERAL_REPORT_QUERY, question