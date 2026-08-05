# THIRD_PARTY.md — 第三方依赖与开源模块声明

## FastAPI

- Locked version: 0.140.13

- Repository: https://github.com/fastapi/fastapi
- Usage: REST API framework and OpenAPI generation
- Integration type: Runtime dependency
- Modified source: No
- Project location: app/main.py, app/api/
- Maintainer: 平台与集成负责人

## Starlette

- Repository: https://github.com/Kludex/starlette
- Locked version: 1.3.1
- Usage: ASGI runtime used by FastAPI
- Integration type: Runtime dependency
- Modified source: No
- Project location: app/main.py
- Maintainer: Platform and integration owner

## HTTPX

- Repository: https://github.com/encode/httpx
- Locked version: 0.28.1
- Usage: ASGI HTTP integration tests without deprecated TestClient wrappers
- Integration type: Test dependency
- Modified source: No
- Project location: tests/asgi_client.py, tests/api/, tests/integration/
- Maintainer: Platform and integration owner

## Pydantic

- Locked version: 2.13.4

- Repository: https://github.com/pydantic/pydantic
- Usage: Contract validation and serialization
- Integration type: Runtime dependency
- Modified source: No
- Project location: contracts/schemas/
- Maintainer: 平台与集成负责人

## SQLAlchemy

- Locked version: 2.0.51

- Repository: https://github.com/sqlalchemy/sqlalchemy
- Usage: SQLite ORM and transaction management
- Integration type: Runtime dependency
- Modified source: No
- Project location: app/models/, app/repositories/
- Maintainer: 平台与集成负责人

## sentence-transformers

- Repository: https://github.com/UKPLab/sentence-transformers
- License: Apache-2.0
- Usage: FallbackEmbeddingProvider 文本向量化
- Integration type: Runtime dependency
- Modified source: No
- Project location: adapters/embedding/fallback_provider.py
- Maintainer: 算法负责人

## numpy

- Repository: https://github.com/numpy/numpy
- License: BSD-3-Clause
- Usage: 向量余弦相似度计算 (MemoryVectorStore, FaissVectorStore)
- Integration type: Runtime dependency
- Modified source: No
- Project location: adapters/vector_store/memory_vector_store.py, adapters/vector_store/faiss_vector_store.py
- Maintainer: 算法负责人

## FAISS

- Repository: https://github.com/facebookresearch/faiss
- License: MIT
- Usage: FaissVectorStore fallback 向量检索 (可选依赖)
- Integration type: Optional runtime dependency
- Modified source: No
- Project location: adapters/vector_store/faiss_vector_store.py
- Maintainer: 算法负责人

## BM25 (scorta/BM25 参考)

- Repository: https://github.com/scorta/BM25
- License: MIT
- Usage: BM25 关键词评分算法 (从 C++ 移植为 Python)
- Integration type: Algorithm reference, reimplemented
- Modified source: Yes (ported to Python, fixed tokenizer bug)
- Project location: modules/knowledge_retrieval/bm25.py
- Maintainer: 算法负责人

## memory_tier (dsco 参考)

- Repository: https://github.com/arthurcolle/dsco
- License: MIT
- Usage: 三层记忆衰减算法 (从 C 移植为 Python)
- Integration type: Algorithm reference, reimplemented
- Modified source: Yes (ported to Python)
- Project location: modules/knowledge_retrieval/memory_tier.py
- Maintainer: 算法负责人

## kylin-coreai-embedding (麒麟 SDK)

- Source: kylin-coreai-embedding-openkylin-nile-sp2
- License: GPLv3-or-later
- Usage: KylinEmbeddingProvider 主线 (待麒麟目标机接入)
- Integration type: System package (libkysdk-coreai-embedding.so)
- Modified source: No
- Project location: adapters/embedding/kylin_provider/ (待实现)
- Maintainer: 算法负责人

## libkysdk-vector-engine-client (麒麟 SDK)

- Source: libkysdk-vector-engine-client-openkylin-nile-sp2
- License: Apache-2.0 (修改自 Milvus C++ SDK)
- Usage: KylinVectorStoreAdapter 主线 (待麒麟目标机接入)
- Integration type: System package (libkysdk-vector-engine-client.so)
- Modified source: No
- Project location: adapters/vector_store/kylin_vector_store/ (待实现)
- Maintainer: 算法负责人
