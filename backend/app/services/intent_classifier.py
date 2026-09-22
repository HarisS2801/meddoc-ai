"""Deterministic question-intent classification for the RAG chat.

The router decides, without calling an LLM, whether a question is about
the *document itself* (metadata-answerable) or about *content* (RAG).
Classifying deterministically means the routing never invents a label and
never depends on model availability or cost.

   DOCUMENT_TYPE_QUERY      -> answered from stored document metadata
   ABBREVIATION_QUERY       -> answered from metadata when the short form
                               matches the document's report type
   DOCUMENT_SUMMARY_QUERY   -> answered from document content (RAG + LLM)
   MEDICAL_VALUE_QUERY      -> specific value inside the document (RAG)
   GENERAL_REPORT_QUERY     -> anything else (RAG)
"""

from __future__ import annotations

import re


class QuestionIntent(str):
    """Stable intent labels for chat routing and telemetry."""

    DOCUMENT_TYPE_QUERY = "document_type_query"
    ABBREVIATION_QUERY = "abbreviation_query"
    DOCUMENT_SUMMARY_QUERY = "document_summary_query"
    MEDICAL_VALUE_QUERY = "medical_value_query"
    GENERAL_REPORT_QUERY = "general_report_query"


# "Which type of report is this?" -> the document itself is the subject.
_TYPE_QUERY_PATTERNS = (
    re.compile(
        r"\b(?:wh[ea]t|which)\s+(?:kind|type|sort|category)\s+of\s+"
        r"(?:report|test|document|examination|exam|letter|file)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bwh[ea]t\s+(?:medical|blood|lab(?:oratory)?|diagnostic|serum)?\s*"
        r"(?:test|examination|exam)\s+(?:is|was)\s+this\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bwh[ea]t\s+(?:kind|type)\s+of\s+(?:medical\s+)?"
        r"(?:report|document)\s+is\s+this\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bidentify\s+the\s+(?:report|document)\s+type\b", re.IGNORECASE),
    re.compile(r"\bwh[ea]t\s+test\s+is\s+this\b", re.IGNORECASE),
    re.compile(
        r"\b(?:wh[ea]t|which)\s+(?:test|examination|exam)\s+was\s+"
        r"(?:performed|done|run|carried\s+out)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bwhich\s+report\s+is\s+this\b", re.IGNORECASE),
)

# "Summarize this report", "What does this report contain?" -> the whole
# document is in scope so retrieval uses the full document context.
_SUMMARY_QUERY_PATTERNS = (
    re.compile(r"\bsummari[sz](?:e|ed|es|ing)\b", re.IGNORECASE),
    re.compile(r"\bsummary\b", re.IGNORECASE),
    re.compile(r"\boverview\b", re.IGNORECASE),
    re.compile(r"\b(?:give|write|provide)\s+(?:me\s+)?a?\s*(?:brief|short)?\s*(?:report\s+|document\s+)?(?:summary|synopsis|recap)\b", re.IGNORECASE),
    re.compile(r"\bwh[ea]t\s+does\s+(?:this|the)\s+(?:report|document)\s+contain\b", re.IGNORECASE),
    re.compile(r"\bwh[ea]t\s+is\s+(?:this|the)\s+(?:report|document)\s+about\b", re.IGNORECASE),
    re.compile(r"\bcontents?\s+of\s+(?:this|the)\s+(?:report|document)\b", re.IGNORECASE),
)

# "What does FBC mean / stand for?" -> metadata answerable when the short
# form matches the uploaded document's detected report type.
_ABBREVIATION_PATTERNS = (
    re.compile(
        r"\bwh[ea]t\s+does\s+(?:the\s+)?(?:abbreviation\s+|term\s+)?([A-Za-z]{2,8})\s+"
        r"(?:stand\s+for|mean)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bwh[ea]t\s+(?:is|are)\s+([A-Za-z]{2,8})\s+(?:short\s+for|the\s+abbreviation\s+for)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bwh[ea]t\s+(?:is|does)\s+(?:the\s+)?(?:full\s+form|meaning|expansion)\s+of\s+([A-Za-z]{2,8})\b",
        re.IGNORECASE,
    ),
)

# Biomarker / test names that make a question about a specific value
# inside the document rather than the document as a whole.
_MEDICAL_VALUE_TERMS = (
    r"\bwbc\b", r"\brbc\b", r"\bplt\b", r"\bplatelet", r"\bhaemoglobin\b",
    r"\bhemoglobin\b", r"\bglucose\b", r"\bsugar\b", r"\bhba1c\b", r"\ba1c\b",
    r"\bcholesterol\b", r"\bldl\b", r"\bhdl\b", r"\btriglyceride", r"\blipid",
    r"\bcreatinine\b", r"\begfr\b", r"\bgfr\b", r"\burea\b", r"\bpotassium\b",
    r"\bsodium\b", r"\balt\b", r"\bast\b", r"\bsgpt\b", r"\bsgot\b",
    r"\bbilirubin\b", r"\bblood\s+pressure\b", r"\bheart\s+rate\b",
    r"\bvitamin\b", r"\btsh\b", r"\bt4\b", r"\bt3\b", r"\bcortisol\b",
    r"\bcrp\b", r"\besr\b", r"\bferritin\b",
)
_MEDICAL_VALUE_RE = re.compile("|".join(_MEDICAL_VALUE_TERMS), re.IGNORECASE)

_VALUE_SCOPE_RE = re.compile(
    r"\b(?:wh[ea]t|how\s+much|how\s+many|level|value|reading|result|concentration|count)\b",
    re.IGNORECASE,
)

_WHITESPACE = re.compile(r"\s+")


def classify_intent(question: str) -> str:
    """Classify a chat question into one of the stable intent labels.

    Deterministic, ordered, first-match-wins. Prefers document-level
    intents (type / abbreviation / summary) before generic fallbacks.
    """
    lowered = _WHITESPACE.sub(" ", question.strip().lower())
    if any(pattern.search(lowered) for pattern in _TYPE_QUERY_PATTERNS):
        return QuestionIntent.DOCUMENT_TYPE_QUERY
    if any(pattern.search(lowered) for pattern in _ABBREVIATION_PATTERNS):
        return QuestionIntent.ABBREVIATION_QUERY
    if any(pattern.search(lowered) for pattern in _SUMMARY_QUERY_PATTERNS):
        return QuestionIntent.DOCUMENT_SUMMARY_QUERY
    if _MEDICAL_VALUE_RE.search(lowered) and _VALUE_SCOPE_RE.search(lowered):
        return QuestionIntent.MEDICAL_VALUE_QUERY
    return QuestionIntent.GENERAL_REPORT_QUERY


def extract_abbreviation(question: str) -> str | None:
    """Return the abbreviated term a question is asking about, if any."""
    lowered = _WHITESPACE.sub(" ", question.strip().lower())
    for pattern in _ABBREVIATION_PATTERNS:
        match = pattern.search(lowered)
        if match:
            return match.group(1)
    return None