# OS Agent Memory 评测报告（Dataset V0.1）

- **生成时间**：2026-08-03T14:45:51.662656+00:00
- **数据划分**：`all`
- **运行时**：3.12.7（要求 CPython >=3.12,<3.13）
- **可执行文件**：`D:\software\anaconda\python.exe`

> **声明**：本报告为离线 baseline / 联调结果，**不得**直接表述为比赛红线已达标。麒麟实机 Embedding/向量库延迟与真实 ForgetService 需另行验收。

## 1. 总览

| 任务 | n | 主结果摘要 | status |
|------|---|------------|--------|
| preference | 50 | exact=0.18, macro_f1=0.11111111111111112 | `baseline_not_competition_claim` |
| retrieval | 50 | R@5=0.42, MRR=0.30752380952380953 | `baseline_not_competition_claim` |
| conflict | 20 | joint=0.1 | `baseline_not_competition_claim` |
| forget | 20 | P=0.7083333333333333, R=0.95, exec=0.45 | `baseline_not_competition_claim` |
| security | 10 | block=1.0, entity=0.9 | `baseline_not_competition_claim` |
| latency | 50 | p95=1.5ms (demo) | `baseline_not_competition_claim` |

## 2. 分任务明细

### preference

```
{'task': 'preference',
 'split': 'all',
 'n': 50,
 'exact_match_accuracy': 0.18,
 'match_fields': ['preference_key',
                  'value',
                  'category',
                  'scope',
                  'scope_value',
                  'polarity',
                  'status'],
 'micro_precision': 0.46153846153846156,
 'micro_recall': 0.1276595744680851,
 'micro_f1': 0.2,
 'macro_f1': 0.11111111111111112,
 'sample_macro_f1': 0.18,
 'ephemeral_false_positive_rate': 0.0,
 'note': 'baseline_extract only; inject PreferenceService via extract_fn for real scores',
 'extractor': 'baseline_extract',
 'status': 'baseline_not_competition_claim'}
```

### retrieval

```
{'task': 'retrieval',
 'split': 'all',
 'n': 50,
 'corpus_size': 50,
 'recall_at_k': {'1': 0.22, '3': 0.36, '5': 0.42, '10': 0.52},
 'hit_at_k': {'1': 0.22, '3': 0.36, '5': 0.42, '10': 0.52},
 'mrr': 0.30752380952380953,
 'latency_ms': {'p50': 1.0, 'p95': 1.0, 'mean': 0.742},
 'cross_user_leak_cases': 0,
 'id_hash': 'sha256',
 'backend': 'HybridRetriever+BM25+MemoryVectorStore+DemoEmbedding(sha256)',
 'note': 'DemoEmbedding latency is NOT Kylin ≤500ms evidence',
 'status': 'baseline_not_competition_claim'}
```

### conflict

```
{'task': 'conflict',
 'split': 'all',
 'n': 20,
 'primary_metric': 'joint_accuracy',
 'joint_accuracy': 0.1,
 'relation_accuracy': 0.25,
 'strategy_accuracy': 0.1,
 'predicted_manual_review_rate': 0.55,
 'gold_manual_review_rate': 0.1,
 'auto_apply_rate': 0.44999999999999996,
 'confusion_matrix_relation': {'duplicate->duplicate': 0,
                               'duplicate->support': 0,
                               'duplicate->extend': 0,
                               'duplicate->replace': 3,
                               'duplicate->contradict': 0,
                               'duplicate->unrelated': 0,
                               'support->duplicate': 0,
                               'support->support': 0,
                               'support->extend': 0,
                               'support->replace': 2,
                               'support->contradict': 0,
                               'support->unrelated': 0,
                               'extend->duplicate': 0,
                               'extend->support': 0,
                               'extend->extend': 0,
                               'extend->replace': 0,
                               'extend->contradict': 2,
                               'extend->unrelated': 1,
                               'replace->duplicate': 0,
                               'replace->support': 0,
                               'replace->extend': 0,
                               'replace->replace': 0,
                               'replace->contradict': 4,
                               'replace->unrelated': 1,
                               'contradict->duplicate': 0,
                               'contradict->support': 0,
                               'contradict->extend': 0,
                               'contradict->replace': 0,
                               'contradict->contradict': 4,
                               'contradict->unrelated': 1,
                               'unrelated->duplicate': 0,
                               'unrelated->support': 0,
                               'unrelated->extend': 0,
                               'unrelated->replace': 0,
                               'unrelated->contradict': 1,
                               'unrelated->unrelated': 1},
 'classifier': 'KnowledgeService.classify_conflict',
 'status': 'baseline_not_competition_claim'}
```

### forget

```
{'task': 'forget',
 'split': 'all',
 'n': 20,
 'preview_precision': 0.7083333333333333,
 'preview_recall': 0.95,
 'false_delete_count': 10,
 'execute_success_rate': 0.45,
 'residual_or_false_delete_fail_rate': 0.5,
 'confirmation_token_scheme': 'sha256(case_id:user:instruction)',
 'drop_collection_forbidden': True,
 'resolver': 'baseline_preview',
 'status': 'baseline_not_competition_claim',
 'note': 'execute is in-memory tombstone simulation until ForgetService Real is wired'}
```

### security

```
{'task': 'security',
 'split': 'all',
 'n': 10,
 'block_accuracy': 1.0,
 'entity_type_accuracy': 0.9,
 'joint_accuracy': 0.9,
 'detector': 'baseline_detect',
 'status': 'baseline_not_competition_claim',
 'note': 'n=10 small; baseline regex co-located — do not claim production readiness'}
```

### latency

```
{'task': 'latency',
 'split': 'all',
 'n': 50,
 'p50_ms': 1.0,
 'p95_ms': 1.5,
 'mean_ms': 0.8759999999999999,
 'budget_ms': 500,
 'p95_within_budget_demo_only': True,
 'status': 'baseline_not_competition_claim',
 'note': 'Must re-measure on Kylin Real embedding/vector for ≤500ms claim'}
```

## 3. 赛题硬目标对照（仅作差距提示）

| 指标 | 目标 | 本报告 |
|------|------|--------|
| 偏好 exact-match | ≥85% | 0.18 |
| 检索 Recall（常用 R@5 参考） | ≥85% | 0.42 |
| 冲突正确率（joint） | ≥88% | 0.1 |
| 检索延迟 P95 | ≤500ms（麒麟实机） | demo p95=1.5ms |

## 4. 附件

- 机器可读明细：同目录 `result.csv`
- 原始快照：`v0.1_<split>.txt`
- 数据规范：`evaluation/dataset/README.md`
- 复核记录：`evaluation/复核记录.md`
