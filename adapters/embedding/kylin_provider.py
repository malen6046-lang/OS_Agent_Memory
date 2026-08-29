"""V1.2.2 EmbeddingProvider backed by the local Kylin C++ Sidecar."""

from __future__ import annotations

from typing import Any

from contracts.schemas.provider import (
    EmbeddingBatch,
    EmbeddingModelInfo,
    ProviderHealth,
)

from .kylin_sidecar_client import KylinSidecarClient, KylinSidecarError


class KylinEmbeddingProvider:
    """Adapt Sidecar JSON to the frozen Pydantic provider contracts."""

    def __init__(
        self,
        model_name: str = "default",
        config: Any = None,
        app_config: Any = None,
        client: KylinSidecarClient | None = None,
    ) -> None:
        del config, app_config
        self._expected_model = model_name.strip()
        self._client = client or KylinSidecarClient()
        self._started = False
        self._model: EmbeddingModelInfo | None = None

    def start(self) -> ProviderHealth:
        health_data = self._client.health()
        if health_data.get("status") != "ready":
            raise RuntimeError(
                f"Kylin Sidecar is not ready: {health_data.get('status')!r}"
            )
        model = self._parse_model_info(self._client.model_info())
        if self._expected_model not in {"", "default", model.model_name}:
            raise RuntimeError(
                "Kylin Sidecar model mismatch: "
                f"expected {self._expected_model!r}, got {model.model_name!r}"
            )
        self._model = model
        self._started = True
        return ProviderHealth(
            provider=model.provider,
            status="ok",
            details={
                "model_name": model.model_name,
                "dimension": model.dimension,
                "model_fingerprint": model.model_fingerprint,
            },
        )

    def close(self) -> None:
        self._started = False
        self._model = None

    def health(self, deep: bool = False) -> ProviderHealth:
        if not self._started or self._model is None:
            return ProviderHealth(
                provider="kylin-ai-runtime",
                status="stopped",
                details={},
            )
        try:
            data = self._client.health()
            status = "ok" if data.get("status") == "ready" else "unavailable"
            details: dict[str, Any] = {
                "model_name": self._model.model_name,
                "dimension": self._model.dimension,
            }
            if deep:
                batch_data = self._client.encode(["health-check"])
                vectors = batch_data.get("vectors")
                valid = (
                    isinstance(vectors, list)
                    and len(vectors) == 1
                    and isinstance(vectors[0], list)
                    and len(vectors[0]) == self._model.dimension
                )
                details["deep_check"] = valid
                details["elapsed_ms"] = batch_data.get("elapsed_ms", 0)
                if not valid:
                    status = "degraded"
            return ProviderHealth(
                provider=self._model.provider,
                status=status,
                details=details,
            )
        except KylinSidecarError as exc:
            return ProviderHealth(
                provider=self._model.provider,
                status="unavailable",
                details={"error": str(exc)},
            )

    def model_info(self) -> EmbeddingModelInfo:
        self._require_started()
        assert self._model is not None
        return self._model

    def encode(self, texts: list[str]) -> EmbeddingBatch:
        self._require_started()
        assert self._model is not None
        if not texts:
            return EmbeddingBatch(
                vectors=[],
                model_name=self._model.model_name,
                dimension=self._model.dimension,
            )
        if any(not isinstance(text, str) or not text for text in texts):
            raise ValueError("texts must contain non-empty strings")

        data = self._client.encode(texts)
        vectors = data.get("vectors")
        if not isinstance(vectors, list) or len(vectors) != len(texts):
            raise RuntimeError("Kylin Sidecar returned a different number of vectors")
        model_name = data.get("model")
        dimension = data.get("dimension")
        if model_name != self._model.model_name:
            raise RuntimeError("Kylin Sidecar changed model during encode")
        if dimension != self._model.dimension:
            raise RuntimeError("Kylin Sidecar changed dimension during encode")
        return EmbeddingBatch(
            vectors=vectors,
            model_name=model_name,
            dimension=dimension,
        )

    def _require_started(self) -> None:
        if not self._started:
            raise RuntimeError("KylinEmbeddingProvider not started")

    @staticmethod
    def _parse_model_info(data: dict[str, Any]) -> EmbeddingModelInfo:
        return EmbeddingModelInfo(
            provider=data.get("provider"),
            model_name=data.get("model"),
            dimension=data.get("dimension"),
            model_fingerprint=data.get("space_id"),
        )
