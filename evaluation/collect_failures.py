# -*- coding: utf-8 -*-
"""Collect per-case eval failures into failure attribution CSV/MD (安排第四项).

Usage:
  python -m evaluation.collect_failures --split dev
  python -m evaluation.collect_failures --split validation

Does not claim competition scores; baseline / injected services both OK.
Suggested ``reason_code`` is heuristic — 1/2号确认后可改。
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path
from typing import Any

from evaluation.forget_eval import baseline_preview, simulate_execute
from evaluation.loaders import load_cases, load_corpus
from evaluation.metrics import preference_set_exact_match, preference_signature, recall_at_k
from evaluation.preference_eval import baseline_extract
from evaluation.retrieval_eval import build_retriever
from evaluation.security_eval import baseline_detect
from modules.knowledge_retrieval.knowledge_service import KnowledgeService

ROOT = Path(__file__).resolve().parent
OUT_CSV = ROOT / "reports" / "failure_attribution.csv"
OUT_MD = ROOT / "失败案例归因表.md"

# 标准原因码（可扩展；填表时优先用这些）
REASON_CODES = [
    "同义表达",
    "隐式偏好",
    "临时指令误记",
    "多gold部分命中",
    "无答案误命中",
    "用户隔离",
    "冲突relation误判",
    "冲突strategy误判",
    "forget欠删",
    "forget过删",
    "security实体错",
    "security漏拦",
    "security误拦",
    "基线能力不足",
    "其他",
]


def _pref_failures(split: str) -> list[dict[str, Any]]:
    rows = []
    for case in load_cases("preference", split=split):
        preds = baseline_extract(case)
        golds = case.get("expected", {}).get("preferences", [])
        ok = preference_set_exact_match(preds, golds)
        if ok:
            continue
        ephemeral = bool(case.get("expected", {}).get("is_ephemeral_instruction"))
        reason = "临时指令误记" if ephemeral and preds else "隐式偏好"
        if not ephemeral and not preds and golds:
            reason = "隐式偏好"
        elif not ephemeral and preds and golds:
            reason = "基线能力不足"
        rows.append(
            {
                "case_id": case["case_id"],
                "task": "preference",
                "metric": "exact_match",
                "split": split,
                "system_result": json.dumps(
                    [preference_signature(p) for p in preds], ensure_ascii=False
                ),
                "gt": json.dumps(
                    [preference_signature(g) for g in golds], ensure_ascii=False
                ),
                "reason_code": reason,
                "reason_note": "",
                "owner": "1/2号",
                "status": "open",
                "run_date": str(date.today()),
            }
        )
    return rows


def _ret_failures(split: str) -> list[dict[str, Any]]:
    rows = []
    corpus = load_corpus()
    hr = build_retriever(corpus)
    for q in load_cases("retrieval", split=split):
        resp = hr.search({"query": q["query"], "user_id": q.get("user_id"), "top_k": 10})
        ranked = [r["memory_id"] for r in resp.get("results", [])]
        gold = q.get("expected", {}).get("gold_memory_ids", []) or []
        r5 = recall_at_k(ranked, gold, 5)
        if gold:
            if r5 >= 1.0:
                continue
        else:
            if not ranked:
                continue
        if not gold and ranked:
            reason = "无答案误命中"
            sys_res = f"ranked={ranked[:5]}"
            gt = "[]"
        elif gold and r5 <= 0:
            reason = "同义表达"
            sys_res = f"未命中@5; top={ranked[:5]}"
            gt = ",".join(gold)
        else:
            reason = "多gold部分命中"
            sys_res = f"recall@5={r5:.2f}; top={ranked[:5]}"
            gt = ",".join(gold)
        # user leak
        id2user = {m["memory_id"]: m.get("user_id") for m in corpus}
        uid = q.get("user_id")
        if any(
            id2user.get(mid) not in (None, uid, "usr_corpus_shared") for mid in ranked[:10]
        ):
            reason = "用户隔离"
        rows.append(
            {
                "case_id": q["case_id"],
                "task": "retrieval",
                "metric": "recall@5",
                "split": split,
                "system_result": sys_res,
                "gt": gt,
                "reason_code": reason,
                "reason_note": q.get("query", "")[:80],
                "owner": "1/2号",
                "status": "open",
                "run_date": str(date.today()),
            }
        )
    return rows


def _conf_failures(split: str) -> list[dict[str, Any]]:
    rows = []

    class _NullEmb:
        def health(self, deep: bool = False) -> dict:
            return {"status": "stopped"}

        def encode(self, texts: list[str]) -> dict:
            return {"vectors": [], "dimension": 0, "errors": None}

    class _NullVS:
        def query(self, request: dict) -> list:
            return []

    ks = KnowledgeService(_NullEmb(), _NullVS(), bm25=None)
    for case in load_cases("conflict", split=split):
        pred = ks.classify_conflict(case["old"], case["new"])
        exp = case["expected"]
        pr, er = pred.get("relation"), exp.get("relation")
        ps, es = pred.get("strategy"), exp.get("strategy")
        if pr == er and ps == es:
            continue
        reason = "冲突relation误判" if pr != er else "冲突strategy误判"
        rows.append(
            {
                "case_id": case["case_id"],
                "task": "conflict",
                "metric": "joint",
                "split": split,
                "system_result": f"relation={pr}, strategy={ps}",
                "gt": f"relation={er}, strategy={es}",
                "reason_code": reason,
                "reason_note": "",
                "owner": "1/2号",
                "status": "open",
                "run_date": str(date.today()),
            }
        )
    return rows


def _forg_failures(split: str) -> list[dict[str, Any]]:
    rows = []
    for case in load_cases("forget", split=split):
        preview = baseline_preview(case)
        gold_del = set(case["expected_preview"].get("should_delete_ids", []))
        gold_keep = set(case["expected_preview"].get("should_keep_ids", []))
        pred_del = set(preview.get("should_delete_ids", []))
        under = gold_del - pred_del
        over = pred_del & gold_keep
        exe = simulate_execute(case, preview)
        preview_ok = pred_del == gold_del
        exe_ok = bool(exe.get("ok")) and not exe.get("false_delete_ids")
        if preview_ok and exe_ok:
            continue
        if over:
            reason = "forget过删"
        elif under:
            reason = "forget欠删"
        else:
            reason = "基线能力不足"
        rows.append(
            {
                "case_id": case["case_id"],
                "task": "forget",
                "metric": "preview+execute",
                "split": split,
                "system_result": f"del={sorted(pred_del)}; exe_ok={exe.get('ok')}",
                "gt": f"del={sorted(gold_del)}; keep={sorted(gold_keep)}",
                "reason_code": reason,
                "reason_note": (case.get("instruction") or "")[:80],
                "owner": "1/2号",
                "status": "open",
                "run_date": str(date.today()),
            }
        )
    return rows


def _sec_failures(split: str) -> list[dict[str, Any]]:
    rows = []
    for case in load_cases("security", split=split):
        pred = baseline_detect(case["input_text"])
        exp = case["expected"]
        block_ok = pred.get("blocked_or_masked") == exp.get("blocked_or_masked")
        if exp.get("blocked_or_masked"):
            block_ok = block_ok and pred.get("error_code") == exp.get("error_code")
        entity_ok = pred.get("entity_type") == exp.get("entity_type")
        if block_ok and entity_ok:
            continue
        if exp.get("blocked_or_masked") and not pred.get("blocked_or_masked"):
            reason = "security漏拦"
        elif (not exp.get("blocked_or_masked")) and pred.get("blocked_or_masked"):
            reason = "security误拦"
        else:
            reason = "security实体错"
        rows.append(
            {
                "case_id": case["case_id"],
                "task": "security",
                "metric": "joint",
                "split": split,
                "system_result": json.dumps(pred, ensure_ascii=False),
                "gt": json.dumps(exp, ensure_ascii=False),
                "reason_code": reason,
                "reason_note": (case.get("input_text") or "")[:60],
                "owner": "1/2号",
                "status": "open",
                "run_date": str(date.today()),
            }
        )
    return rows


FIELDS = [
    "case_id",
    "task",
    "metric",
    "split",
    "system_result",
    "gt",
    "reason_code",
    "reason_note",
    "owner",
    "status",
    "run_date",
]


def collect(split: str) -> list[dict[str, Any]]:
    all_rows: list[dict[str, Any]] = []
    all_rows.extend(_pref_failures(split))
    all_rows.extend(_ret_failures(split))
    all_rows.extend(_conf_failures(split))
    all_rows.extend(_forg_failures(split))
    all_rows.extend(_sec_failures(split))
    return all_rows


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in FIELDS})


def write_md(rows: list[dict[str, Any]], split: str, path: Path) -> None:
    from collections import Counter

    by_reason = Counter(r["reason_code"] for r in rows)
    by_task = Counter(r["task"] for r in rows)
    lines = [
        "# 失败案例归因表",
        "",
        f"**日期**：{date.today()}  ",
        f"**划分**：`{split}`  ",
        "**依据**：`4号下周安排建议.docx` 第四项  ",
        "**生成**：`python -m evaluation.collect_failures --split <split>`  ",
        f"**失败条数**：{len(rows)}",
        "",
        "> 表中 `reason_code` 为启发式初标，**须 1/2 号确认/改写**后才可作为优化依据。  ",
        "> 本轮请主要看 `dev` 归因；`validation` 只做集成对照，勿按 validation 刷参。",
        "",
        "## 原因码词表",
        "",
        "| reason_code | 含义 |",
        "|-------------|------|",
    ]
    meaning = {
        "同义表达": "问法/表述与语料不一致，语义相近未召回",
        "隐式偏好": "偏好未直说，需从行为推断",
        "临时指令误记": "临时指令被当成长期偏好",
        "多gold部分命中": "多个金标只命中部分",
        "无答案误命中": "应无答案却返回结果",
        "用户隔离": "检索到其他用户私有记忆",
        "冲突relation误判": "冲突关系类别错误",
        "冲突strategy误判": "保留/合并策略错误",
        "forget欠删": "该删的没删",
        "forget过删": "不该删的删了",
        "security实体错": "拦截对了但实体类型错",
        "security漏拦": "该拦没拦",
        "security误拦": "不该拦却拦",
        "基线能力不足": "规则/demo 基线本身覆盖不到",
        "其他": "需手写说明",
    }
    for code in REASON_CODES:
        lines.append(f"| `{code}` | {meaning.get(code, '')} |")

    lines += [
        "",
        "## 汇总",
        "",
        "### 按任务",
        "",
        "| task | 失败数 |",
        "|------|--------|",
    ]
    for t, n in sorted(by_task.items()):
        lines.append(f"| {t} | {n} |")
    lines += [
        "",
        "### 按原因",
        "",
        "| reason_code | 失败数 |",
        "|-------------|--------|",
    ]
    for r, n in by_reason.most_common():
        lines.append(f"| {r} | {n} |")

    # show top failures per task (cap)
    lines += [
        "",
        "## 明细（节选，完整见 CSV）",
        "",
        "| ID | 指标 | 系统结果 | GT | 原因 |",
        "|----|------|----------|----|------|",
    ]
    # match doc example columns; show up to 40
    for r in rows[:40]:
        sys = str(r["system_result"]).replace("|", "/")[:60]
        gt = str(r["gt"]).replace("|", "/")[:40]
        lines.append(
            f"| {r['case_id']} | {r['metric']} | {sys} | {gt} | {r['reason_code']} |"
        )
    if len(rows) > 40:
        lines.append(f"| … | … | 其余 {len(rows)-40} 条见 CSV | … | … |")

    lines += [
        "",
        f"完整表：[`reports/failure_attribution.csv`](./reports/failure_attribution.csv)",
        "",
        "## 使用方式（给 1/2 号）",
        "",
        "1. 注入真实服务后重跑：`python -m evaluation.collect_failures --split dev`",
        "2. 打开 CSV，把 `reason_code` / `reason_note` 改成真实归因",
        "3. 每周选**数量最多的原因码**作为本周最大错误类型优先修",
        "4. 修完把对应行 `status` 改为 `fixed`，再跑 validation 回归",
        "",
        "## 下一步",
        "",
        "安排第五项：5 个精品 E2E 场景完全跑通。",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser(description="Collect failure attribution rows")
    p.add_argument(
        "--split",
        default="dev",
        choices=["dev", "validation", "final_test", "held_out", "all"],
    )
    p.add_argument("--csv", type=Path, default=OUT_CSV)
    p.add_argument("--md", type=Path, default=OUT_MD)
    args = p.parse_args()
    rows = collect(args.split)
    write_csv(rows, args.csv)
    write_md(rows, args.split, args.md)
    print(f"failures={len(rows)}")
    print(f"csv -> {args.csv}")
    print(f"md  -> {args.md}")


if __name__ == "__main__":
    main()
