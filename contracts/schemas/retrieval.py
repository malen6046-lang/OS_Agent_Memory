from pydantic import Field

from contracts.schemas.base import ContractModel, JsonObject, NonBlankStr
from contracts.schemas.enums import MemoryKind
from contracts.schemas.memory import MemoryResponse


class SearchFilters(ContractModel):
    scene: NonBlankStr | None = None
    memory_kinds: list[MemoryKind] | None = None
    attributes: JsonObject = Field(default_factory=dict)


class SearchRequest(ContractModel):
    request_id: NonBlankStr
    user_id: NonBlankStr
    query: NonBlankStr
    filters: SearchFilters = Field(default_factory=SearchFilters)
    top_k: int = Field(default=5, strict=True, ge=1, le=100)


class SearchResult(ContractModel):
    memory: MemoryResponse
    rank: int = Field(strict=True, ge=1)
    score: float = Field(allow_inf_nan=False)


class SearchResponse(ContractModel):
    items: list[SearchResult] = Field(default_factory=list)
