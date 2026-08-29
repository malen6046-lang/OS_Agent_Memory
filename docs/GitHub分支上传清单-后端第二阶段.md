# GitHub 分支上传清单：后端第二阶段

## 1. 本次上传范围

本快照以当前 Git 分支的已跟踪项目为基础，只叠加后端第二阶段相关源码、配置、测试和验证工具。它是一份完整项目，可以解压后复制到目标分支，不是只能单独使用的补丁包。

## 2. 修改文件及要点

| 文件 | 要点 |
|---|---|
| `app/core/config.py` | 增加依赖超时配置及正数校验，使各后端依赖可分别设置超时。 |
| `app/core/responses.py` | 将编排器的私有响应元数据提升到统一响应 `meta`，避免计时信息留在业务 `data`。 |
| `app/dependencies/api_service.py` | 在 API 服务边界传递 `elapsed_ms`、降级状态和 provider 信息，并精简写入响应中的大向量字段。 |
| `app/dependencies/services.py` | 注入依赖超时配置，增加服务容器预热逻辑，并把配置传给编排器。 |
| `app/main.py` | 在 FastAPI lifespan 启动阶段执行真实服务初始化和预热。 |
| `app/orchestrator/memory_orchestrator.py` | 增加写入各阶段耗时记录：safety、preference、knowledge、repository、vector_store、audit。 |
| `configs/kylin.yaml` | 配置麒麟 Embedding、向量存储实现、768 维空间、cosine 度量及依赖超时。 |

## 3. 新增文件及要点

| 目录或文件 | 要点 |
|---|---|
| `adapters/embedding/` | Python 后端到麒麟 Sidecar 的 Embedding Provider 和 Unix Socket 客户端。 |
| `adapters/vector_store/` | 麒麟向量引擎适配器，负责集合、写入、查询和健康检查。 |
| `adapters/evaluation/` | 离线 EvaluationService 实现，补齐 real 模式服务容器。 |
| `configs/kylin-real.yaml` | 麒麟真实模式配置入口。 |
| `scripts/verify_kylin_embedding.py` | 单独验证 Embedding 运行时和向量维度。 |
| `scripts/verify_kylin_vector_store.py` | 单独验证向量引擎连接、写入和查询。 |
| `tests/unit/adapters/test_evaluation_service.py` | EvaluationService 单元测试。 |
| `tests/unit/adapters/test_kylin_embedding_provider.py` | 麒麟 Embedding Provider 单元测试。 |
| `tests/unit/adapters/test_kylin_vector_store.py` | 麒麟 Vector Store 单元测试。 |
| `tests/unit/api/test_response_timing.py` | 统一响应计时元数据测试。 |
| `tools/real_perf_100.py` | 100 次写入和 20 次搜索的真实模式性能基线工具。 |
| `tools/run_retrieval_eval.py` | 检索 Recall 与延迟评测工具。 |

## 4. 明确排除的内容

- `.venv/`、`.git/`、`__pycache__/`、`.pytest_cache/` 和 `*.pyc`；
- `backup/`、`backups/`、`*.before_*` 等人工备份；
- `evaluation/baselines/`、`evaluation/diagnostics/` 等机器相关实验产物；
- 名为 `inspect`、空格文件等误生成文件；
- `modules/knowledge_retrieval/algorithm_v1_1/hybrid_retriever.py` 的本地权重实验修改。包内使用当前 Git 分支的原版算法文件，避免破坏算法源码完整性校验。

## 5. 上传前验证

解压或复制到目标分支后执行：

```bash
git status --short
python -m pytest tests/unit/adapters/test_algorithm_source_integrity.py -q
python -m pytest tests/unit/adapters/test_kylin_embedding_provider.py tests/unit/adapters/test_kylin_vector_store.py tests/unit/adapters/test_evaluation_service.py tests/unit/api/test_response_timing.py -q
```

确认无误后，在目标分支提交：

```bash
git add app adapters configs scripts tests tools docs
git commit -m "feat: complete Kylin real backend and stage2 performance instrumentation"
git push origin HEAD
```

不要提交 `.venv`、运行时数据库、Socket、日志或 `/tmp` 下的报告。
