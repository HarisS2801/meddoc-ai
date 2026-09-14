"""Shared enum values used by both the database models and the API schemas."""

import enum


class DocumentStatus(enum.StrEnum):
    UPLOADING = "uploading"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"


class MessageRole(enum.StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ReviewStatus(enum.StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ReviewReason(enum.StrEnum):
    LOW_CONFIDENCE = "low_confidence"
    UNSUPPORTED_ANSWER = "unsupported_answer"
    MEDICAL_ADVICE_ASKED = "medical_advice_asked"
    INCOMPLETE_EXTRACTION = "incomplete_extraction"
    PROCESSING_ERROR = "processing_error"


class ExtractionSchemaType(enum.StrEnum):
    FOLLOW_UP = "follow_up"