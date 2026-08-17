# THIRD_PARTY.md — 第三方依赖与开源模块声明

## FastAPI

- Repository: https://github.com/fastapi/fastapi
- Usage: REST API framework and OpenAPI generation
- Integration type: Runtime dependency
- Modified source: No
- Project location: app/main.py, app/api/
- Maintainer: 平台与集成负责人

## Pydantic

- Repository: https://github.com/pydantic/pydantic
- Usage: Contract validation and serialization
- Integration type: Runtime dependency
- Modified source: No
- Project location: contracts/schemas/
- Maintainer: 平台与集成负责人

## Streamlit

- Version: 1.37.1
- Repository: https://github.com/streamlit/streamlit
- License: Apache-2.0
- Usage: OS Agent Memory MVP interactive frontend
- Integration type: Frontend runtime dependency installed by package manager
- Modified source: No
- Project location: frontend/
- Maintainer: project maintainer / platform integration

## HTTPX

- Version: 0.27.0
- Repository: https://github.com/encode/httpx
- License: BSD-3-Clause
- Usage: Frontend-to-FastAPI HTTP client
- Integration type: Frontend runtime dependency installed by package manager
- Modified source: No
- Project location: frontend/src/api/client.py
- Maintainer: project maintainer / platform integration

## Uvicorn

- Version: 0.51.0
- Repository: https://github.com/Kludex/uvicorn
- License: BSD-3-Clause
- Usage: ASGI server for running the existing FastAPI backend during the MVP demo
- Integration type: Demo runtime dependency installed by package manager
- Modified source: No
- Project location: frontend/requirements.txt
- Maintainer: project maintainer / platform integration

## SQLAlchemy

- Repository: https://github.com/sqlalchemy/sqlalchemy
- Usage: SQLite ORM and transaction management
- Integration type: Runtime dependency
- Modified source: No
- Project location: app/models/, app/repositories/
- Maintainer: 平台与集成负责人
 平台与集成负责人


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
- Usage: KylinEmbeddingProvider 主线
- Integration type: System package (libkysdk-coreai-embedding.so)
- Modified source: No
- Project location: adapters/embedding/kylin_provider/
- Maintainer: 算法负责人

## libkysdk-vector-engine-client (麒麟 SDK)

- Source: libkysdk-vector-engine-client-openkylin-nile-sp2
- License: Apache-2.0 (修改自 Milvus C++ SDK)
- Usage: KylinVectorStoreAdapter 主线
- Integration type: System package + local C ABI bridge
- Modified source: No (SDK); Yes (project-owned bridge)
- Project location: adapters/vector_store/kylin_vector_store/
- Maintainer: 算法负责人
 main
