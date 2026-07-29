"""Tests for embedding providers — V1.1 embedding unit tests.

Tests the FallbackEmbeddingProvider (if sentence-transformers is installed)
and a deterministic fake for CI-safe testing.
"""
import pytest


# ── Deterministic fake ──────────────────────────────────────────


class FakeEmbeddingProvider:
    def __init__(self, dim: int = 4):
        self._dim = dim
        self._started = False

    def start(self) -> dict:
        self._started = True
        return {"provider": "fake", "status": "healthy", "model": "fake-test", "dimension": self._dim, "load_ms": 5.0}

    def close(self) -> None:
        self._started = False

    def health(self, deep: bool = False) -> dict:
        if not self._started:
            return {"provider": "fake", "status": "stopped", "model": "fake-test", "dimension": 0}
        r = {"provider": "fake", "status": "healthy", "model": "fake-test", "dimension": self._dim}
        if deep:
            r["deep_ms"] = 2.0
            r["deep_dim"] = self._dim
        return r

    def model_info(self) -> dict:
        return {"model_name": "fake-test", "dimension": self._dim, "provider": "fake", "fingerprint": f"fake@{self._dim}d"}

    def encode(self, texts: list[str]) -> dict:
        if not self._started:
            raise RuntimeError("not started")
        errors = []
        vectors = []
        for idx, t in enumerate(texts):
            if not t or not t.strip():
                errors.append({"index": idx, "error": "empty_text", "text_len": len(t)})
                continue
            vectors.append([0.1 * (hash(t) % 100 + i) for i in range(self._dim)])
        return {"vectors": vectors, "dimension": self._dim, "model_name": "fake-test", "errors": errors or None}


# ── Tests on deterministic fake ─────────────────────────────────


class TestEmbeddingLifecycle:
    def test_start_returns_health(self):
        e = FakeEmbeddingProvider(dim=8)
        h = e.start()
        assert h["status"] == "healthy"
        assert h["dimension"] == 8

    def test_not_started_encode_raises(self):
        e = FakeEmbeddingProvider()
        with pytest.raises(RuntimeError):
            e.encode(["hello"])

    def test_close_then_health_stopped(self):
        e = FakeEmbeddingProvider()
        e.start()
        e.close()
        assert e.health()["status"] == "stopped"


class TestEmbeddingEncode:
    def test_encode_returns_batch_structure(self):
        e = FakeEmbeddingProvider()
        e.start()
        batch = e.encode(["测试文本", "hello world"])
        assert "vectors" in batch
        assert "dimension" in batch
        assert "model_name" in batch
        assert len(batch["vectors"]) == 2
        assert len(batch["vectors"][0]) == e._dim

    def test_encode_empty_texts(self):
        e = FakeEmbeddingProvider()
        e.start()
        batch = e.encode(["", "   "])
        assert len(batch["vectors"]) == 0
        assert batch["errors"] is not None
        assert len(batch["errors"]) == 2

    def test_encode_mixed_valid_and_empty(self):
        e = FakeEmbeddingProvider()
        e.start()
        batch = e.encode(["有效文本", "", "another"])
        assert len(batch["vectors"]) == 2
        assert batch["errors"] is not None
        assert len(batch["errors"]) == 1

    def test_encode_chinese_batch(self):
        e = FakeEmbeddingProvider(dim=16)
        e.start()
        texts = ["麒麟系统终端快捷键", "用户偏好深色主题", "数据库备份自动执行"]
        batch = e.encode(texts)
        assert len(batch["vectors"]) == 3
        assert all(len(v) == 16 for v in batch["vectors"])


class TestEmbeddingHealth:
    def test_health_shallow(self):
        e = FakeEmbeddingProvider()
        e.start()
        h = e.health(deep=False)
        assert h["status"] == "healthy"

    def test_health_deep(self):
        e = FakeEmbeddingProvider()
        e.start()
        h = e.health(deep=True)
        assert h["status"] == "healthy"
        assert "deep_ms" in h
        assert h["deep_dim"] == e._dim


class TestEmbeddingModelInfo:
    def test_model_info_fields(self):
        e = FakeEmbeddingProvider(dim=768)
        e.start()
        info = e.model_info()
        assert info["model_name"] == "fake-test"
        assert info["dimension"] == 768
        assert info["provider"] == "fake"
        assert "fingerprint" in info


# ── Optional: real fallback provider tests ──────────────────────


class TestFallbackEmbeddingIfAvailable:
    @pytest.fixture(autouse=False)
    def provider(self):
        try:
            from adapters.embedding.fallback_provider import FallbackEmbeddingProvider
        except ImportError:
            pytest.skip("sentence-transformers not installed")
        p = FallbackEmbeddingProvider()
        p.start()
        yield p
        p.close()

    def test_real_health_deep(self, provider):
        h = provider.health(deep=True)
        assert h["status"] in ("healthy", "degraded")
        if h["status"] == "healthy":
            assert "deep_dim" in h

    def test_real_model_info(self, provider):
        info = provider.model_info()
        assert info["dimension"] > 0
        assert info["model_name"]
        assert info["provider"] == "fallback"

    def test_real_encode_chinese(self, provider):
        batch = provider.encode(["麒麟系统终端测试"])
        assert len(batch["vectors"]) == 1
        assert len(batch["vectors"][0]) == provider._dim
