# Retrieval Dataset Scripts（V0.6）

面向 **知识检索 Dev 集** 的可复现整改工具。`validation` / `final_test` 冻结不动。

## 背景

V0.5 扩样把约 30 个主题复制成 ~820 条近重复语料，并在正文写入「条目 N」。  
Exact `memory_id` Recall@K 因此被人为压到 ~20%，而主题级召回约 95%。

V0.6 目标：

- Corpus：**一主题一条** canonical MemoryRecord（约 80～120 条 + 特殊记忆）
- Queries：保留多种问法，gold 指向同一 `memory_id`
- 正文删除「条目 N」；序号仅留在 metadata
- 产出 multi-gold 人工复核清单
- no-answer 样本标记 `expected.is_no_answer=true`

## 文件

| 脚本 | 作用 |
|------|------|
| `deduplicate_topics.py` | 主题去重、清「条目 N」、remap Dev qrels、写 review |
| `validate_qrels.py` | 校验 gold∈corpus、无条目污染、无重复标题 |
| `expand_unique_to_820.py` | 补齐语料/问法到 ≥820：主题唯一、无条目N、无假多意图 |
| `_common.py` | 共享清洗 / IO 工具 |

## 复现步骤

```bash
# 1) dry-run 看报告
python scripts/dataset/deduplicate_topics.py

# 2) 写入 evaluation/dataset/
python scripts/dataset/deduplicate_topics.py --apply

# 3) 校验
python scripts/dataset/validate_qrels.py
python -m evaluation.check_freeze

# 4) multi-gold 决策 + 问法改写
python scripts/dataset/finalize_retrieval_dev.py --apply

# 5) 补齐到 820（主题唯一扩样，避免 V0.5 近重复陷阱）
python scripts/dataset/expand_unique_to_820.py --apply --target 820
```

## 参数与约定

| 项 | 值 |
|----|----|
| 随机种子（rebuild） | `42`（`--seed`） |
| release | `V0.6-retrieval-dedupe` |
| batch tag | `v0.6_dedupe` |
| 主题键 | 规范化 title（去「条目 N」「补充说明」） |
| canonical 选择 | 优先冻结集引用的 `memory_id`，否则最小 `mem_kb_*` |
| 正式主指标 | 仍为 exact `memory_id` Recall@K |
| 辅助字段 | `canonical_topic_id` / `expected.gold_topic_ids` |

## 输出产物

应用后：

- `evaluation/dataset/knowledge_corpus.jsonl` — 去重后语料
- `evaluation/dataset/retrieval_queries.jsonl` — Dev gold 已 remap
- `evaluation/dataset/archive/v0.5_pre_dedupe/` — 整改前备份（仅首次）
- `evaluation/dataset/reviews/v0.6_remediation_report.json`
- `evaluation/dataset/reviews/v0.6_id_to_canonical.json`
- `evaluation/dataset/reviews/multi_gold_review.csv` — **需人工填写**

## 人工待办

1. 打开 `reviews/multi_gold_review.csv`，对每条填写 `human_decision`
2. 不要自动批量改 formal Recall 为 topic Recall
3. 其它任务（preference/conflict/…）的 820 扩样不在本轮范围
