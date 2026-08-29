"""V1.2.2 VectorStoreAdapter backed by the local Kylin C++ Sidecar."""

from __future__ import annotations

from typing import Any

from adapters.embedding.kylin_sidecar_client import KylinSidecarClient
from contracts.schemas.provider import (
    CollectionSpec,
    DeleteResult,
    ProviderHealth,
    UpsertResult,
    VectorHit,
    VectorItem,
    VectorQuery,
    VectorStoreConfig,
)


class KylinVectorStoreAdapter:
    def __init__(
        self,
        config: Any = None,
        app_config: Any = None,
        client: KylinSidecarClient | None = None,
    ) -> None:
        del config, app_config
        self._client = client or KylinSidecarClient()
        self._started = False
        self._config: VectorStoreConfig | None = None

    def start(self, config: VectorStoreConfig) -> ProviderHealth:
        data = self._client.vector_start(config.model_dump(mode="json"))
        if data.get("status") != "ready":
            raise RuntimeError(
                f"Kylin vector store is not ready: {data.get('status')!r}"
            )
        if data.get("collection_name") != config.collection_name:
            raise RuntimeError("Sidecar returned a different collection name")
        if data.get("dimension") != config.expected_dimension:
            raise RuntimeError("Sidecar returned a different vector dimension")
        if data.get("metric") != config.metric:
            raise RuntimeError("Sidecar returned a different vector metric")
        self._config = config
        self._started = True
        return ProviderHealth(
            provider="kylin",
            status="ok",
            details={
                "database_path": data.get("database_path", ""),
                "collection_name": config.collection_name,
                "dimension": config.expected_dimension,
                "metric": config.metric,
            },
        )

    def close(self) -> None:
        if self._started:
            self._client.vector_close()
        self._started = False
        self._config = None

    def health(self) -> ProviderHealth:
        """Compatibility health probe used by the HTTP health endpoint."""
        if not self._started or self._config is None:
            return ProviderHealth(
                provider="kylin",
                status="stopped",
                details={},
            )
        try:
            sidecar = self._client.health()
            status = "ok" if sidecar.get("vector_status") == "ready" else "unavailable"
            return ProviderHealth(
                provider="kylin",
                status=status,
                details={
                    "collection_name": self._config.collection_name,
                    "dimension": self._config.expected_dimension,
                    "metric": self._config.metric,
                },
            )
        except Exception as exc:
            return ProviderHealth(
                provider="kylin",
                status="unavailable",
                details={"error": str(exc)},
            )

    def ensure_collection(self, spec: CollectionSpec) -> None:
        self._require_started()
        assert self._config is not None
        if spec.name != self._config.collection_name:
            raise ValueError("collection name differs from start config")
        if spec.dimension != self._config.expected_dimension:
            raise ValueError("collection dimension differs from start config")
        if spec.metric != self._config.metric:
            raise ValueError("collection metric differs from start config")
        self._client.ensure_collection(spec.model_dump(mode="json"))

    def upsert(self, items: list[VectorItem]) -> UpsertResult:
        self._require_started()
        if not items:
            return UpsertResult(upserted=0)
        assert self._config is not None
        payload_items: list[dict[str, object]] = []
        for item in items:
            if len(item.vector) != self._config.expected_dimension:
                raise ValueError("upsert vector dimension mismatch")
            payload_items.append(item.model_dump(mode="json"))
        data = self._client.vector_upsert(payload_items)
        return UpsertResult.model_validate(data)

    def query(self, request: VectorQuery) -> list[VectorHit]:
        self._require_started()
        assert self._config is not None
        if len(request.vector) != self._config.expected_dimension:
            raise ValueError("query vector dimension mismatch")
        data = self._client.vector_query(request.model_dump(mode="json"))
        hits = data.get("hits")
        if not isinstance(hits, list):
            raise RuntimeError("Sidecar query response is missing hits")
        return [VectorHit.model_validate(hit) for hit in hits]

    def delete(self, vector_pks: list[int]) -> DeleteResult:
        self._require_started()
        if not vector_pks:
            return DeleteResult(deleted=0, missing_vector_pks=[])
        data = self._client.vector_delete(vector_pks)
        return DeleteResult.model_validate(data)

    def _require_started(self) -> None:
        if not self._started:
            raise RuntimeError("KylinVectorStoreAdapter not started")
