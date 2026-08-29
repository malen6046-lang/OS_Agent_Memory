"""Verify the real Kylin EmbeddingProvider without starting FastAPI."""

from __future__ import annotations

import json

from adapters.embedding.kylin_provider import KylinEmbeddingProvider


def main() -> int:
    provider = KylinEmbeddingProvider(model_name="ensemble-embd_gte-base_uint8-text")
    try:
        health = provider.start()
        model = provider.model_info()
        batch = provider.encode(["用户喜欢深色主题。"])
        deep_health = provider.health(deep=True)
        print(
            json.dumps(
                {
                    "health": health.model_dump(mode="json"),
                    "model": model.model_dump(mode="json"),
                    "vector_count": len(batch.vectors),
                    "first_vector_dimension": (
                        len(batch.vectors[0]) if batch.vectors else 0
                    ),
                    "deep_health": deep_health.model_dump(mode="json"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    finally:
        provider.close()


if __name__ == "__main__":
    raise SystemExit(main())
