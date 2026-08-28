# 麒麟 SDK 算法接入最终验收报告

## 1. 验收结论

OS Agent Memory 算法模块已经完成银河麒麟 Embedding SDK 与 Vector Engine SDK 接入，并通过真实麒麟虚拟机上的功能、持久化、遗忘、准确率、性能及用户隔离验收。

最终检索策略冻结为：

1. 麒麟 Embedding 与 Vector Engine 正常时，使用 GTE-base Dense 检索并保留原始余弦相似度排序。
2. Embedding 或 Vector Engine 异常时，降级使用持久化 BM25 检索。
3. 不使用等权 RRF 融合，因为 dev 与 held-out 均证明其准确率低于纯 Dense。
4. 无答案拒答机制保留为可配置能力，但默认关闭；Dataset V0.1 仅有 2 条无答案样本，不足以确定可靠的生产阈值。

总体状态：**通过**。

## 2. SDK 与运行环境

| 项目 | 验收配置 |
|---|---|
| 操作系统 | 银河麒麟桌面系统，x86_64 |
| Python | CPython 3.12.3 |
| Embedding SDK | `libkysdk-coreai-embedding.so.1`，SDK 1.0.0 |
| Vector SDK | `libkysdk-vector-engine-client.so.1`，SDK 1.0.0 |
| Embedding 模型 | `ensemble-embd_gte-base_uint8-text` |
| 向量维度 | 768 |
| 距离指标 | cosine |
| 向量桥接 | `libosam_kylin_vector_bridge.so`，C++ 到 C ABI 再由 Python `ctypes` 调用 |
| 正式向量库 | `$HOME/.local/share/os-agent-memory/vector.db` |
| 独立评测库 | `$HOME/.local/share/os-agent-memory/evaluation-vector.db` |

SDK 健康检查、模型初始化、向量集合初始化均返回 `status=ok`。评测使用独立向量数据库，并在结束后自动删除评测向量。

## 3. 功能验收

以下链路均已在真实麒麟环境验证通过：

- Embedding SDK 独立加载、模型初始化及 768 维向量生成。
- Vector Engine SDK 建库、建集合、写入、查询和删除。
- 正式 API 记忆写入与语义检索。
- SQLite、麒麟 Vector DB 和 BM25 状态跨服务重启持久化。
- 遗忘预览、确认执行、SQLite 逻辑删除、向量删除和 BM25 清理。
- 遗忘后立即搜索无结果，服务再次重启后仍无结果。
- Dense-first 正式 API 返回麒麟余弦分数；测试查询得分 `0.8208449483`，不再返回旧 RRF 分数 `0.032786...`。
- 搜索公开响应不再包含完整 embedding 数组。
- 算法及 SDK Adapter 回归测试：`18 passed in 3.52s`。

## 4. Dataset V0.1 准确率

数据集包含 60 条知识语料和 78 条检索查询，其中 76 条有答案查询、2 条无答案查询。`inactive` 遗留状态仅在评测脚本中映射为冻结契约支持的 `expired`，未修改数据集或公共契约。

### 4.1 Dev

| 指标 | Dense | 等权 RRF Hybrid |
|---|---:|---:|
| Recall@1 | 82.76% | 76.72% |
| Hit@1 | 94.83% | 87.93% |
| Recall@3 | 100.00% | 97.41% |
| Recall@5 | 100.00% | 98.28% |
| Recall@10 | 100.00% | 98.28% |
| MRR | 97.41% | 93.10% |
| 跨用户泄漏 | 0 | 0 |

### 4.2 Held-out

Held-out 仅在 dev 策略冻结后运行一次，未依据其结果继续调参。

| 指标 | Dense | 等权 RRF Hybrid |
|---|---:|---:|
| Recall@1 | 83.33% | 77.78% |
| Hit@1 | 88.89% | 83.33% |
| Recall@3 | 100.00% | 100.00% |
| Recall@5 | 100.00% | 100.00% |
| Recall@10 | 100.00% | 100.00% |
| MRR | 93.52% | 89.81% |
| 跨用户泄漏 | 0 | 0 |

### 4.3 综合结果

按 76 条有答案查询加权：

| 指标 | Dense 综合结果 |
|---|---:|
| Recall@1 | 82.89% |
| Hit@1 | 93.42% |
| Recall@3 | 100.00% |
| Recall@5 | 100.00% |
| Recall@10 | 100.00% |
| MRR | 96.49% |

Recall@1 低于 Hit@1 的主要原因是部分查询具有多个 gold memory，Recall@1 按命中的 gold 数量计算；这不代表 Top-1 完全未命中。

两条无答案查询均会产生近邻结果。dev 预选的低分差规则未在 held-out 上泛化，因此拒答阈值保持关闭，不把有限样本结果冒充生产能力。

## 5. 性能结果

### 5.1 SDK 直连基线

30 次真实 SDK 基准：

| 操作 | Mean | P50 | P95 | P99 | Max |
|---|---:|---:|---:|---:|---:|
| Embedding | 33.825 ms | 31.802 ms | 52.213 ms | 69.061 ms | 71.590 ms |
| Vector Upsert | 10.885 ms | 6.489 ms | 38.450 ms | 60.306 ms | 65.690 ms |
| Vector Query | 3.161 ms | 2.822 ms | 5.635 ms | 7.048 ms | 7.612 ms |
| Encode→Upsert→Query | 47.954 ms | 41.704 ms | 78.435 ms | 116.269 ms | 131.297 ms |
| Delete | 3.831 ms | 3.842 ms | 4.992 ms | 5.462 ms | 5.614 ms |

### 5.2 最终 HTTP API 基准

配置：5 次写入、5 次搜索预热、30 次正式搜索、`top_k=5`。

| API | Mean | P50 | P95 | P99 | Max |
|---|---:|---:|---:|---:|---:|
| Ingest | 93.909 ms | 54.155 ms | 187.124 ms | 200.296 ms | 203.589 ms |
| Search | 30.416 ms | 30.021 ms | 38.635 ms | 44.760 ms | 47.206 ms |
| Forget Preview | 7.483 ms | — | — | — | — |
| Forget Execute | 22.953 ms | — | — | — | — |
| Cleanup Search | 18.166 ms | — | — | — | — |

与最初 HTTP 基线相比：

- Search P95：`46.507 ms → 38.635 ms`，改善约 **16.9%**。
- Search 平均响应：`83,503 bytes → 2,410 bytes`，减少约 **97.1%**。
- 所有关键检索延迟均显著低于 500 ms 目标。
- 最终性能测试 `cleanup=passed`。

Ingest P95 为 `187.124 ms`，较最初基线存在约 12.7% 波动；其响应仍约 52 KB。原因是后端 Orchestrator 写入响应包含完整 embedding。该问题属于后端响应 DTO/编排区域，不在算法负责人授权修改范围内，建议交由后端负责人压缩公开响应。

## 6. 安全、隔离与数据清理

- Dev 和 held-out 的 Dense/Hybrid 跨用户泄漏均为 0。
- 向量查询强制使用 `user_id + active status` 过滤。
- 评测对私有用户同时考虑本人空间及约定的公共知识空间 `usr_corpus_shared`。
- 遗忘使用精确向量主键删除，未使用 DropCollection。
- BM25 删除状态持久化，重启后不会恢复已遗忘文档。
- 正式搜索响应已删除公开 `attributes.embedding`，避免传输 768 维向量。

## 7. 已知边界

1. 无答案数据仅 2 条，当前不能建立可靠拒答阈值；功能默认关闭。
2. Ingest 响应仍包含大体积向量数据，需要后端负责人处理。
3. `8000` 端口由麒麟 `kytensor` 占用，项目服务使用 `127.0.0.1:18080`，不得停止系统服务以抢占端口。
4. Vector Engine `.pc` 文件引用了不存在的 include 路径；原生桥接 CMake 已在算法 SDK 区域做兼容过滤。
5. 当前验收对象为 GTE-base 768 维模型；切换 BGE、BCE 或 M3E 时必须使用独立集合或数据库，并重新验证维度、准确率和性能。

## 8. 证据文件

- `evaluation/reports/kylin_gte_base_baseline.json`
- `evaluation/reports/kylin_gte_base_api_baseline.json`
- `evaluation/reports/kylin_gte_base_api_optimized.json`
- `evaluation/reports/kylin_gte_base_api_dense_first_final.json`
- `evaluation/reports/kylin_gte_base_retrieval_dev.json`
- `evaluation/reports/kylin_gte_base_retrieval_held_out.json`

## 9. 最终建议

比赛演示与正式联调使用 GTE-base Dense-first 方案。BM25 保留为 SDK 故障时的可用性保障，不参与正常结果融合；无答案拒答保持关闭并列为后续扩充数据集后的优化项。
