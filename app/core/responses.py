from __future__ import annotations

from time import perf_counter
from typing import TypeVar

from contracts.schemas import ContractModel, Provider, ResponseMeta, SuccessResponse

T = TypeVar("T", bound=ContractModel)


def success(
    *,
    request_id: str,
    data: T,
    started_at: float,
    degraded: bool = False,
    provider: Provider | None = None,
) -> SuccessResponse[T]:
    elapsed_ms = max(0, round((perf_counter() - started_at) * 1000))
    return SuccessResponse(
        request_id=request_id,
        data=data,
        meta=ResponseMeta(
            elapsed_ms=elapsed_ms,
            degraded=degraded,
            provider=provider,
        ),
    )
