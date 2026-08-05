# -*- coding: utf-8 -*-
"""Run all evaluation tasks; write txt snapshot + evaluation_report.md + result.csv."""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path
from pprint import pformat, pprint
from typing import Any

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from evaluation.conflict_eval import run_conflict_eval
from evaluation.forget_eval import run_forget_eval
from evaluation.latency_eval import run_latency_eval
from evaluation.preference_eval import run_preference_eval
from evaluation.retrieval_eval import run_retrieval_eval
from evaluation.security_eval import run_security_eval

TASK_RUNNERS = {
    "preference": run_preference_eval,
    "retrieval": run_retrieval_eval,
    "conflict": run_conflict_eval,
    "forget": run_forget_eval,
    "security": run_security_eval,
    "latency": run_latency_eval,
}

# Flattened CSV columns: task, metric, value, split, status
PRIMARY_METRICS = {
    "preference": [
        "exact_match_accuracy",
        "micro_f1",
        "macro_f1",
        "ephemeral_false_positive_rate",
    ],
    "retrieval": [
        "recall_at_k.1",
        "recall_at_k.3",
        "recall_at_k.5",
        "recall_at_k.10",
        "mrr",
        "latency_ms.p95",
    ],
    "conflict": [
        "joint_accuracy",
        "relation_accuracy",
        "strategy_accuracy",
        "auto_apply_rate",
        "predicted_manual_review_rate",
    ],
    "forget": [
        "preview_precision",
        "preview_recall",
        "execute_success_rate",
        "false_delete_count",
    ],
    "security": [
        "block_accuracy",
        "entity_type_accuracy",
        "joint_accuracy",
    ],
    "latency": [
        "p50_ms",
        "p95_ms",
        "mean_ms",
    ],
}


def _dig(obj: Any, path: str) -> Any:
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def write_result_csv(path: Path, summary: dict[str, Any]) -> None:
    rows: list[dict[str, Any]] = []
    split = summary.get("split", "")
    for task, report in summary.get("tasks", {}).items():
        status = report.get("status", "")
        n = report.get("n", "")
        for metric in PRIMARY_METRICS.get(task, []):
            val = _dig(report, metric)
            if val is None and "." not in metric:
                val = report.get(metric)
            rows.append(
                {
                    "task": task,
                    "metric": metric,
                    "value": val if val is not None else "",
                    "n": n,
                    "split": split,
                    "status": status,
                }
            )
        # also dump any top-level numeric extras not listed
    path.write_text("", encoding="utf-8")  # ensure file
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["task", "metric", "value", "n", "split", "status"]
        )
        writer.writeheader()
        writer.writerows(rows)


def write_evaluation_report_md(path: Path, summary: dict[str, Any]) -> None:
    rt = summary.get("runtime", {})
    lines = [
        "# OS Agent Memory 评测报告（Dataset V0.1）",
        "",
        f"- **生成时间**：{summary.get('started_at', '')}",
        f"- **数据划分**：`{summary.get('split', '')}`",
        f"- **运行时**：python_version={rt.get('python_version', '')}"
        f"（要求 {rt.get('requires', 'CPython 3.12')}）",
        f"- **解释器标识**：`{rt.get('executable', 'python3.12')}`"
        "（不含本机绝对路径，符合 V1.2.2）",
        "",
        "> **声明**：本报告为离线 baseline / 联调结果，"
        "**不得**直接表述为比赛红线已达标。"
        "麒麟实机 Embedding/向量库延迟与真实 ForgetService 需另行验收。",
        "",
        "## 1. 总览",
        "",
        "| 任务 | n | 主结果摘要 | status |",
        "|------|---|------------|--------|",
    ]
    for task, report in summary.get("tasks", {}).items():
        n = report.get("n", "")
        status = report.get("status", "")
        if task == "preference":
            summary_s = f"exact={report.get('exact_match_accuracy')}, macro_f1={report.get('macro_f1')}"
        elif task == "retrieval":
            r = report.get("recall_at_k") or {}
            summary_s = f"R@5={r.get('5')}, MRR={report.get('mrr')}"
        elif task == "conflict":
            summary_s = f"joint={report.get('joint_accuracy')}"
        elif task == "forget":
            summary_s = (
                f"P={report.get('preview_precision')}, "
                f"R={report.get('preview_recall')}, "
                f"exec={report.get('execute_success_rate')}"
            )
        elif task == "security":
            summary_s = (
                f"block={report.get('block_accuracy')}, "
                f"entity={report.get('entity_type_accuracy')}"
            )
        elif task == "latency":
            summary_s = f"p95={report.get('p95_ms')}ms (demo)"
        else:
            summary_s = str(report)[:80]
        lines.append(f"| {task} | {n} | {summary_s} | `{status}` |")

    lines.extend(
        [
            "",
            "## 2. 分任务明细",
            "",
        ]
    )
    for task, report in summary.get("tasks", {}).items():
        lines.append(f"### {task}")
        lines.append("")
        lines.append("```")
        lines.append(pformat(report, width=100, sort_dicts=False))
        lines.append("```")
        lines.append("")

    lines.extend(
        [
            "## 3. 赛题硬目标对照（仅作差距提示）",
            "",
            "| 指标 | 目标 | 本报告 |",
            "|------|------|--------|",
        ]
    )
    pref = summary.get("tasks", {}).get("preference", {})
    ret = summary.get("tasks", {}).get("retrieval", {})
    conf = summary.get("tasks", {}).get("conflict", {})
    lat = summary.get("tasks", {}).get("latency", {})
    r5 = (ret.get("recall_at_k") or {}).get("5")
    lines.append(
        f"| 偏好 exact-match | ≥85% | {pref.get('exact_match_accuracy', 'N/A')} |"
    )
    lines.append(f"| 检索 Recall（常用 R@5 参考） | ≥85% | {r5 if r5 is not None else 'N/A'} |")
    lines.append(
        f"| 冲突正确率（joint） | ≥88% | {conf.get('joint_accuracy', 'N/A')} |"
    )
    lines.append(
        f"| 检索延迟 P95 | ≤500ms（麒麟实机） | demo p95={lat.get('p95_ms', 'N/A')}ms |"
    )
    lines.extend(
        [
            "",
            "## 4. 附件",
            "",
            "- 机器可读明细：同目录 `result.csv`",
            "- 原始快照：`v0.1_<split>.txt`",
            "- 数据规范：`evaluation/dataset/README.md`",
            "- 复核记录：`evaluation/复核记录.md`",
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--split", default="dev", choices=["dev", "held_out", "all"])
    p.add_argument("--tasks", default="preference,retrieval,conflict,forget,security,latency")
    p.add_argument("--out", default=None, help="optional raw txt snapshot path")
    args = p.parse_args()

    reports_dir = Path(__file__).resolve().parent / "reports"
    if reports_dir.exists() and not reports_dir.is_dir():
        raise SystemExit(
            f"evaluation/reports must be a directory, found file: {reports_dir}"
        )
    reports_dir.mkdir(parents=True, exist_ok=True)

    py = sys.version_info
    if py[:2] != (3, 12):
        print(
            f"[warn] require CPython 3.12.x; current {sys.version.split()[0]}",
            file=sys.stderr,
        )

    # V1.2.2: do not leak personal absolute paths into deliverable reports.
    summary: dict[str, Any] = {
        "schema_version": "0.1.0",
        "split": args.split,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "runtime": {
            "language": "python",
            "requires": "CPython >=3.12,<3.13",
            "python_version": sys.version.split()[0],
            "executable": f"python{py.major}.{py.minor}",
        },
        "disclaimer": (
            "Baseline offline scores only. Not competition-target claims. "
            "Kylin Real latency/embedding must be measured separately."
        ),
        "tasks": {},
    }
    for name in [t.strip() for t in args.tasks.split(",") if t.strip()]:
        runner = TASK_RUNNERS.get(name)
        if not runner:
            print(f"[skip] {name}", file=sys.stderr)
            continue
        report = runner(split=args.split)
        summary["tasks"][name] = report
        print(f"== {name} ==")
        pprint(report)

    txt_out = Path(args.out) if args.out else reports_dir / f"v0.1_{args.split}.txt"
    txt_out.write_text(pformat(summary, width=100, sort_dicts=False), encoding="utf-8")

    md_out = reports_dir / "evaluation_report.md"
    csv_out = reports_dir / "result.csv"
    write_evaluation_report_md(md_out, summary)
    write_result_csv(csv_out, summary)

    print(f"\nreport written: {txt_out}")
    print(f"markdown written: {md_out}")
    print(f"csv written: {csv_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
