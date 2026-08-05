# OS Agent Memory 评测报告（Dataset V0.1）

- **生成时间**：2026-08-05T06:25:56.021607+00:00
- **数据划分**：`dev`
- **运行时**：python_version=3.12.7（要求 CPython >=3.12,<3.13）
- **解释器标识**：`python3.12`（不含本机绝对路径，符合 V1.2.2）

> **声明**：本报告为离线 baseline / 联调结果，**不得**直接表述为比赛红线已达标。麒麟实机 Embedding/向量库延迟与真实 ForgetService 需另行验收。

## 1. 总览

| 任务 | n | 主结果摘要 | status |
|------|---|------------|--------|
| preference | 42 | exact=0.2619047619047619, macro_f1=0.14774774774774774 | `baseline_not_competition_claim` |
| retrieval | 59 | R@5=0.4576271186440678, MRR=0.34731638418079097 | `baseline_not_competition_claim` |
| conflict | 17 | joint=0.11764705882352941 | `baseline_not_competition_claim` |
| forget | 17 | P=0.6568627450980392, R=0.9411764705882353, exec=0.35294117647058826 | `baseline_not_competition_claim` |
| security | 32 | block=0.84375, entity=0.8125 | `baseline_not_competition_claim` |
| latency | 59 | p95=6.8ms (demo) | `baseline_not_competition_claim` |

## 2. 分任务明细

### preference

```
{'task': 'preference',
 'split': 'dev',
 'n': 42,
 'exact_match_accuracy': 0.2619047619047619,
 'match_fields': ['preference_key',
                  'value',
                  'category',
                  'scope',
                  'scope_value',
                  'polarity',
                  'status'],
 'micro_precision': 0.5789473684210527,
 'micro_recall': 0.2558139534883721,
 'micro_f1': 0.3548387096774194,
 'macro_f1': 0.14774774774774774,
 'sample_macro_f1': 0.28968253968253965,
 'ephemeral_false_positive_rate': 0.0,
 'note': 'baseline_extract only; inject PreferenceService via extract_fn for real scores',
 'extractor': 'baseline_extract',
 'status': 'baseline_not_competition_claim'}
```

### retrieval

```
{'task': 'retrieval',
 'split': 'dev',
 'n': 59,
 'corpus_size': 60,
 'recall_at_k': {'1': 0.1864406779661017,
                 '3': 0.3559322033898305,
                 '5': 0.4576271186440678,
                 '10': 0.5084745762711864},
 'hit_at_k': {'1': 0.22033898305084745,
              '3': 0.423728813559322,
              '5': 0.5423728813559322,
              '10': 0.5932203389830508},
 'mrr': 0.34731638418079097,
 'latency_ms': {'p50': 0.9, 'p95': 5.9, 'mean': 1.6745762711864407},
 'cross_user_leak_cases': 0,
 'id_hash': 'sha256',
 'backend': 'HybridRetriever+BM25+MemoryVectorStore+DemoEmbedding(sha256)',
 'note': 'DemoEmbedding latency is NOT Kylin ≤500ms evidence',
 'status': 'baseline_not_competition_claim'}
```

### conflict

```
{'task': 'conflict',
 'split': 'dev',
 'n': 17,
 'primary_metric': 'joint_accuracy',
 'joint_accuracy': 0.11764705882352941,
 'relation_accuracy': 0.29411764705882354,
 'strategy_accuracy': 0.11764705882352941,
 'predicted_manual_review_rate': 0.5882352941176471,
 'gold_manual_review_rate': 0.058823529411764705,
 'auto_apply_rate': 0.4117647058823529,
 'confusion_matrix_relation': {'duplicate->duplicate': 0,
                               'duplicate->support': 0,
                               'duplicate->extend': 0,
                               'duplicate->replace': 2,
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
                               'extend->unrelated': 0,
                               'replace->duplicate': 0,
                               'replace->support': 0,
                               'replace->extend': 0,
                               'replace->replace': 0,
                               'replace->contradict': 3,
                               'replace->unrelated': 2,
                               'contradict->duplicate': 0,
                               'contradict->support': 0,
                               'contradict->extend': 0,
                               'contradict->replace': 0,
                               'contradict->contradict': 4,
                               'contradict->unrelated': 0,
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
 'split': 'dev',
 'n': 17,
 'preview_precision': 0.6568627450980392,
 'preview_recall': 0.9411764705882353,
 'false_delete_count': 10,
 'execute_success_rate': 0.35294117647058826,
 'residual_or_false_delete_fail_rate': 0.5882352941176471,
 'confirmation_token_scheme': 'sha256(case_id:user:instruction)',
 'drop_collection_forbidden': True,
 'resolver': 'baseline_preview',
 'status': 'baseline_not_competition_claim',
 'note': 'execute is in-memory tombstone simulation until ForgetService Real is wired'}
```

### security

```
{'task': 'security',
 'split': 'dev',
 'n': 32,
 'block_accuracy': 0.84375,
 'entity_type_accuracy': 0.8125,
 'joint_accuracy': 0.8125,
 'detector': 'baseline_detect',
 'status': 'baseline_not_competition_claim',
 'note': 'baseline regex co-located — do not claim production readiness; hard-suite expanded in P3'}
```

### latency

```
{'task': 'latency',
 'split': 'dev',
 'n': 59,
 'p50_ms': 0.0,
 'p95_ms': 6.8,
 'mean_ms': 1.535593220338983,
 'budget_ms': 500,
 'p95_within_budget_demo_only': True,
 'status': 'baseline_not_competition_claim',
 'note': 'Must re-measure on Kylin Real embedding/vector for ≤500ms claim'}
```

## 3. 赛题硬目标对照（仅作差距提示）

| 指标 | 目标 | 本报告 |
|------|------|--------|
| 偏好 exact-match | ≥85% | 0.2619047619047619 |
| 检索 Recall（常用 R@5 参考） | ≥85% | 0.4576271186440678 |
| 冲突正确率（joint） | ≥88% | 0.11764705882352941 |
| 检索延迟 P95 | ≤500ms（麒麟实机） | demo p95=6.8ms |

## 4. 附件

- 机器可读明细：同目录 `result.csv`
- 原始快照：`v0.1_<split>.txt`
- 数据规范：`evaluation/dataset/README.md`
- 复核记录：`evaluation/复核记录.md`
