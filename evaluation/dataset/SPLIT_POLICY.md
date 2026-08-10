# 数据划分与冻结策略（dev / validation / final_test）

依据：`4号下周安排建议.docx`

## 三分法

| 划分 | 用途 | 谁可以看答案 | 本轮能否改 GT |
|------|------|--------------|----------------|
| `dev` | 开发调试 | 1、2 号可以 | 可以（小修需记日志） |
| `validation` | 每轮集成后统一评测 | 评测可见；勿按题刷分 | **冻结** |
| `final_test` | 最终盲测 | **1、2 号不得提前看** | **冻结** |

语料 `knowledge_corpus.jsonl` 无 `split`，三份共用。

## 怎么做（操作步骤）

1. **一次性迁移**（把旧 `held_out` 拆成 validation / final_test，并写冻结清单）：

```bash
python scripts/freeze_dataset_splits.py
```

2. **日常开发评测**（1、2 号）：

```bash
python -m evaluation.run_all --split dev
```

3. **每轮集成回归**（用冻结的 validation）：

```bash
python -m evaluation.run_all --split validation
python -m evaluation.check_freeze
```

4. **最终盲测**（赛前/验收，由 4 号或负责人跑）：

```bash
python -m evaluation.run_all --split final_test
```

5. **本轮优化期间**：禁止改 `validation` / `final_test` 的答案与题目。  
   若必须修正标注错误：先开 issue → 负责人同意 → 改完重跑 `freeze_dataset_splits.py` 仅刷新 manifest（或手工更新 `freeze_manifest.json`）→ 全员知晓「本轮基线重置」。

## 冻结文件

- `freeze_manifest.json`：冻结的 case_id 列表 + content SHA-256  
- 校验：`python -m evaluation.check_freeze`

## 兼容

旧参数 `--split held_out` 仍可用，加载时等同 `validation`（过渡期）。新代码请写 `validation` / `final_test`。
