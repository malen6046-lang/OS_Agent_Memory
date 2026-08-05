"""MockEmbeddingProvider — 测试用固定向量，跨进程可复现。

Uses hashlib.sha256 for deterministic output across Python processes
(unlike built-in hash() which depends on PYTHONHASHSEED).
"""
import hashlib


class MockEmbeddingProvider:
    def __init__(self, dim: int = 768):
        self._dim = dim
        self._started = False

    def start(self) -> dict:
        self._started = True
        return {"provider": "mock", "status": "healthy", "model": "mock", "dimension": self._dim, "load_ms": 0}

    def close(self) -> None:
        self._started = False

    def health(self, deep: bool = False) -> dict:
        if not self._started:
            return {"provider": "mock", "status": "stopped", "model": "mock", "dimension": 0}
        r = {"provider": "mock", "status": "healthy", "model": "mock", "dimension": self._dim}
        if deep:
            r["deep_ms"] = 0.0
            r["deep_dim"] = self._dim
        return r

    def model_info(self) -> dict:
        return {"model_name": "mock", "dimension": self._dim, "provider": "mock", "fingerprint": "mock"}

    def encode(self, texts: list[str]) -> dict:
        if not self._started:
            raise RuntimeError("MockEmbeddingProvider not started")
        vectors = []
        errors = []
        for idx, text in enumerate(texts):
            if not text or not text.strip():
                errors.append({"index": idx, "error": "empty_text"})
                continue
            h = hashlib.sha256(text.encode("utf-8")).digest()
            vec = [(h[i % len(h)] / 255.0) for i in range(self._dim)]
            vectors.append(vec)
        return {"vectors": vectors, "dimension": self._dim, "model_name": "mock", "errors": errors or None}
