"""Embedding unit tests — lifecycle, encode, health, model_info."""
import pytest


class FakeEmbedding:
    def __init__(self, dim=4):
        self._dim, self._started = dim, False
    def start(self):
        self._started = True
        return {"provider":"fake","status":"healthy","model":"fake","dimension":self._dim,"load_ms":1}
    def close(self):
        self._started = False
    def health(self, deep=False):
        if not self._started:
            return {"provider":"fake","status":"stopped","model":"fake","dimension":0}
        r = {"provider":"fake","status":"healthy","model":"fake","dimension":self._dim}
        if deep:
            r["deep_ms"] = 2.0; r["deep_dim"] = self._dim
        return r
    def model_info(self):
        return {"model_name":"fake","dimension":self._dim,"provider":"fake","fingerprint":f"fake@{self._dim}d"}
    def encode(self, texts):
        if not self._started:
            raise RuntimeError("not started")
        vectors, errors = [], []
        for i, t in enumerate(texts):
            if not t.strip():
                errors.append({"index":i,"error":"empty_text"})
                continue
            vectors.append([0.1*(hash(t)%100+j) for j in range(self._dim)])
        return {"vectors":vectors,"dimension":self._dim,"model_name":"fake","errors":errors or None}


class TestLifecycle:
    def test_start(self):
        h = FakeEmbedding(8).start()
        assert h["status"] == "healthy" and h["dimension"] == 8
    def test_not_started_raises(self):
        with pytest.raises(RuntimeError): FakeEmbedding().encode(["x"])
    def test_close_stopped(self):
        e = FakeEmbedding(); e.start(); e.close()
        assert e.health()["status"] == "stopped"


class TestEncode:
    def test_batch(self):
        e = FakeEmbedding(); e.start()
        b = e.encode(["a", "b"])
        assert len(b["vectors"]) == 2 and b["dimension"] == 4
    def test_empty(self):
        e = FakeEmbedding(); e.start()
        b = e.encode(["", "  "])
        assert len(b["vectors"]) == 0 and len(b["errors"]) == 2
    def test_mixed(self):
        e = FakeEmbedding(); e.start()
        b = e.encode(["ok", "", "x"])
        assert len(b["vectors"]) == 2 and len(b["errors"]) == 1


class TestHealth:
    def test_shallow(self):
        e = FakeEmbedding(); e.start()
        assert e.health()["status"] == "healthy"
    def test_deep(self):
        e = FakeEmbedding(); e.start()
        h = e.health(deep=True)
        assert h["status"] == "healthy" and "deep_ms" in h


class TestModelInfo:
    def test_fields(self):
        e = FakeEmbedding(16); e.start()
        i = e.model_info()
        assert i["dimension"] == 16 and "fingerprint" in i
