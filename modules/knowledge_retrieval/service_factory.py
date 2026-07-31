"""Service factory — 创建模块 B 的服务实例，供平台服务容器调用。

Usage (from app/dependencies/services.py):
    from modules.knowledge_retrieval.service_factory import build_knowledge_retrieval_services
    services = build_knowledge_retrieval_services(config)

Returns dict with: embedding_provider, vector_store, bm25, knowledge_service, hybrid_retriever
"""
from __future__ import annotations

from typing import Any


def build_knowledge_retrieval_services(config: dict | object) -> dict[str, Any]:
    """Create and wire all Module B services from config.

    The returned services share the same embedding_provider, vector_store, and bm25
    instance, ensuring KnowledgeService writes and HybridRetriever reads from the
    same stores.
    """
    embedding_config = _get_attr(config, "embedding", {})
    vector_config = _get_attr(config, "vector_store", {})
    retrieval_config = _get_attr(config, "retrieval", {})

    provider = embedding_config.get("provider", "memory")
    vector_provider = vector_config.get("provider", "memory")

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
        from adapters.embedding.mock_provider import MockEmbeddingProvider
        emb = MockEmbeddingProvider(dim=768)

    emb.start()

    # ── VectorStoreAdapter ──
    if vector_provider == "faiss":
        from adapters.vector_store.faiss_vector_store import FaissVectorStore
        vs = FaissVectorStore(dim=getattr(emb, "_dim", 768))
    else:
        from adapters.vector_store.memory_vector_store import MemoryVectorStore
        vs = MemoryVectorStore(dim=getattr(emb, "_dim", 768))

    vs.start({"dim": getattr(emb, "_dim", 768)})

    # ── BM25Retriever ──
    from modules.knowledge_retrieval.bm25 import BM25Retriever
    bm = BM25Retriever()

    # ── KnowledgeService (shares emb, vs, bm) ──
    from modules.knowledge_retrieval.knowledge_service import KnowledgeService
    ks = KnowledgeService(emb, vs, bm)

    # ── HybridRetriever (shares emb, vs, bm) ──
    from modules.knowledge_retrieval.hybrid_retriever import HybridRetriever
    hr = HybridRetriever(emb, vs, bm)

    return {
        "embedding_provider": emb,
        "vector_store": vs,
        "bm25": bm,
        "knowledge_service": ks,
        "hybrid_retriever": hr,
    }


def _get_attr(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)
