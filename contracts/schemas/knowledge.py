from pydantic import AwareDatetime, Field, model_validator

from contracts.schemas.base import ContractModel, NonBlankStr, UnitInterval
from contracts.schemas.common import WriteContext
from contracts.schemas.enums import ItemOutcome, OperationStatus
from contracts.schemas.memory import MemoryResponse
from contracts.schemas.responses import ErrorBody


class KnowledgeCreate(ContractModel):
    title: NonBlankStr
    knowledge_type: NonBlankStr
    body: NonBlankStr
    steps: list[NonBlankStr] = Field(default_factory=list)
    keywords: list[NonBlankStr] = Field(default_factory=list)
    source_uri: NonBlankStr | None = None
    source_reliability: UnitInterval
    effective_at: AwareDatetime


KnowledgeRecord = KnowledgeCreate
KnowledgeDraft = KnowledgeCreate


class KnowledgeUpdate(ContractModel):
    title: NonBlankStr | None = None
    knowledge_type: NonBlankStr | None = None
    body: NonBlankStr | None = None
    steps: list[NonBlankStr] | None = None
    keywords: list[NonBlankStr] | None = None
    source_uri: NonBlankStr | None = None
    source_reliability: UnitInterval | None = None
    effective_at: AwareDatetime | None = None
    expected_revision: int = Field(strict=True, ge=1)

    @model_validator(mode="after")
    def at_least_one_change(self) -> "KnowledgeUpdate":
        if not (self.model_fields_set - {"expected_revision"}):
            raise ValueError("at least one updatable field is required")
        return self


class KnowledgeMemoryResponse(MemoryResponse):
    content: KnowledgeRecord


class KnowledgeIngestRequest(WriteContext):
    records: list[KnowledgeCreate] = Field(min_length=1)


class KnowledgeIngestItem(ContractModel):
    input_index: int = Field(strict=True, ge=0)
    outcome: ItemOutcome
    memory: KnowledgeMemoryResponse | None = None
    conflict_id: NonBlankStr | None = None
    error: ErrorBody | None = None


class KnowledgeIngestResult(ContractModel):
    status: OperationStatus
    items: list[KnowledgeIngestItem] = Field(default_factory=list)
