# -*- coding: utf-8 -*-
"""Run all evaluation datasets. Data is inside each *_eval.py (CASES/CORPUS)."""
from __future__ import annotations

import argparse
from pprint import pformat, pprint
import sys
from datetime import datetime, timezone
from pathlib import Path

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


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--split", default="dev", choices=["dev", "held_out", "all"])
    p.add_argument("--tasks", default="preference,retrieval,conflict,forget,security,latency")
    p.add_argument("--out", default=None)
    args = p.parse_args()

    py = sys.version_info
    if py[:2] != (3, 12):
        print(
            f"[warn] V1.2.1/V1.2.2 require CPython 3.12.x; current is {sys.version.split()[0]}",
            file=sys.stderr,
        )
    summary = {
        "schema_version": "0.1.0",
        "split": args.split,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "runtime": {
            "language": "python",
            "requires": "CPython >=3.12,<3.13",
            "python_version": sys.version.split()[0],
            "executable": sys.executable,
        },
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

    out = Path(args.out) if args.out else Path(__file__).resolve().parent / "reports" / f"v0.1_{args.split}.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(pformat(summary, width=100, sort_dicts=False), encoding="utf-8")
    print(f"\nreport written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
