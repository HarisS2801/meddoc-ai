from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import ExtractionSchemaType


class ExtractionRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    document_id: int
    extraction_type: ExtractionSchemaType = Field(
        validation_alias="schema",
        serialization_alias="schema",
    )


class ExtractionResult(BaseModel):
    follow_up_date: str | None = None
    source_page: int | None = None
    requires_review: bool = True


class ExtractionResponse(BaseModel):
    document_id: int
    result: ExtractionResult