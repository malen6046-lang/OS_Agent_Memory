# evaluation/（Dataset V0.1）

## 结构

```text
evaluation/
├── dataset/                 # 数据与脚本分离
│   ├── preference.jsonl
│   ├── knowledge_corpus.jsonl
│   ├── retrieval_queries.jsonl
│   ├── conflict.jsonl
│   ├── forget.jsonl
│   └── security.jsonl
├── loaders.py / metrics.py
├── *_eval.py / run_all.py   # 评测逻辑（读 dataset/）
└── reports/                 # 必须是目录
```

## 运行（CPython 3.12）

```bash
cd OS_Agent_Memory-evaluation-dataset
python3.12 -m evaluation.run_all --split dev
python3.12 -m evaluation.run_all --split validation
python3.12 -m evaluation.check_freeze
python3.12 -m pytest tests/unit/evaluation -q
```

数据三分法与冻结：`dataset/SPLIT_POLICY.md`。  
Ground Truth 检查：`python -m evaluation.check_ground_truth` → `GT检查报告.md`。  
失败归因：`python -m evaluation.collect_failures --split dev` → `失败案例归因表.md` + `reports/failure_attribution.csv`。  
E2E 清单：`python -m evaluation.check_e2e_ready` → `E2E跑通清单.md`。

报告写入：
- `evaluation/reports/v0.1_<split>.txt`（原始快照）
- `evaluation/reports/evaluation_report.md`（正式报告）
- `evaluation/reports/result.csv`（指标表）

数据规范：`dataset/README.md`；复核：`复核记录.md`；端到端场景：`scenarios/`。  
联调注入：`联调注入说明.md`；第二人抽查：`第二人抽查清单.md`。  
单测：`python -m pytest tests/unit/evaluation -q`。  
当前分数为 **baseline**，`status=baseline_not_competition_claim`，不可写成已达红线。

## 8_3 关键点摘要

- reports 目录 / `__init__.py` 命名
- 数据外置 JSONL
- 偏好完整字段 exact-match + micro/macro F1；临时指令 gold preferences=[]
- Recall@K 真公式；稳定 SHA-256 id/embedding
- 冲突 joint 主指标 + auto_apply_rate + 完整混淆矩阵
- 遗忘 preview+内存 execute/残留；token 由 case 派生不抄答案
- 安全核对 entity_type；标明小样本/baseline
