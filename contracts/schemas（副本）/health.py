from contracts.schemas.base import CONTRACT_VERSION, ContractModel, NonBlankStr
from contracts.schemas.enums import HealthStatus
from contracts.schemas.provider import EmbeddingModelInfo, IndexInfo, ProviderHealth


class HealthQuery(ContractModel):
    request_id: NonBlankStr | None = None


class HealthResponse(ContractModel):
    status: HealthStatus
    service_version: NonBlankStr
    contract_version: str = CONTRACT_VERSION
    components: dict[str, ProviderHealth]
    model_info: EmbeddingModelInfo | None = None
    index_info: IndexInfo | None = None
