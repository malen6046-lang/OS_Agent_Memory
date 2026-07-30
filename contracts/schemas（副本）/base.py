from __future__ import annotations

from typing import Annotated, TypeAlias

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    JsonValue,
)

CONTRACT_VERSION = "1.0.0"


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


def _number_only(value: object) -> object:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("must be a JSON number")
    return value


def _non_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


UnitInterval: TypeAlias = Annotated[
    float, BeforeValidator(_number_only), Field(ge=0.0, le=1.0)
]
NonBlankStr: TypeAlias = Annotated[str, Field(strict=True), AfterValidator(_non_blank)]
JsonObject: TypeAlias = dict[str, JsonValue]
