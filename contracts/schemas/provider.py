"""Embedding and vector-provider data contracts for V1.2.2."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from .common import MemoryStatus, NonEmptyString


class ProviderHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: NonEmptyString
    status: Literal["ok", "degraded", "unavailable", "stopped"]
    details: dict[str, JsonValue] = Field(default_factory=dict)


class EmbeddingModelInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: NonEmptyString
    model_name: NonEmptyString
    dimension: int = Field(gt=0)
    model_fingerprint: NonEmptyString | None = None


class EmbeddingBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vectors: list[list[float]]
    model_name: NonEmptyString
    dimension: int = Field(gt=0)

    @model_validator(mode="after")
    def verify_dimensions(self) -> "EmbeddingBatch":
        if any(len(vector) != self.dimension for vector in self.vectors):
            raise ValueError("embedding vector dimension mismatch")
        return self


class VectorStoreConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["kylin", "faiss", "memory"]
    collection_name: NonEmptyString
    expected_dimension: int = Field(gt=0)
    metric: Literal["cosine", "inner_product", "l2"] = "cosine"


class CollectionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: NonEmptyString
    dimension: int = Field(gt=0)
    metric: Literal["cosine", "inner_product", "l2"] = "cosine"


class VectorItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vector_pk: int = Field(ge=0, le=2**63 - 1)
    memory_id: NonEmptyString
    user_id: NonEmptyString
    status: MemoryStatus
    vector: list[float] = Field(min_length=1)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class UpsertResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upserted: int = Field(ge=0)


class VectorQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: NonEmptyString
    status: MemoryStatus = MemoryStatus.ACTIVE
    vector: list[float] = Field(min_length=1)
    top_k: int = Field(ge=1, le=100)
    timeout_ms: int = Field(gt=0)
    filters: dict[str, JsonValue] = Field(default_factory=dict)


class VectorHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vector_pk: int = Field(ge=0, le=2**63 - 1)
    memory_id: NonEmptyString
    user_id: NonEmptyString
    status: MemoryStatus
    score: float


class DeleteResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deleted: int = Field(ge=0)
    missing_vector_pks: list[int] = Field(default_factory=list)
