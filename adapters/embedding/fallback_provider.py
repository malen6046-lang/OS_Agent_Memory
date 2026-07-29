"""FallbackEmbeddingProvider — sentence-transformers 本地向量化，不依赖麒麟 SDK。

Implements the EmbeddingProvider protocol from V1.1:
  start() -> ProviderHealth
  close() -> None
  health(deep: bool) -> ProviderHealth
  model_info() -> EmbeddingModelInfo
  encode(texts: list[str]) -> EmbeddingBatch
"""
from __future__ import annotations

import time
from typing import Any


class FallbackEmbeddingProvider:
    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5"):
        self._name = model_name
        self._model: Any = None
        self._dim = 0

    # ── lifecycle ──────────────────────────────────────────────

    def start(self) -> dict:
        from sentence_transformers import SentenceTransformer
        t0 = time.time()
        self._model = SentenceTransformer(self._name, device="cpu")
        self._dim = self._model.get_sentence_embedding_dimension()
        return {
            "provider": "fallback",
            "model": self._name,
            "dimension": self._dim,
            "status": "healthy",
            "load_ms": round((time.time() - t0) * 1000),
        }

    def close(self) -> None:
        self._model = None

    # ── health ─────────────────────────────────────────────────

    def health(self, deep: bool = False) -> dict:
        if self._model is None:
            return {"provider": "fallback", "status": "stopped", "model": self._name, "dimension": 0}
        result: dict = {
            "provider": "fallback",
            "status": "healthy",
            "model": self._name,
            "dimension": self._dim,
        }
        if deep:
            t0 = time.time()
            try:
                batch = self.encode(["health-check: 麒麟系统就绪"])
                vectors: list = batch["vectors"]
                if vectors and len(vectors[0]) == self._dim:
                    result["deep_ms"] = round((time.time() - t0) * 1000)
                    result["deep_dim"] = len(vectors[0])
                else:
                    result["status"] = "degraded"
            except Exception:
                result["status"] = "degraded"
                result["deep_ms"] = round((time.time() - t0) * 1000)
        return result

    # ── model info ─────────────────────────────────────────────

    def model_info(self) -> dict:
        return {
            "model_name": self._name,
            "dimension": self._dim,
            "provider": "fallback",
            "fingerprint": f"{self._name}@{self._dim}d",
        }

    # ── encode ─────────────────────────────────────────────────

    def encode(self, texts: list[str]) -> dict:
        if self._model is None:
            raise RuntimeError("EmbeddingProvider not started")
        errors: list[dict] = []
        vectors: list[list[float]] = []

        for idx, text in enumerate(texts):
            if not text or not text.strip():
                errors.append({"index": idx, "error": "empty_text", "text_len": len(text)})
                continue
            try:
                vec = self._model.encode(
                    [text],
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
                vectors.append(vec[0].tolist())
            except Exception as exc:
                errors.append({"index": idx, "error": str(exc), "text_len": len(text)})

        return {
            "vectors": vectors,
            "dimension": self._dim,
            "model_name": self._name,
            "errors": errors or None,
        }
