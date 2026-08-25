# -*- coding: utf-8 -*-
"""Print scenario turn checklist and validate scenarios.json structure."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
SCENARIOS = ROOT / "scenarios" / "scenarios.json"
DATASET = ROOT / "dataset"


def load_scenarios() -> list[dict[str, Any]]:
    return json.loads(SCENARIOS.read_text(encoding="utf-8"))


def index_case_ids() -> set[str]:
    ids: set[str] = set()
    for name in (
        "preference.jsonl",
        "retrieval_queries.jsonl",
        "conflict.jsonl",
        "forget.jsonl",
        "security.jsonl",
        "knowledge_corpus.jsonl",
    ):
        path = DATASET / name
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            cid = row.get("case_id") or row.get("memory_id")
            if cid:
                ids.add(cid)
    return ids


def validate_scenario(scn: dict[str, Any], known_ids: set[str]) -> list[str]:
    errs: list[str] = []
    sid = scn.get("scenario_id", "?")
    turns = scn.get("turns") or []
    if not turns:
        errs.append(f"{sid}: missing turns[]")
        return errs
    turn_ids = [t.get("turn_id") for t in turns]
    if len(turn_ids) != len(set(turn_ids)):
        errs.append(f"{sid}: duplicate turn_id")
    demo = scn.get("demo_path") or []
    for tid in demo:
        if tid not in turn_ids:
            errs.append(f"{sid}: demo_path references unknown {tid}")
    for turn in turns:
        for ref in turn.get("ref_cases") or []:
            if ref.startswith("mem_") and ref not in known_ids:
                errs.append(f"{sid} {turn.get('turn_id')}: unknown ref {ref}")
            elif ref.split("-", 1)[0] in {"PREF", "RET", "CONF", "FORG", "SEC"}:
                if ref not in known_ids:
                    errs.append(f"{sid} {turn.get('turn_id')}: unknown ref {ref}")
    return errs


def print_scenario(scn: dict[str, Any], *, demo_only: bool = False) -> None:
    sid = scn["scenario_id"]
    print(f"\n{'=' * 60}")
    print(f"{sid} {scn.get('name')}  role={scn.get('role')}  user={scn.get('user_id')}")
    print(f"doc: scenarios/{scn.get('doc')}")
    if scn.get("demo_path"):
        print(f"demo_path: {' → '.join(scn['demo_path'])}")
    print(f"status: {scn.get('actual_result_status')}")
    print(f"capabilities: {', '.join(scn.get('capabilities') or [])}")
    print("-" * 60)
    turns = scn.get("turns") or []
    demo_set = set(scn.get("demo_path") or [])
    for turn in turns:
        tid = turn.get("turn_id")
        if demo_only and tid not in demo_set:
            continue
        mark = "*" if tid in demo_set else " "
        goal = turn.get("goal", "")
        ui = turn.get("user_input")
        ui_s = "(系统操作)" if ui is None else ui
        refs = ", ".join(turn.get("ref_cases") or []) or "—"
        criteria = ", ".join(turn.get("pass_criteria") or [])
        print(f"{mark} {tid} | {goal}")
        print(f"    输入: {ui_s}")
        print(f"    用例: {refs}")
        print(f"    验收: {criteria}")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Scenario turn checklist")
    parser.add_argument("--id", help="Scenario id, e.g. SCN-01")
    parser.add_argument("--demo", action="store_true", help="Show demo_path turns only")
    parser.add_argument("--validate", action="store_true", help="Validate structure and refs")
    args = parser.parse_args()

    scenarios = load_scenarios()
    known = index_case_ids()
    by_id = {s["scenario_id"]: s for s in scenarios}

    if args.validate:
        errs: list[str] = []
        for scn in scenarios:
            errs.extend(validate_scenario(scn, known))
        if errs:
            for e in errs:
                print(f"FAIL: {e}")
            return 1
        print(f"OK: {len(scenarios)} scenarios, turns validated")
        return 0

    if args.id:
        scn = by_id.get(args.id)
        if scn is None:
            print(f"unknown scenario: {args.id}")
            return 1
        print_scenario(scn, demo_only=args.demo)
        return 0

    for scn in scenarios:
        print_scenario(scn, demo_only=args.demo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
