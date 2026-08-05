from pydantic import Field, model_validator

from contracts.schemas.base import ContractModel, NonBlankStr
from contracts.schemas.common import WriteContext


class PromotionRunRequest(WriteContext):
    scene: NonBlankStr | None = None


class PromotionResult(ContractModel):
    promoted_count: int = Field(strict=True, ge=0)
    promoted_ids: list[NonBlankStr] = Field(default_factory=list)
    degraded_count: int = Field(strict=True, ge=0)
    degraded_ids: list[NonBlankStr] = Field(default_factory=list)
    expired_count: int = Field(strict=True, ge=0)
    expired_ids: list[NonBlankStr] = Field(default_factory=list)

    @model_validator(mode="after")
    def counts_match_lists(self) -> "PromotionResult":
        if self.promoted_count != len(self.promoted_ids):
            raise ValueError("promoted_count must equal promoted_ids length")
        if self.degraded_count != len(self.degraded_ids):
            raise ValueError("degraded_count must equal degraded_ids length")
        if self.expired_count != len(self.expired_ids):
            raise ValueError("expired_count must equal expired_ids length")
        return self
