"""Hybrid retrieval request and response contracts for V1.2.2."""

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from .common import MemoryStatus, NonEmptyString


class SearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: NonEmptyString
    user_id: NonEmptyString
    query: NonEmptyString
    top_k: int = Field(default=5, ge=1, le=100)
    filters: dict[str, JsonValue] = Field(default_factory=dict)


class SearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: NonEmptyString
    user_id: NonEmptyString
    status: MemoryStatus
    content_text: str
    score: float
    attributes: dict[str, JsonValue] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: NonEmptyString
    user_id: NonEmptyString
    items: list[SearchHit] = Field(default_factory=list)
    total: int = Field(ge=0)
    provider: NonEmptyString
    degraded: bool = False
