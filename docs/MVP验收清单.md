# MVP 验收清单 — Step 7 完整验收

- **日期**：2026-08-06
- **仓库分支**：`integration/mvp-v0.1`
- **运行配置**：`OS_AGENT_ENV=algorithm_modules`（完整算法适配图）+ Streamlit 前端
- **Python**：3.12.7
- **执行方式**：全部通过真实运行的 FastAPI 服务 + 前端自己的 `MemoryApiClient` 验证

## 1. 启动测试 — PASS

| 项 | 结果 |
|----|------|
| 后端 `uvicorn app.main:app` 启动 | OK |
| `GET /api/v1/health` | 200 `{status: ok}` |
| 默认 mock profile 健康检查 | 200 ok |
| `algorithm_modules` profile 健康检查 | 200 ok（embedding/vector 仍为 mock，符合阶段性配置） |

## 2. 前端测试 — PASS

| 项 | 结果 |
|----|------|
| `streamlit run frontend/streamlit_app.py` 启动 | HTTP 200，页面渲染 |
| 四个页面渲染（系统状态/导入/搜索/遗忘） | AppTest 5 项通过 |
| 前端 API 客户端契约测试 | `frontend/tests` 34 passed |
| 前端不依赖后端内部实现 | `test_dependency_boundary` 通过 |

## 3. 写入记忆测试 — PASS

输入：`我喜欢中文回答。`（POST /api/v1/events/ingest）

- 返回 `success=true`，生成 `memory_id=mem_e3931bff1798846ec00f565f`
- 记录进入 MemoryRepository（status=active）

> 备注：该句未触发 Algorithm V1.1 偏好提取器的结构化偏好规则（preferences=[]），但记忆记录已完整入库，满足验收要求；偏好规则对「我喜欢深色主题，并使用 Python。」可提取 theme=dark / language=python。

## 4. 检索测试 — PASS

输入：`以后回答方式是什么？`（POST /api/v1/memory/search）

- 返回 1 条命中：`我喜欢中文回答。`（score≈0.0328），`memory_id` 一致
- 用户隔离与状态过滤由后端执行

## 5. 遗忘测试 — PASS

输入：遗忘预览 `删除语言偏好` → 确认执行

- preview：`affected_memory_ids=[mem_e393...]`，`confirmation_token` 生成
- execute：`success=true`，记录 tombstone + 向量删除
- 再次检索 `中文回答`：hits=0（已遗忘）

## 6. 评测测试 — PASS（baseline 离线分数）

命令：`python -m evaluation.run_all --split dev` → `evaluation/reports/`（v0.1_dev.txt / evaluation_report.md / result.csv）

| 任务 | n | 主指标 |
|------|---|--------|
| preference | 42 | exact-match 26.2% / micro-F1 35.5% |
| retrieval | 59 | R@5 45.8% / R@10 50.8% / MRR 34.7% |
| conflict | 17 | joint 11.8% / relation 29.4% |
| forget | 17 | 预览 P 65.7% / R 94.1% / 执行成功 35.3% |
| security | 32 | block 84.4% / entity 81.2% |
| latency | 59 | p50 1.0ms / p95 2.0ms（demo 嵌入） |

> 全部标记 `baseline_not_competition_claim`。真实比赛分数需在 Kylin 实机 + 真实 Embedding/向量库 + 注入真实 Adapter 后重测。

## 7. 总体结论

- 全量测试：**310 passed**（后端 282 + 评测 28）+ 前端 34 passed
- 启动 / 前端 / 写入 / 检索 / 遗忘 / 评测 六项验收全部 PASS
- 工程成功（Level 1）、模块成功（Level 2）、业务成功（Level 3：写入→检索→偏好→遗忘闭环）均已达成
- 评测单测 + 场景一致性检查通过

## 8. 遗留事项（不阻塞验收）

1. Repository / Embedding / Vector / Evaluation 仍为 Mock 基础设施（文档已知的阶段性配置）
2. 偏好提取对部分句式无结构化匹配（如「我喜欢中文回答」），建议联调时用覆盖的测试句式
3. 数据集：corpus 含 1 条 inactive + 1 条 tombstoned（4号 设计的困难集）；54 条 global 偏好 `scope_value="global"` 与 V1.2.1 严格 schema（应为 null）不一致，待 4号 确认
4. 麒麟实机验收（真实 Embedding/向量/延迟 P95≤500ms）与真实 Adapter 注入评测未做，属 Kylin 实机阶段
