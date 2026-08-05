"""真实模型评测 — 用 BGE-small-zh 替代 Mock 向量。

Usage:
    python -m evaluation.run_real_eval
"""
import json
import sys
import time
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from evaluation.retrieval_eval import evaluate_retrieval, KNOWLEDGE, QUERIES
from evaluation.conflict_eval import evaluate_conflict


def main():
    print("=" * 50)
    print("真实模型评测 (BGE-small-zh)")
    print("=" * 50)

    # 真实 embedding
    try:
        from adapters.embedding.fallback_provider import FallbackEmbeddingProvider
        emb = FallbackEmbeddingProvider()  # BAAI/bge-small-zh-v1.5
        t0 = time.time()
        emb.start()
        info = emb.model_info()
        print(f"\n模型: {info['model_name']} (dim={info['dimension']})")
        print(f"加载耗时: {info.get('load_ms', 'N/A')}ms")

        r = evaluate_retrieval(embedding_provider=emb)
        print("\n=== 真实模型检索评测 ===")
        print(json.dumps(r, ensure_ascii=False, indent=2))
        emb.close()
    except Exception as e:
        print(f"\n真实模型加载失败: {type(e).__name__}: {str(e)[:120]}")
        print("改用 Mock 向量基准：")
        r = evaluate_retrieval()
        print(json.dumps(r, ensure_ascii=False, indent=2))

    print("\n=== 冲突分类评测 ===")
    print(json.dumps(evaluate_conflict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
