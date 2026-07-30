from pydantic import Field

from contracts.schemas.base import ContractModel, NonBlankStr
from contracts.schemas.enums import DistanceMetric, HealthStatus, Provider


class ProviderHealth(ContractModel):
    status: HealthStatus
    provider: Provider
    message: str | None = None


class EmbeddingModelInfo(ContractModel):
    provider: Provider
    model_name: NonBlankStr
    dimension: int = Field(strict=True, gt=0)
    sdk_version: NonBlankStr


class IndexInfo(ContractModel):
    provider: Provider
    status: HealthStatus
    index_type: NonBlankStr
    metric_type: DistanceMetric
    dimension: int = Field(strict=True, gt=0)


class EmbeddingBatch(ContractModel):
    model_info: EmbeddingModelInfo
    vectors: list[list[float]]
