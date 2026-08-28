# -*- coding: utf-8 -*-
"""Check scenario private refs share the scenario user_id (8_4 P1)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "dataset"
SCENARIOS_JSON = ROOT / "scenarios" / "scenarios.json"

PUBLIC_USERS = {"usr_corpus_shared"}
TASK_FILES = {
    "PREF": "preference.jsonl",
    "CONF": "conflict.jsonl",
    "FORG": "forget.jsonl",
    "RET": "retrieval_queries.jsonl",
    "SEC": "security.jsonl",
}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def index_cases() -> dict[str, dict[str, Any]]:
    idx: dict[str, dict[str, Any]] = {}
    for fname in set(TASK_FILES.values()):
        path = DATASET / fname
        if not path.exists():
            continue
        for row in load_jsonl(path):
            cid = row.get("case_id")
            if cid:
                idx[cid] = row
    # corpus by memory_id
    corpus_path = DATASET / "knowledge_corpus.jsonl"
    if corpus_path.exists():
        for row in load_jsonl(corpus_path):
            mid = row.get("memory_id")
            if mid:
                idx[mid] = row
    return idx


def case_prefix(case_id: str) -> str:
    return case_id.split("-", 1)[0]


def check() -> list[str]:
    errors: list[str] = []
    scenarios = json.loads(SCENARIOS_JSON.read_text(encoding="utf-8"))
    idx = index_cases()

    for scn in scenarios:
        sid = scn["scenario_id"]
        uid = scn["user_id"]
        private = scn.get("ref_private_cases") or [
            c for c in scn.get("ref_cases", []) if not str(c).startswith("mem_kb_")
        ]
        public_mems = scn.get("ref_public_memory_ids") or scn.get("ref_memory_ids") or []

        for cid in private:
            row = idx.get(cid)
            if row is None:
                errors.append(f"{sid}: missing case {cid}")
                continue
            cuid = row.get("user_id")
            if cid.startswith("RET-"):
                # retrieval query user must be scenario user; gold may be public
                if cuid != uid:
                    errors.append(f"{sid}: {cid} user_id={cuid} != scenario {uid}")
                golds = (row.get("expected") or {}).get("gold_memory_ids") or []
                for gid in golds:
                    grow = idx.get(gid)
                    if grow is None:
                        errors.append(f"{sid}: {cid} gold {gid} missing in corpus")
                        continue
                    guid = grow.get("user_id")
                    if guid not in PUBLIC_USERS and guid != uid:
                        errors.append(
                            f"{sid}: {cid} gold {gid} user_id={guid} not public/self"
                        )
                continue
            if cuid != uid:
                errors.append(f"{sid}: private {cid} user_id={cuid} != scenario {uid}")
            # nested fixtures
            if cid.startswith("CONF-"):
                for key in ("old", "new"):
                    nested = (row.get(key) or {}).get("user_id")
                    if nested and nested != uid:
                        errors.append(f"{sid}: {cid}.{key}.user_id={nested} != {uid}")
            if cid.startswith("FORG-"):
                for fx in row.get("memory_fixtures") or []:
                    fuid = fx.get("user_id")
                    if fuid and fuid != uid:
                        errors.append(
                            f"{sid}: {cid} fixture {fx.get('memory_id')} user_id={fuid}"
                        )
            if cid.startswith("PREF-"):
                for ev in row.get("input_events") or []:
                    if ev.get("user_id") and ev["user_id"] != uid:
                        errors.append(f"{sid}: {cid} input_event user_id mismatch")

        for mid in public_mems:
            row = idx.get(mid)
            if row is None:
                errors.append(f"{sid}: public memory {mid} missing")
                continue
            guid = row.get("user_id")
            if guid not in PUBLIC_USERS:
                errors.append(
                    f"{sid}: {mid} marked public but user_id={guid} not in {PUBLIC_USERS}"
                )

    return errors


def main() -> int:
    errs = check()
    if errs:
        print("FAIL: scenario user isolation")
        for e in errs:
            print(" -", e)
        return 1
    print("OK: scenario private refs match scenario user_id; public golds are shared")
    return 0


if __name__ == "__main__":
    sys.exit(main())
