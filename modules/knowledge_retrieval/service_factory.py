"""Service factory — 创建模块 B 的服务实例，供平台服务容器调用。

Usage (from app/dependencies/services.py):
    from modules.knowledge_retrieval.service_factory import build_knowledge_retrieval_services
    services = build_knowledge_retrieval_services(config)

Returns all knowledge, retrieval, preference, safety, and forget services.
"""
from __future__ import annotations

from typing import Any


def build_knowledge_retrieval_services(config: dict | object) -> dict[str, Any]:
    """Create and wire all Module B services from config.

    The returned services share the same embedding_provider, vector_store, and bm25
    instance, ensuring KnowledgeService writes and HybridRetriever reads from the
    same stores.
    """
    embedding_config = config_dict(config, "embedding")
    vector_config = config_dict(config, "vector_store")

    provider = str(embedding_config.get("provider", "mock")).strip().lower()
    vector_provider = str(vector_config.get("provider", "memory")).strip().lower()

    # ── EmbeddingProvider ──
    if provider == "mock":
        from adapters.embedding.mock_provider import MockEmbeddingProvider
        dim = embedding_config.get("dim", 768)
        emb = MockEmbeddingProvider(dim=dim)
    elif provider == "fallback":
        from adapters.embedding.fallback_provider import FallbackEmbeddingProvider
        model = embedding_config.get("model_name", "BAAI/bge-small-zh-v1.5")
        emb = FallbackEmbeddingProvider(model_name=model)
    else:
        raise ValueError(
            f"unsupported embedding provider {provider!r}; "
            "expected 'mock' or 'fallback'"
        )

    # ── VectorStoreAdapter ──
    if vector_provider == "faiss":
        from adapters.vector_store.faiss_vector_store import FaissVectorStore
        vs = FaissVectorStore(dim=getattr(emb, "_dim", 768))
    elif vector_provider == "memory":
        from adapters.vector_store.memory_vector_store import MemoryVectorStore
        vs = MemoryVectorStore(dim=getattr(emb, "_dim", 768))
    else:
        raise ValueError(
            f"unsupported vector provider {vector_provider!r}; "
            "expected 'memory' or 'faiss'"
        )

    # ── BM25Retriever ──
    from modules.knowledge_retrieval.bm25 import BM25Retriever
    bm = BM25Retriever()

    # ── KnowledgeService (shares emb, vs, bm) ──
    from modules.knowledge_retrieval.knowledge_service import KnowledgeService
    ks = KnowledgeService(emb, vs, bm)

    # ── HybridRetriever (shares emb, vs, bm) ──
    from modules.knowledge_retrieval.hybrid_retriever import HybridRetriever
    hr = HybridRetriever(emb, vs, bm)

    from modules.preference_safety.forget_service import ForgetService
    from modules.preference_safety.preference_service import PreferenceService
    from modules.preference_safety.safety_service import SafetyService

    return {
        "embedding_provider": emb,
        "vector_store": vs,
        "bm25": bm,
        "knowledge_service": ks,
        "hybrid_retriever": hr,
        "preference_service": PreferenceService(),
        "safety_service": SafetyService(),
        "forget_service": ForgetService(),
    }


def config_value(cfg: Any, name: str, default: Any = None) -> Any:
    """Read a config value from dict or Pydantic model."""
    if isinstance(cfg, dict):
        return cfg.get(name, default)
    return getattr(cfg, name, default) if hasattr(cfg, name) else default


def config_dict(cfg: Any, name: str) -> dict:
    """Read a nested config section as dict."""
    val = config_value(cfg, name, {})
    if isinstance(val, dict):
        return val
    if hasattr(val, "model_dump"):
        return val.model_dump()
    return {}
