from pydantic import Field

from contracts.schemas.base import ContractModel, NonBlankStr
from contracts.schemas.common import EventBatch
from contracts.schemas.enums import ItemOutcome, OperationStatus
from contracts.schemas.responses import ErrorBody


class EventIngestRequest(EventBatch):
    pass


class EventIngestItem(ContractModel):
    source_event_id: NonBlankStr
    outcome: ItemOutcome
    memory_ids: list[NonBlankStr] = Field(default_factory=list)
    conflict_id: NonBlankStr | None = None
    error: ErrorBody | None = None


class EventIngestResult(ContractModel):
    status: OperationStatus
    task_id: NonBlankStr | None = None
    items: list[EventIngestItem] = Field(default_factory=list)
