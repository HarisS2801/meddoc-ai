"""Response schemas for the structured medical report summary.

The AI provider is asked to return JSON that maps onto these models. Every
field has a safe default, so a partial or loosely-shaped answer can never
crash the request: missing values simply read "Not mentioned in the
report" instead of being invented.
"""

from pydantic import BaseModel, Field

NOT_MENTIONED = "Not mentioned in the report"

SAFETY_NOTICE = (
    "This AI-generated summary is for information and document understanding "
    "only. It is not a medical diagnosis and does not replace advice from a "
    "qualified healthcare professional. Please consult your doctor before "
    "making decisions about medication, treatment, or follow-up care."
)


class PatientInformation(BaseModel):
    name: str = NOT_MENTIONED
    patient_id: str = NOT_MENTIONED
    age: str = NOT_MENTIONED
    gender: str = NOT_MENTIONED
    report_date: str = NOT_MENTIONED
    doctor_or_hospital: str = NOT_MENTIONED


class DocumentOverview(BaseModel):
    document_type: str = "Medical Report"
    purpose: str = NOT_MENTIONED


class MainCondition(BaseModel):
    document_type: str = "Medical Report"
    main_condition: str = NOT_MENTIONED
    status: str = NOT_MENTIONED
    symptoms_or_findings: list[str] = Field(default_factory=list)
    purpose: str = NOT_MENTIONED


class DiseaseSeverity(BaseModel):
    label: str = "Unable to determine from the available information"
    explanation: str = (
        "The report does not provide enough evidence to determine the disease "
        "severity or control level."
    )
    evidence: list[str] = Field(default_factory=list)


class Measurement(BaseModel):
    name: str = ""
    value: str = NOT_MENTIONED
    unit: str = ""
    reference_range: str = NOT_MENTIONED
    status: str = "Not available"
    explanation: str = ""


class RiskItem(BaseModel):
    characteristic: str = ""
    level: str = "Not enough information"
    evidence: str = NOT_MENTIONED
    explanation: str = ""
    recommendation: str = ""


class KeyFinding(BaseModel):
    finding: str = ""
    value: str = ""
    why_it_matters: str = ""


class KeyFindings(BaseModel):
    abnormal: list[KeyFinding] = Field(default_factory=list)
    normal_or_reassuring: list[KeyFinding] = Field(default_factory=list)


class Medication(BaseModel):
    name: str = ""
    dosage: str = NOT_MENTIONED
    frequency: str = NOT_MENTIONED
    duration: str = NOT_MENTIONED
    reason: str = NOT_MENTIONED
    changes: str = NOT_MENTIONED
    follow_up: str = NOT_MENTIONED


class FollowUp(BaseModel):
    follow_up_plan: list[str] = Field(default_factory=list)
    monitoring_plan: list[str] = Field(default_factory=list)
    precautions: list[str] = Field(default_factory=list)


class StatusCard(BaseModel):
    patient_name: str = NOT_MENTIONED
    main_condition: str = NOT_MENTIONED
    report_date: str = NOT_MENTIONED
    report_type: str = "Medical Report"
    overall_status: str = "Unable to determine from the report"
    disease_control: str = "Not mentioned in the report"
    abnormal_findings_count: int = 0
    measurements_count: int = 0
    follow_up_required: str = "Not mentioned"


class StructuredSummary(BaseModel):
    """Full patient-friendly breakdown of one uploaded report."""

    status_card: StatusCard = Field(default_factory=StatusCard)
    patient_information: PatientInformation = Field(default_factory=PatientInformation)
    document_overview: DocumentOverview = Field(default_factory=DocumentOverview)
    main_condition: MainCondition = Field(default_factory=MainCondition)
    disease_severity: DiseaseSeverity = Field(default_factory=DiseaseSeverity)
    measurements: list[Measurement] = Field(default_factory=list)
    risk_overview: list[RiskItem] = Field(default_factory=list)
    key_findings: KeyFindings = Field(default_factory=KeyFindings)
    medications: list[Medication] = Field(default_factory=list)
    follow_up: FollowUp = Field(default_factory=FollowUp)
    simple_explanation: str = ""
    safety_notice: str = SAFETY_NOTICE


class SummaryResponse(BaseModel):
    document_id: int
    summary: str
    source_pages: list[int]
    document_type: str = "Medical Report"
    notice: str | None = None
    structured: StructuredSummary | None = None
    provider_used: str = "groq"
    model_used: str = ""
    generation_status: str = "success"
    cached: bool = False
