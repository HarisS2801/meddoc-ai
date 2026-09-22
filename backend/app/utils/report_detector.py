"""Deterministic report-type detection from extracted document text.

When a document is processed, its type is determined from the document's
own header/title text rather than from vector retrieval or an LLM. The
uploaded document is the source of truth: "FULL BLOOD COUNT" becomes
"Full Blood Count (FBC)", never "Complete Blood Count (CBC)".

Detection only reports a type when the document clearly identifies one
(a title or header line matching a known report/panel name). No type is
invented for documents that do not name themselves.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_WHITESPACE = re.compile(r"\s+")

# Ordered (raw-line pattern, display name, abbreviation). Abbreviations
# are only added when the report name is conventionally abbreviated; a
# display like "Full Blood Count (FBC)" preserves the document's own
# terminology while surfacing the common short form.
_REPORT_PATTERNS: list[tuple[re.Pattern, str, str | None]] = [
    (re.compile(r"\bfull\s+blood\s+count\b", re.IGNORECASE), "Full Blood Count", "FBC"),
    (re.compile(r"\bcomplete\s+blood\s+count\b", re.IGNORECASE), "Complete Blood Count", "CBC"),
    (re.compile(r"\blipid\s+(?:profile|panel)\b", re.IGNORECASE), "Lipid Profile", None),
    (re.compile(r"\bcholesterol\s+(?:profile|panel)\b", re.IGNORECASE), "Cholesterol Profile", None),
    (
        re.compile(r"\b(?:liver|hepatic)\s+function\s+test\b", re.IGNORECASE),
        "Liver Function Test",
        "LFT",
    ),
    (
        re.compile(r"\b(?:kidney|renal)\s+function\s+test\b", re.IGNORECASE),
        "Kidney Function Test / Renal Function Test",
        None,
    ),
    (
        re.compile(r"\bthyroid\s+function\s+test\b", re.IGNORECASE),
        "Thyroid Function Test",
        "TFT",
    ),
    (
        re.compile(r"\bfasting\s+(?:blood\s+)?(?:sugar|glucose)\b", re.IGNORECASE),
        "Fasting Blood Glucose",
        None,
    ),
    (re.compile(r"\bblood\s+(?:glucose|sugar)\b", re.IGNORECASE), "Blood Glucose", None),
    (
        re.compile(r"\bglyc(?:ated|osylated)\s+ha?emoglobin\b", re.IGNORECASE),
        "Glycated Haemoglobin (HbA1c)",
        None,
    ),
    (
        re.compile(r"\bha?emoglobin\s+a1c\b", re.IGNORECASE),
        "Glycated Haemoglobin (HbA1c)",
        None,
    ),
    (
        re.compile(r"\blaboratory\s+results\s+report\b", re.IGNORECASE),
        "Laboratory Results Report",
        None,
    ),
    (
        re.compile(r"\bdiabetes\s+care\s+plan\b", re.IGNORECASE),
        "Diabetes Care Plan",
        None,
    ),
    (
        re.compile(r"\bhypertension\s+follow[- ]?up\b", re.IGNORECASE),
        "Hypertension Follow-up Note",
        None,
    ),
]

# Abbreviation -> full name, used to answer "What does FBC mean?" type
# questions from the document's own detected metadata.
_ABBREVIATION_MEANINGS: dict[str, str] = {
    "FBC": "Full Blood Count",
    "CBC": "Complete Blood Count",
    "LFT": "Liver Function Test",
    "TFT": "Thyroid Function Test",
    "HBA1C": "Glycated Haemoglobin",
}


@dataclass(frozen=True)
class ReportTypeMeta:
    """Detected report identity, preserved from the uploaded document."""

    report_type: str
    header: str | None = None


def _display(name: str, abbreviation: str | None) -> str:
    if not abbreviation:
        return name
    return f"{name} ({abbreviation})"


def abbreviation_meaning(abbreviation: str) -> str | None:
    """Return the full name for a known report abbreviation, if any."""
    return _ABBREVIATION_MEANINGS.get(abbreviation.strip().upper())


def detect_report_type(text: str | None) -> ReportTypeMeta | None:
    """Detect the report type from a document's header/title text.

    Returns ``None`` when no known report name is found. The returned
    ``ReportTypeMeta`` keeps the document's own spelling; the matching
    header line is preserved (truncated) so chat can cite what it saw.
    """
    if not text:
        return None
    # Collapse whitespace so PDF extraction line-breaks inside a header
    # (e.g. "FULL\nBLOOD COUNT") still match the report name.
    collapsed = _WHITESPACE.sub(" ", text)
    for pattern, name, abbreviation in _REPORT_PATTERNS:
        if pattern.search(collapsed):
            header = _extract_header_line(text, pattern)
            return ReportTypeMeta(
                report_type=_display(name, abbreviation),
                header=header,
            )
    return None


def _extract_header_line(text: str, pattern: re.Pattern) -> str | None:
    """Return the original line that matched ``pattern``, best effort."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and pattern.search(stripped):
            return stripped[:255]
    match = pattern.search(text)
    if match:
        return _WHITESPACE.sub(" ", match.group(0))[:255]
    return None