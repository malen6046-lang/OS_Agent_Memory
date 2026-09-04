# Multi-gold 复核结果（V0.6 finalize）

已落地决策见同目录 `multi_gold_review.csv`。

| 决策 | 含义 | 数量 |
|------|------|------|
| `keep_both` | 真多意图，保留双 gold | 16 |
| `keep_first` | 假多意图扩样，只留第一 gold 并重写问法 | 61（已应用） |

人工 curated / hard-p3 / cross_user 样本的原始问法已从 V0.5 备份恢复，未再被自动改写。
