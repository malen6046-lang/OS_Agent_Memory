from contracts.schemas.base import ContractModel, NonBlankStr, UnitInterval
from contracts.schemas.common import WriteContext
from contracts.schemas.enums import ConflictRelation, ConflictStrategy
from contracts.schemas.memory import MemoryResponse


class ConflictDecision(ContractModel):
    relation: ConflictRelation
    old_memory_id: NonBlankStr
    new_memory_id: NonBlankStr
    confidence: UnitInterval
    strategy: ConflictStrategy
    reason_codes: list[NonBlankStr]


class ConflictResolveRequest(WriteContext):
    decision: ConflictDecision


class ConflictResult(ContractModel):
    conflict_id: NonBlankStr
    decision: ConflictDecision
    memory: MemoryResponse | None = None
