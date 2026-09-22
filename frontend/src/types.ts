export type DocumentStatus = "uploading" | "processing" | "processed" | "failed";
export type MessageRole = "user" | "assistant";
export type ReviewStatus = "pending" | "approved" | "rejected";
export type ViewId = "documents" | "summary" | "chat" | "history";

export interface DocumentItem {
  id: number;
  filename: string;
  title: string | null;
  content_type: string;
  status: DocumentStatus;
  extracted_text_len: number;
  page_count: number;
  chunk_count: number;
  error_message: string | null;
  created_at: string;
}

export interface SourceRef {
  document_id: number;
  filename: string;
  page_number: number | null;
  chunk_text: string | null;
}

export interface ChatResponse {
  conversation_id: number;
  answer: string;
  sources: SourceRef[];
  review_recommended: boolean;
  provider_used: string;
  model_used: string;
  generation_status: string;
}

export interface Conversation {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: number;
  role: MessageRole;
  content: string;
  created_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: Message[];
}

export interface PatientInformation {
  name: string;
  patient_id: string;
  age: string;
  gender: string;
  report_date: string;
  doctor_or_hospital: string;
}

export interface DocumentOverview {
  document_type: string;
  purpose: string;
}

export interface MainCondition {
  document_type: string;
  main_condition: string;
  status: string;
  symptoms_or_findings: string[];
  purpose: string;
}

export interface DiseaseSeverity {
  label: string;
  explanation: string;
  evidence: string[];
}

export interface Measurement {
  name: string;
  value: string;
  unit: string;
  reference_range: string;
  status: string;
  explanation: string;
}

export interface RiskItem {
  characteristic: string;
  level: string;
  evidence: string;
  explanation: string;
  recommendation: string;
}

export interface KeyFinding {
  finding: string;
  value: string;
  why_it_matters: string;
}

export interface KeyFindings {
  abnormal: KeyFinding[];
  normal_or_reassuring: KeyFinding[];
}

export interface Medication {
  name: string;
  dosage: string;
  frequency: string;
  duration: string;
  reason: string;
  changes: string;
  follow_up: string;
}

export interface FollowUp {
  follow_up_plan: string[];
  monitoring_plan: string[];
  precautions: string[];
}

export interface StatusCard {
  patient_name: string;
  main_condition: string;
  report_date: string;
  report_type: string;
  overall_status: string;
  disease_control: string;
  abnormal_findings_count: number;
  measurements_count: number;
  follow_up_required: string;
}

export interface StructuredSummary {
  status_card: StatusCard;
  patient_information: PatientInformation;
  document_overview: DocumentOverview;
  main_condition: MainCondition;
  disease_severity: DiseaseSeverity;
  measurements: Measurement[];
  risk_overview: RiskItem[];
  key_findings: KeyFindings;
  medications: Medication[];
  follow_up: FollowUp;
  simple_explanation: string;
  safety_notice: string;
}

export interface SummaryResponse {
  document_id: number;
  summary: string;
  source_pages: number[];
  document_type?: string;
  notice?: string | null;
  structured?: StructuredSummary | null;
  provider_used: string;
  model_used: string;
  generation_status: string;
  cached: boolean;
}

export interface ExtractionResult {
  follow_up_date: string | null;
  source_page: number | null;
  requires_review: boolean;
}

export interface ExtractionResponse {
  document_id: number;
  result: ExtractionResult;
}

export interface ReviewItem {
  id: number;
  message_id: number | null;
  question: string;
  answer: string;
  context: unknown[] | Record<string, unknown> | null;
  sources: Record<string, unknown>[] | null;
  reason: string;
  status: ReviewStatus;
  reviewer_comment: string | null;
  created_at: string;
  reviewed_at: string | null;
}

export interface ReviewStats {
  pending: number;
  approved: number;
  rejected: number;
}